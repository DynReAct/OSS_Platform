import unittest
from datetime import datetime, timedelta

from dynreact.base.LotsOptimizer import LotsOptimizationAlgo, LotsOptimizer, LotsOptimizationState, OptimizationListener
from dynreact.base.PlantPerformanceModel import PlantPerformanceModel
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.TestPerformanceModel import TestPerformanceModel, TestPerformanceConfig, PlantPerformanceBasic, \
    Concatenation, BaseCondition
from dynreact.base.model import Site, Process, Equipment, ProductionTargets, ProductionPlanning, Snapshot, Order, \
    Material, OrderAssignment, EquipmentStatus, Model, EquipmentProduction

from dynreact.lotcreation.LotsOptimizerImpl import TabuAlgorithm
from dynreact.base.impl.SimpleCostProvider import SimpleCostProvider


class OptimizationTest(unittest.TestCase):

    def test_2_orders_1_plant_empty_initial(self):
        process = "testProcess"
        process_id = 0
        num_plants = 1
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=process) for p in range(num_plants)]
        test_site = Site(
            processes=[Process(name_short=process, process_ids=[process_id])],
            equipment=plants,
            storages=[], material_categories=[]
        )
        orders = [OptimizationTest._create_order("a", range(num_plants), 10), OptimizationTest._create_order("b", range(num_plants), 10)]
        snapshot = Snapshot(timestamp=datetime(2024, 5, 1),
                orders=orders, material=OptimizationTest._create_coils_for_orders(orders, process_id), inline_material={}, lots={})
        transition_costs = {"a": {"b": 1}, "b": {"a": 2}}  # in this example it is cheaper to produce a first then b, than vice versa
        costs = SimpleCostProvider("simple:costs", test_site, transition_costs, minimum_possible_costs=1)
        planning_period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
        target_weight = 20
        targets: ProductionTargets = ProductionTargets(process=process, target_weight={p.id: EquipmentProduction(equipment=p.id, total_weight=target_weight) for p in plants}, period=planning_period)
        start_assignments: dict[str, OrderAssignment] = {o.id: OrderAssignment(equipment=-1, order=o.id, lot="", lot_idx=-1) for o in orders}  # nothing assigned yet
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments, snapshot, planning_period, target_weight) for p in plants}
        initial_solution: ProductionPlanning = ProductionPlanning(process=process, order_assignments=start_assignments, equipment_status=initial_status)
        algo: LotsOptimizationAlgo = TabuAlgorithm(test_site)
        optimization: LotsOptimizer = algo.create_instance(process, snapshot, costs, targets=targets, initial_solution=initial_solution)
        # optimization.add_listener(TestListener())  # for debugging
        optimization_state: LotsOptimizationState = optimization.run(max_iterations=10)
        objective_value = optimization_state.best_objective_value.total_value
        assert objective_value == 1, "Unexpected objective value " + str(objective_value)
        solution: ProductionPlanning = optimization_state.best_solution
        all_lots = solution.get_lots()
        assert len(all_lots) > 0 and sum(len(plant_lots) for plant_lots in all_lots.values()) > 0, "No lots generated"
        assert orders[0].id in solution.order_assignments and orders[1].id in solution.order_assignments, "Unexpectedly unassigned order found"
        ass1 = solution.order_assignments[orders[0].id]
        ass2 = solution.order_assignments[orders[1].id]
        assert ass1.lot == ass2.lot, "Orders unexpectedly assigned to different lots"
        assert ass1.lot_idx < ass2.lot_idx, "Unexpeced production order for two orders"

    def test_2_orders_1_plant_initial_swapped(self):
        process = "testProcess"
        process_id = 0
        num_plants = 1
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=process) for p in range(num_plants)]
        test_site = Site(
            processes=[Process(name_short=process, process_ids=[process_id])],
            equipment=plants,
            storages=[], material_categories=[]
        )
        orders = [OptimizationTest._create_order("a", range(num_plants), 10), OptimizationTest._create_order("b", range(num_plants), 10)]
        snapshot = Snapshot(timestamp=datetime(2024, 5, 1),
                orders=orders, material=OptimizationTest._create_coils_for_orders(orders, process_id), inline_material={}, lots={})
        transition_costs = {"a": {"b": 1}, "b": {"a": 2}}  # in this example it is cheaper to produce a first then b, than vice versa
        costs = SimpleCostProvider("simple:costs", test_site, transition_costs, minimum_possible_costs=0)  # avoid early break
        planning_period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
        target_weight = 20
        targets: ProductionTargets = ProductionTargets(process=process, target_weight={p.id: EquipmentProduction(equipment=p.id, total_weight=target_weight) for p in plants}, period=planning_period)
        # this is not the optimum solution, but rather the two orders are swapped
        start_assignments: dict[str, OrderAssignment] = {
            orders[0].id: OrderAssignment(equipment=plants[0].id, order=orders[0].id, lot=plants[0].name_short + "1", lot_idx=2),
            orders[1].id: OrderAssignment(equipment=plants[0].id, order=orders[1].id, lot=plants[0].name_short + "1", lot_idx=1)
        }
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments, snapshot, planning_period, target_weight) for p in plants}
        initial_solution: ProductionPlanning = ProductionPlanning(process=process, order_assignments=start_assignments, equipment_status=initial_status)
        algo: LotsOptimizationAlgo = TabuAlgorithm(test_site)
        optimization: LotsOptimizer = algo.create_instance(process, snapshot, costs, targets=targets, initial_solution=initial_solution)
        # optimization.add_listener(TestListener())  # for debugging
        optimization_state: LotsOptimizationState = optimization.run(max_iterations=10)
        objective_value = optimization_state.best_objective_value.total_value
        assert objective_value == 1, "Unexpected objective value " + str(objective_value)  # TODO parameters
        solution: ProductionPlanning = optimization_state.best_solution
        assert orders[0].id in solution.order_assignments and orders[1].id in solution.order_assignments, "Unexpectedly unassigned order found"
        ass1 = solution.order_assignments[orders[0].id]
        ass2 = solution.order_assignments[orders[1].id]
        assert ass1.lot == ass2.lot, "Orders unexpectedly assigned to different lots"
        assert ass1.lot_idx < ass2.lot_idx, "Unexpected production order for two orders"

    def test_optimization_respects_plant_performance_model_results(self):
        process = "testProcess"
        process_id = 0
        num_plants = 1
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=process) for p in range(num_plants)]
        test_site = Site(
            processes=[Process(name_short=process, process_ids=[process_id])],
            equipment=plants,
            storages=[], material_categories=[]
        )
        orders = [OptimizationTest._create_order(oid, range(num_plants), 10) for oid in ["a", "b", "c", "d"]]
        now: datetime = DatetimeUtils.now()
        snapshot = Snapshot(timestamp=now,  orders=orders, material=OptimizationTest._create_coils_for_orders(orders, process_id), inline_material={}, lots={})
        transition_costs = {"a": {"b": 1, "c": 1, "d": 1}, "b": {"a": 1, "c": 1, "d": 1}, "c": {"a": 1, "b": 1, "d": 1}, "d": {"a": 1, "b": 1, "c": 1}}
        costs = SimpleCostProvider("simple:costs", test_site, transition_costs, minimum_possible_costs=0)  # avoid early break
        planning_period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
        # target is to produce all of the orders
        target_weight = sum(o.actual_weight for o in orders)
        targets: ProductionTargets = ProductionTargets(process=process, target_weight={p.id: EquipmentProduction(equipment=p.id, total_weight=target_weight) for p in plants}, period=planning_period)
        plant: int = plants[0].id

        # the plant performance model tells us: orders "b" and "d" cannot be produced on plant 0
        affected_orders = Concatenation(operator="OR", items=[BaseCondition(field="id", condition="=", value="b"), BaseCondition(field="id", condition="=", value="d")])
        ppm_config: TestPerformanceConfig = TestPerformanceConfig(id="test0", equipment={plant:
                    [PlantPerformanceBasic(equipment=plant, performance=0, start=now-timedelta(days=1), end=now+timedelta(days=365), affected_orders=affected_orders)]})
        ppm: PlantPerformanceModel = TestPerformanceModel("", test_site, config=ppm_config)

        # initial solution: all orders in a single lot
        start_assignments: dict[str, OrderAssignment] = \
            {order.id: OrderAssignment(equipment=plants[0].id, order=order.id, lot=plants[0].name_short + ".1", lot_idx=idx + 1) for idx, order in enumerate(orders)}
        initial_status: dict[int, EquipmentStatus] = \
            {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments, snapshot, planning_period, target_weight) for p in plants}
        initial_solution: ProductionPlanning = ProductionPlanning(process=process, order_assignments=start_assignments, equipment_status=initial_status)
        algo: LotsOptimizationAlgo = TabuAlgorithm(test_site)
        optimization: LotsOptimizer = algo.create_instance(process, snapshot, costs, targets=targets, initial_solution=initial_solution, performance_models=[ppm])
        # optimization.add_listener(TestListener())  # for debugging
        optimization_state: LotsOptimizationState = optimization.run(max_iterations=10)
        assignments: dict[str, int] = {order: ass.equipment for order, ass in optimization_state.best_solution.order_assignments.items()}
        for forbidden_order in ["b", "d"]:
            assert forbidden_order not in assignments or assignments.get(forbidden_order) < 0, \
                "Order " + forbidden_order + " is disallowed for the plant considered by a plant performance model but has been assigned nevertheless"
        for allowed_order in ["a", "c"]:
            assert allowed_order in assignments and assignments.get(allowed_order) >= 0, \
                "Order " + allowed_order + " should have been assigned to a lot"

    def test_2_orders_1_plant_with_priority(self):
        process = "testProcess"
        process_id = 0
        num_plants = 1
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=process) for p in range(num_plants)]
        test_site = Site(
            processes=[Process(name_short=process, process_ids=[process_id])],
            equipment=plants, storages=[], material_categories=[]
        )
        orders = [
            OptimizationTest._create_order("a", range(num_plants), 10),
            OptimizationTest._create_order("b", range(num_plants), 10),
            OptimizationTest._create_order("c", range(num_plants), 10, priority=10)]  # high priority!
        snapshot = Snapshot(timestamp=datetime(2024, 5, 1),
                orders=orders, material=OptimizationTest._create_coils_for_orders(orders, process_id), inline_material={}, lots={})
        transition_costs = {"a": {"b": 1, "c": 2}, "b": {"a": 1, "c": 2}, "c": {"a": 2, "b": 2}}    # c has high transition costs, but also a high priority
        costs = SimpleCostProvider("simple:costs", test_site, transition_costs, minimum_possible_costs=1, priority_costs_factor=1)
        planning_period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
        target_weight = 20  # include 2 out of three orders
        targets: ProductionTargets = ProductionTargets(process=process, target_weight={p.id: EquipmentProduction(equipment=p.id, total_weight=target_weight) for p in plants}, period=planning_period)
        start_assignments: dict[str, OrderAssignment] = {o.id: OrderAssignment(equipment=-1, order=o.id, lot="", lot_idx=-1) for o in orders}  # nothing assigned yet
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments, snapshot, planning_period, target_weight) for p in plants}
        initial_solution: ProductionPlanning = ProductionPlanning(process=process, order_assignments=start_assignments, equipment_status=initial_status)
        algo: LotsOptimizationAlgo = TabuAlgorithm(test_site)
        optimization: LotsOptimizer = algo.create_instance(process, snapshot, costs, targets=targets, initial_solution=initial_solution)
        # optimization.add_listener(TestListener())  # for debugging
        optimization_state: LotsOptimizationState = optimization.run(max_iterations=10)
        solution: ProductionPlanning = optimization_state.best_solution
        all_lots = solution.get_lots()
        assert len(all_lots) > 0 and sum(len(plant_lots) for plant_lots in all_lots.values()) > 0, "No lots generated"
        assert orders[-1].id in solution.order_assignments, "Priority order not in lot"
        assert solution.order_assignments[orders[-1].id].equipment == plants[0].id, "Priority order not in lot"

    def test_2_orders_1_plant_with_custom_priority(self):
        """
        Exactly like the test above, but with custom priority set instead of order priority
        :return:
        """
        process = "testProcess"
        process_id = 0
        num_plants = 1
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=process) for p in range(num_plants)]
        test_site = Site(
            processes=[Process(name_short=process, process_ids=[process_id])],
            equipment=plants, storages=[], material_categories=[]
        )
        orders = [
            OptimizationTest._create_order("a", range(num_plants), 10),
            OptimizationTest._create_order("b", range(num_plants), 10),
            OptimizationTest._create_order("c", range(num_plants), 10)]
        custom_priorities = {"c":  10}  # high prio
        snapshot = Snapshot(timestamp=datetime(2024, 5, 1),
                orders=orders, material=OptimizationTest._create_coils_for_orders(orders, process_id), inline_material={}, lots={})
        transition_costs = {"a": {"b": 1, "c": 2}, "b": {"a": 1, "c": 2}, "c": {"a": 2, "b": 2}}    # c has high transition costs, but also a high priority
        costs = SimpleCostProvider("simple:costs", test_site, transition_costs, minimum_possible_costs=1, priority_costs_factor=1)
        planning_period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
        target_weight = 20  # include 2 out of three orders
        targets: ProductionTargets = ProductionTargets(process=process, target_weight={p.id: EquipmentProduction(equipment=p.id, total_weight=target_weight) for p in plants}, period=planning_period)
        start_assignments: dict[str, OrderAssignment] = {o.id: OrderAssignment(equipment=-1, order=o.id, lot="", lot_idx=-1) for o in orders}  # nothing assigned yet
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments, snapshot, planning_period, target_weight) for p in plants}
        initial_solution: ProductionPlanning = ProductionPlanning(process=process, order_assignments=start_assignments, equipment_status=initial_status)
        algo: LotsOptimizationAlgo = TabuAlgorithm(test_site)
        optimization: LotsOptimizer = algo.create_instance(process, snapshot, costs, targets=targets, initial_solution=initial_solution, orders_custom_priority=custom_priorities)
        # optimization.add_listener(TestListener())  # for debugging
        optimization_state: LotsOptimizationState = optimization.run(max_iterations=10)
        solution: ProductionPlanning = optimization_state.best_solution
        all_lots = solution.get_lots()
        assert len(all_lots) > 0 and sum(len(plant_lots) for plant_lots in all_lots.values()) > 0, "No lots generated"
        assert orders[-1].id in solution.order_assignments, "Priority order not in lot"
        assert solution.order_assignments[orders[-1].id].equipment == plants[0].id, "Priority order not in lot"


    @staticmethod
    def _create_order(id: str, plants: list[int], weight: float, due_date: datetime|None=None, priority: int=0):
        return Order(id=id, allowed_equipment=plants, target_weight=weight, actual_weight=weight, due_date=due_date, material_properties=TestMaterial(material_id="test"),
                     current_processes=[], active_processes={}, priority=priority)

    @staticmethod
    def _create_coils_for_orders(orders: list[Order], process: int) -> list[Material]:  # one coil per order
        return [Material(id=o.id + "1", order=o.id, weight=o.actual_weight, order_position=1, current_process=process) for o in orders]


class TestMaterial(Model):

    material_id: str


class TestListener(OptimizationListener):

    def update_solution(self, planning: ProductionPlanning, objective_value: float):
        print("~~ solution updated", objective_value, "assignments", planning.order_assignments.values())

    def update_iteration(self, iteration_cnt: int, lots_cnt: int, objective_value: float) -> bool:
        print("~~ iteration updated, iteration cnt", iteration_cnt, "num lots", lots_cnt, ", objective value", objective_value)
        return True


if __name__ == '__main__':
    unittest.main()

