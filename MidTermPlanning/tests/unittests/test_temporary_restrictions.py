import unittest
from datetime import datetime, timedelta
from typing import Callable, Sequence

from dynreact.base.LotsOptimizer import OptimizationListener, LotsOptimizationState, LotsOptimizationAlgo, LotsOptimizer
from dynreact.base.TemporaryRestrictionsProvider import TemporaryRestrictionsProvider, EquipmentRestriction
from dynreact.base.conditions import ThresholdCondition
from dynreact.base.impl.SimpleCostProvider import SimpleCostProvider
from dynreact.base.model import Equipment, Site, Process, Snapshot, EquipmentStatus, OrderAssignment, ProductionTargets, \
    EquipmentProduction, Order, Material, Model, ProductionPlanning, ObjectiveFunction, Lot
from dynreact.lotcreation.LotsOptimizerImpl import TabuAlgorithm
from dynreact.lotcreation.TabuParams import TabuParams


def _create_order(oid: str, equipment: list[int], processes: list[int], weight: float=10, material_count: int=1,
                  lots: dict[str, str]|None = None, lot_positions: dict[str, int]|None=None) -> Order:
    return Order(id=oid, target_weight=weight, actual_weight=weight, material_count=material_count, allowed_equipment=equipment, current_processes=processes,
                 active_processes={p: "PENDING" for p in processes}, lots=lots, lot_positions=lot_positions, material_properties={})

def _create_material_for_order(o: Order, process: int, material_count: int = 1) -> list[Material]:
    return [Material(id=f"{o.id}_{i+1}", order=o.id, weight=o.actual_weight/material_count, current_process=process) for i in range(material_count)]

def _init_algo(site: Site, temporary_restrictions: TemporaryRestrictionsProvider|None=None) -> LotsOptimizationAlgo:
    algo: TabuAlgorithm = TabuAlgorithm("default:tabu-search", site, temporary_restrictions=temporary_restrictions)
    # disable limited number of tsps per worker to guarantee deterministic test behaviour
    # params.tsp_solver_global_timeout = 2  # higher timeout in tests to avoid spurious failures?
    algo.set_params(TabuParams(tsp_solver_final_tsp=False, max_tsps_per_worker=-1, rand_seed=42, strict=True))
    return algo


class TemporaryRestrictionsTest(unittest.TestCase):

    def test_restrictions_are_considered(self):
        process = "testProcess"
        process_id = 0
        num_plants = 2
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=process) for p in range(num_plants)]
        test_site = Site(
            processes=[Process(name_short=process, process_ids=[process_id])],
            equipment=plants,
            storages=[], material_categories=[]
        )
        allowed_plants = list(range(num_plants))
        orders = [
                _create_order("prev0", allowed_plants, [0]),
                _create_order("a", allowed_plants, [0]),
                _create_order("prev1", allowed_plants, [0]),
                _create_order("b", allowed_plants, [0])]
        snapshot = Snapshot(timestamp=datetime(2026, 7, 2),
                orders=orders, material=[mat for o in orders for mat in _create_material_for_order(o, process_id)], inline_material={}, lots={})
        # in this example it is cheaper to produce a at plant 0 and b at plant 1
        transition_costs = {"prev0": {"a": 1, "b": 2}, "prev1": {"a": 2, "b": 1}, "a": {"b": 1}, "b": {"a": 1}}
        costs = SimpleCostProvider("simple:costs", test_site, transition_costs, minimum_possible_costs=1)
        planning_period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
        target_weight = orders[0].actual_weight
        targets: ProductionTargets = ProductionTargets(process=process, target_weight={p.id: EquipmentProduction(equipment=p.id, total_weight=target_weight) for p in plants}, period=planning_period)
        start_assignments: dict[str, OrderAssignment] = {o.id: OrderAssignment(equipment=-1, order=o.id, lot="", lot_idx=-1) for o in orders if not o.id.startswith("prev")}  # nothing assigned yet
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id),
                        process, start_assignments, snapshot, planning_period, previous_order=f"prev{p.id}") for p in plants}
        initial_solution: ProductionPlanning = ProductionPlanning(process=process, order_assignments=start_assignments, equipment_status=initial_status)
        # Order a temporarily not allowed at equipment 0
        restriction = EquipmentRestriction(id="test", label="test", equipment=0, condition=ThresholdCondition(attribute="id", operator="=", value="a"))
        restrictions = TestRestrictionsProvider(test_site, [(restriction, True)])
        algo: LotsOptimizationAlgo = _init_algo(test_site, temporary_restrictions=restrictions)
        optimization: LotsOptimizer = algo.create_instance(process, snapshot, costs, targets=targets, initial_solution=initial_solution)

        def check_expected_lots(solution: ProductionPlanning, objective: ObjectiveFunction):
            all_lots: dict[int, list[Lot]] = solution.get_lots()
            assert len(all_lots) == num_plants, f"Plant(s) without lots: {[p for p in range(num_plants) if p not in all_lots]}"
            ass_a = solution.order_assignments["a"]
            ass_b = solution.order_assignments["b"]
            assert ass_a.equipment == 1, f"Temporary constraint has been ignored(?), order \"a\" not assigned to plant 1: {ass_a}"
            assert ass_b.equipment == 0, f"Order \"b\" not assigned to plant 0?: {ass_b}"

        listener = InterruptionTestListener(check_expected_lots)
        optimization.add_listener(listener)
        optimization_state: LotsOptimizationState = optimization.run(max_iterations=10)
        listener.check()


