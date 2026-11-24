import unittest
from datetime import datetime, timedelta, time
from typing import Mapping, Sequence, Literal, Iterator, Callable

from dynreact.base.EnergyService import EnergyService, EnergyServiceMetadata, EnergyPrediction, ServiceResultsFailed, \
    EnergyCostService
from dynreact.base.LotsOptimizer import LotsOptimizationAlgo, LotsOptimizer, OptimizationListener, LotsOptimizationState
from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.impl.SimpleCostProvider import SimpleCostProvider
from dynreact.base.impl.SimpleEnergyService import SimpleEnergyService, EnergyConfig, EnergyCostConfig, \
    SimpleEnergyCostService
from dynreact.base.model import Equipment, Site, Process, Snapshot, ProductionTargets, OrderAssignment, \
    EquipmentProduction, EquipmentStatus, ProductionPlanning, Order, Model, EnergyType, PlannedWorkingShift, \
    ObjectiveFunction
from dynreact.lotcreation.LotsOptimizerImpl import TabuAlgorithm
from dynreact.lotcreation.TabuParams import TabuParams


class EnergySchedulingTest(unittest.TestCase):

    def test_energy_sensitive_scheduling_works0(self):
        """
        2 orders with different energy characteristics to be scheduled at one plant (o1: 2 MWh, o2: 1 MWh)
        except for energy considerations, o1 -> o2 is the best order, energy price characteristics
        change this to o2 -> o1
        """
        process = "energyTestProcess"
        process_id = 0
        plant = 0
        plants = [Equipment(id=plant, name_short=f"Plant{plant}", process=process, throughput_capacity=20/8)]
        test_site = Site(
            processes=[Process(name_short=process, process_ids=[process_id])],
            equipment=plants,
            storages=[], material_categories=[]
        )
        snap_date = datetime(2024, 5, 1).astimezone()
        orders = [EnergySchedulingTest._create_order("a", (plant, ), 10), EnergySchedulingTest._create_order("b", (plant,), 10)]
        snapshot = Snapshot(timestamp=snap_date, orders=orders, material=tuple(), inline_material={}, lots={})
        transition_costs = {"a": {"b": 1}, "b": {"a": 2}}  # in this example it is cheaper to produce a first then b, than vice versa
        costs = SimpleCostProvider("simple:costs", test_site, transition_costs, minimum_possible_costs=1)
        planning_period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
        target_weight = 20
        targets: ProductionTargets = ProductionTargets(process=process, target_weight={p.id: EquipmentProduction(equipment=p.id, total_weight=target_weight) for p in plants}, period=planning_period)
        start_assignments: dict[str, OrderAssignment] = {o.id: OrderAssignment(equipment=-1, order=o.id, lot="", lot_idx=-1) for o in orders}  # nothing assigned yet
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments, snapshot, planning_period) for p in plants}
        initial_solution: ProductionPlanning = ProductionPlanning(process=process, order_assignments=start_assignments, equipment_status=initial_status)
        algo: LotsOptimizationAlgo = _init_algo(test_site, n_parallel=1, energy_factor=1, default_energy_price={"electric": 1.5})
        shift_duration = timedelta(hours=8)
        shifts = {plants[0].id: (PlannedWorkingShift(equipment=plant, period=(snap_date, snap_date+shift_duration), worktime=shift_duration),)}
        sp = TestSnapshotProvider(test_site, snapshot)
        #
        energy_prediction: Mapping[EnergyType, EnergyService] = {"electric": TestEnergyProvider(test_site, sp,
                                energies={plants[0].id: {orders[0].id: 2, orders[1].id: 1}})}
        # the energy price for the first four hours of the day is twice as high as for the rest
        cc = EnergyCostConfig(energy_type="electric", cost_steps=((time(), 3.), (time(hour=4), 1.)))
        energy_prices: Mapping[EnergyType, EnergyCostService] = {"electric": SimpleEnergyCostService("energyprices+simple:", config=cc)}
        # expected energy prices if o1 -> o2: 6 for order 1, 1 for order 2 => sum 7
        # expected energy prices if o2 -> o1: 3 for order 2, 2 for order 1 => sum 5
        optimization: LotsOptimizer = algo.create_instance(process, snapshot, costs, targets=targets, initial_solution=initial_solution,
                                            shifts=shifts, energy_prices=energy_prices, energy_services=energy_prediction)

        def check_expected_lots(solution: ProductionPlanning, objective: ObjectiveFunction):
            all_lots = solution.get_lots()
            assert len(all_lots) == 1, f"Unexpected number of plants scheduled: {len(all_lots)}, wanted: 1"
            scheduled_orders = [o for lot in all_lots[plant] for o in lot.orders]
            assert len(scheduled_orders) == len(orders), f"Not all orders scheduled: {len(scheduled_orders)}, wanted {len(orders)}"
            assert orders[1].id == scheduled_orders[0], f"Order schedule does not respect energy price objective."

        listener = InterruptionTestListener(check_expected_lots)
        optimization.add_listener(listener)
        optimization_state: LotsOptimizationState = optimization.run(max_iterations=5)
        listener.check()



    @staticmethod
    def _create_order(id: str, plants: Sequence[int], weight: float, due_date: datetime|None=None, priority: int=0, material_classes: Mapping[str, str]|None=None):
        return Order(id=id, allowed_equipment=plants, target_weight=weight, actual_weight=weight, due_date=due_date, material_properties=TestMaterial(material_id="test"),
                     current_processes=[], active_processes={}, priority=priority, material_classes=material_classes or {})


class TestMaterial(Model):

    material_id: str


def _init_algo(site: Site, n_parallel: int|None = None, t_allowed: float|None=None, energy_factor: float|None=None,
               default_energy_price: Mapping[Literal["electric", "heat"], float]|None=None) -> LotsOptimizationAlgo:
    algo: TabuAlgorithm = TabuAlgorithm("default:tabu-search", site)
    algo.set_params(TabuParams(tsp_solver_final_tsp=False, max_tsps_per_worker=-1, rand_seed=42,
                               strict=True, NParallel=n_parallel, TAllowed=t_allowed,
                               energy_costs_penalty=energy_factor, energy_costs_default=default_energy_price))
    return algo


class TestSnapshotProvider(SnapshotProvider):

    def __init__(self, site: Site, snapshot: Snapshot):
        super().__init__("test:", site)
        self._snapshot = snapshot
        self._timestamp = snapshot.timestamp

    def snapshots(self, start_time: datetime, end_time: datetime, order: Literal["asc", "desc"] = "asc") -> Iterator[datetime]:
        t = self._timestamp
        if t < start_time or t > end_time:
            return iter(tuple())
        return iter((t, ))

    def load(self, *args, time: datetime|None=None, **kwargs) -> Snapshot|None:
        return self._snapshot


class TestEnergyProvider(EnergyService):

    def __init__(self, site: Site, snapshot_provider: SnapshotProvider,
                 energies: Mapping[int, Mapping[str, float]], energy_type: EnergyType = "electric",
                 default_energy: float=1):
        super().__init__("test+energy:", site, snapshot_provider)
        self._energy_type = energy_type
        self._energies = energies
        self._default_energy = default_energy
        self._empty = {}

    def service(self) -> EnergyServiceMetadata:
        return EnergyServiceMetadata(id="test", label="test", energy_type=self._energy_type)

    def status(self) -> int:
        return 0

    def energy_consumption(self,
                           order: Order,
                           equipment: int,
                           snapshot: datetime,
                           *args,
                           missing_value_ensemble: Sequence[Order] | None = None,
                           **kwargs) -> EnergyPrediction | ServiceResultsFailed:
        en = self._energies.get(equipment, self._empty).get(order.id, self._default_energy)
        return EnergyPrediction(predicted_energy=en)


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