class TestRestrictionsProvider(TemporaryRestrictionsProvider):

    def __init__(self, site: Site, restrictions: Sequence[tuple[EquipmentRestriction, bool]]):
        super().__init__("test:", site)
        self._restrictions: list[tuple[EquipmentRestriction, bool]] = list(restrictions)

    @staticmethod
    def _equipment_matches(rule: EquipmentRestriction, equipment: int|Sequence[int]) -> bool:
        is_multi = isinstance(equipment, Sequence)
        if isinstance(rule.equipment, Sequence):
            return equipment in rule.equipment if not is_multi else any(e in rule.equipment for e in equipment)
        return equipment == rule.equipment if not is_multi else rule.equipment in equipment

    def equipment_restrictions(self, equipment: int|Sequence[int]|None=None, active_only: bool=False) -> Sequence[tuple[EquipmentRestriction, bool]]:
        rules = list(self._restrictions)
        if equipment is not None:
            rules = [r for r in rules if TestRestrictionsProvider._equipment_matches(r[0], equipment)]
        if active_only:
            rules = [r for r in rules if r[1]]
        return rules

    def set_active_status(self, rule: str|Sequence[str], active: bool):
        if isinstance(rule, str):
            rule = (rule, )
        for r in rule:
            r_idx = next((idx for idx, rule in enumerate(self._restrictions) if rule[0].id == r), -1)
            if r_idx >= 0:
                self._restrictions[r_idx] = (self._restrictions[r_idx][0], active)


class InterruptionTestListener(OptimizationListener):

    def __init__(self, test_function: Callable[[ProductionPlanning, ObjectiveFunction], None]):
        super().__init__()
        self._test_function = test_function
        self._success: bool = False
        self._assertion_error = AssertionError("Test listener not executed")
        self._best_objective = float("inf")

    def update_solution(self, planning: ProductionPlanning, objective: ObjectiveFunction):
        if objective.total_value >= self._best_objective:
            return
        self._best_objective = objective.total_value
        try:
            self._test_function(planning, objective)
            self._success = True
        except AssertionError as e:
            self._assertion_error = e

    def update_iteration(self, iteration_cnt: int, lots_cnt: int, objective_value: float) -> bool:
        return not self._success

    def check(self):
        if not self._success:
            raise self._assertion_error
