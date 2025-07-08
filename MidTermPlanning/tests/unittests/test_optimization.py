import unittest
from datetime import datetime, timedelta
from typing import Callable

from dynreact.base.LotsOptimizer import LotsOptimizationAlgo, LotsOptimizer, LotsOptimizationState, OptimizationListener
from dynreact.base.PlantPerformanceModel import PlantPerformanceModel
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.TestPerformanceModel import TestPerformanceModel, TestPerformanceConfig, PlantPerformanceBasic, \
    Concatenation, BaseCondition
from dynreact.base.model import Site, Process, Equipment, ProductionTargets, ProductionPlanning, Snapshot, Order, \
    Material, OrderAssignment, EquipmentStatus, Model, EquipmentProduction, Lot

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
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments, snapshot, planning_period) for p in plants}
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
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments, snapshot, planning_period) for p in plants}
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
            {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments, snapshot, planning_period) for p in plants}
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
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments, snapshot, planning_period) for p in plants}
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
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments, snapshot, planning_period) for p in plants}
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

    def test_lot_creation_with_predecessor(self):
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
        # a->b has high transition costs, and c->b is slightly more expensive than b->c, so without the start cond. the order b->c would be preferred
        transition_costs = {"a": {"b": 10, "c": 1}, "b": {"a": 10, "c": 1}, "c": {"a": 1, "b": 2}}
        costs = SimpleCostProvider("simple:costs", test_site, transition_costs, minimum_possible_costs=1, missing_weight_costs=1)
        p_id = plants[0].id
        # we create an existing lot for order "a"
        existing_lots: dict[int, list[Lot]] = {p_id: [Lot(id="TestLot1", equipment=p_id, active=True, status=4, orders=[orders[0].id])]}
        snapshot = Snapshot(timestamp=datetime(2025, 6, 18) ,orders=orders, material=OptimizationTest._create_coils_for_orders(orders, process_id),
                            inline_material={}, lots=existing_lots)
        planning_period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
        target_weight = 20  # include 2 out of three orders
        targets: ProductionTargets = ProductionTargets(process=process, target_weight={p.id: EquipmentProduction(equipment=p.id, total_weight=target_weight) for p in plants},  period=planning_period)
        # b and c included for scheduling
        start_assignments: dict[str, OrderAssignment] = { o.id: OrderAssignment(equipment=-1, order=o.id, lot="", lot_idx=-1) for o in orders[1:]}
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments,
                                                       snapshot, planning_period, previous_order=orders[0].id) for p in plants}
        initial_solution: ProductionPlanning = ProductionPlanning(process=process, order_assignments=start_assignments,
                                                                  equipment_status=initial_status, previous_orders={p_id: orders[0].id})
        algo: LotsOptimizationAlgo = TabuAlgorithm(test_site)
        optimization: LotsOptimizer = algo.create_instance(process, snapshot, costs, targets=targets, initial_solution=initial_solution)
        # optimization.add_listener(TestListener())  # for debugging
        optimization_state: LotsOptimizationState = optimization.run(max_iterations=10)
        solution: ProductionPlanning = optimization_state.best_solution

        all_lots = solution.get_lots()
        assert len(all_lots) > 0, "No lots generated"
        lots: list[Lot] = all_lots.get(p_id)
        assert len(lots) == 1, f"Unexpected number of lots: {len(lots)}"
        lot = lots[0]
        assert len(lot.orders) == 2, f"Unexpected number of orders in lot: {len(lot.orders)}: {lot.orders}"
        assert lot.orders[0] == orders[-1].id and lot.orders[1] == orders[-2].id, f"Unexpected lot order: expected: {[orders[-1].id, orders[-2].id]}, got: {lot.orders}"

    def test_lot_creation_with_lot_weight_range(self):
        process = "testProcess"
        process_id = 0
        num_plants = 1
        num_orders = 50
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=process) for p in range(num_plants)]
        test_site = Site(processes=[Process(name_short=process, process_ids=[process_id])], equipment=plants, storages=[], material_categories=[])
        orders = [OptimizationTest._create_order("order" + str(o), range(num_plants), 10) for o in range(num_orders)]  # each order weighs 10t here
        # a->b has high transition costs, and c->b is slightly more expensive than b->c, so without the start cond. the order b->c would be preferred
        transition_costs = {o1.id: {o2.id: 1 for o2 in orders if o2.id != o1.id} for o1 in orders}  # all transition costs = 1
        costs = SimpleCostProvider("simple:costs", test_site, transition_costs, minimum_possible_costs=1, missing_weight_costs=100, surplus_weight_costs=100)
        p_id = plants[0].id
        snapshot = Snapshot(timestamp=datetime(2025, 6, 18), orders=orders,material=OptimizationTest._create_coils_for_orders(orders, process_id),inline_material={}, lots={})
        planning_period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
        target_weight = 200  # aim to include 20 orders
        lot_weight_range = (45, 55)  # aim for lots of 5 orders
        targets: ProductionTargets = ProductionTargets(process=process, target_weight={p.id: EquipmentProduction(equipment=p.id, total_weight=target_weight, lot_weight_range=lot_weight_range) for p in plants},period=planning_period)
        start_assignments: dict[str, OrderAssignment] = { o.id: OrderAssignment(equipment=-1, order=o.id, lot="", lot_idx=-1) for o in orders}
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments,
                                                       snapshot, planning_period, previous_order=orders[0].id) for p in plants}
        initial_solution: ProductionPlanning = ProductionPlanning(process=process, order_assignments=start_assignments,equipment_status=initial_status)
        algo: LotsOptimizationAlgo = TabuAlgorithm(test_site)
        optimization: LotsOptimizer = algo.create_instance(process, snapshot, costs, targets=targets, initial_solution=initial_solution)
        # optimization.add_listener(TestListener())  # for debugging
        optimization_state: LotsOptimizationState = optimization.run(max_iterations=20)
        solution: ProductionPlanning = optimization_state.best_solution

        all_lots = solution.get_lots()
        assert len(all_lots) > 0, "No lots generated"
        lots: list[Lot] = all_lots.get(p_id)
        assert len(lots) > 0, f"No lots generated 2"
        order_ids_included = [o for lot in lots for o in lot.orders]
        orders_included = [o for o in orders if o.id in order_ids_included]
        total_weight = sum(o.actual_weight for o in orders_included)
        assert abs(total_weight-target_weight)/target_weight < 0.1, f"Specified target weight was {target_weight}, but {total_weight} has been assigned"
        for lot in lots:
            lot_size = sum(o.actual_weight for o in orders_included if o.id in lot.orders)
            assert lot_weight_range[0] <= lot_size <= lot_weight_range[1], f"Lot size {lot_size} of lot {lot.id} outside bound {lot_weight_range}"

    def test_lot_creation_with_min_due_date(self):
        process = "testProcess"
        process_id = 0
        num_plants = 1
        num_orders = 3
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=process) for p in range(num_plants)]
        test_site = Site(processes=[Process(name_short=process, process_ids=[process_id])], equipment=plants, storages=[], material_categories=[])
        orders = [OptimizationTest._create_order("order" + str(o), range(num_plants), 10) for o in range(num_orders)]  # each order weighs 10t here
        special_order = "order" + str(num_orders)
        min_due_date = datetime(year=2025, month=6, day=28)
        orders.append(OptimizationTest._create_order(special_order, range(num_plants), 10, due_date=min_due_date - timedelta(days=1)))
        snapshot = Snapshot(timestamp=min_due_date - timedelta(days=7), orders=orders, material=OptimizationTest._create_coils_for_orders(orders, process_id),inline_material={}, lots={})
        planning_period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
        # a->b has high transition costs, and c->b is slightly more expensive than b->c, so without the start cond. the order b->c would be preferred
        transition_costs = {o1.id: {o2.id: 1 if o2.id != special_order and o1.id != special_order else 3 for o2 in orders if o2.id != o1.id} for o1 in orders}  # all transition costs = 1
        costs = SimpleCostProvider("simple:costs", test_site, transition_costs, minimum_possible_costs=1, missing_weight_costs=100, surplus_weight_costs=100)
        p_id = plants[0].id
        target_weight = orders[0].actual_weight * (len(orders) - 2)  # do not schedule all orders
        targets: ProductionTargets = ProductionTargets(process=process, target_weight={p.id: EquipmentProduction(equipment=p.id, total_weight=target_weight) for p in plants},period=planning_period)
        start_assignments: dict[str, OrderAssignment] = { o.id: OrderAssignment(equipment=-1, order=o.id, lot="", lot_idx=-1) for idx, o in enumerate(orders)}
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments,
                                                       snapshot, planning_period, previous_order=orders[0].id) for p in plants}
        initial_solution: ProductionPlanning = ProductionPlanning(process=process, order_assignments=start_assignments,equipment_status=initial_status)
        algo: LotsOptimizationAlgo = TabuAlgorithm(test_site)
        optimization: LotsOptimizer = algo.create_instance(process, snapshot, costs, targets=targets, initial_solution=initial_solution, min_due_date=min_due_date)
        # optimization.add_listener(TestListener())  # for debugging
        optimization_state: LotsOptimizationState = optimization.run(max_iterations=20)
        solution: ProductionPlanning = optimization_state.best_solution

        all_lots = solution.get_lots()
        assert len(all_lots) > 0, "No lots generated"
        lots: list[Lot] = all_lots.get(p_id)
        assert len(lots) > 0, f"No lots generated 2"
        order_ids_included = [o for lot in lots for o in lot.orders]
        assert special_order in order_ids_included, f"Forced order not scheduled: {order_ids_included}, looking for {special_order}"

    def test_lot_creation_with_forced_orders(self):
        process = "testProcess"
        process_id = 0
        num_plants = 1
        num_orders = 3
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=process) for p in range(num_plants)]
        test_site = Site(processes=[Process(name_short=process, process_ids=[process_id])], equipment=plants, storages=[], material_categories=[])
        orders = [OptimizationTest._create_order("order" + str(o), range(num_plants), 10) for o in range(num_orders)]  # each order weighs 10t here
        special_order = "order" + str(num_orders)
        orders.append(OptimizationTest._create_order(special_order, range(num_plants), 10))
        snapshot = Snapshot(timestamp=datetime(year=2025, month=6, day=25), orders=orders, material=OptimizationTest._create_coils_for_orders(orders, process_id),inline_material={}, lots={})
        planning_period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
        # a->b has high transition costs, and c->b is slightly more expensive than b->c, so without the start cond. the order b->c would be preferred
        transition_costs = {o1.id: {o2.id: 1 if o2.id != special_order and o1.id != special_order else 3 for o2 in orders if o2.id != o1.id} for o1 in orders}  # all transition costs = 1
        costs = SimpleCostProvider("simple:costs", test_site, transition_costs, minimum_possible_costs=1, missing_weight_costs=100, surplus_weight_costs=100)
        p_id = plants[0].id
        target_weight = orders[0].actual_weight * (len(orders) - 2)  # do not schedule all orders
        targets: ProductionTargets = ProductionTargets(process=process, target_weight={p.id: EquipmentProduction(equipment=p.id, total_weight=target_weight) for p in plants},period=planning_period)
        start_assignments: dict[str, OrderAssignment] = { o.id: OrderAssignment(equipment=-1, order=o.id, lot="", lot_idx=-1) for idx, o in enumerate(orders)}
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments,
                                                       snapshot, planning_period, previous_order=orders[0].id) for p in plants}
        initial_solution: ProductionPlanning = ProductionPlanning(process=process, order_assignments=start_assignments,equipment_status=initial_status)
        algo: LotsOptimizationAlgo = TabuAlgorithm(test_site)
        optimization: LotsOptimizer = algo.create_instance(process, snapshot, costs, targets=targets, initial_solution=initial_solution, forced_orders=[special_order])
        # optimization.add_listener(TestListener())  # for debugging
        optimization_state: LotsOptimizationState = optimization.run(max_iterations=20)
        solution: ProductionPlanning = optimization_state.best_solution

        all_lots = solution.get_lots()
        assert len(all_lots) > 0, "No lots generated"
        lots: list[Lot] = all_lots.get(p_id)
        assert len(lots) > 0, f"No lots generated 2"
        order_ids_included = [o for lot in lots for o in lot.orders]
        assert special_order in order_ids_included, f"Forced order not scheduled: {order_ids_included}, looking for {special_order}"

    def test_append_to_lots(self):
        process = "testProcess"
        process_id = 0
        num_plants = 2
        num_orders_p1 = 3
        num_orders_p2 = 5
        num_orders_unassigned = 25
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=process) for p in range(num_plants)]
        test_site = Site(processes=[Process(name_short=process, process_ids=[process_id])], equipment=plants, storages=[], material_categories=[])
        orders_p1 = [OptimizationTest._create_order("order_p1_" + str(o), list(range(num_plants)), 10) for o in range(num_orders_p1)]  # each order weighs 10t here
        orders_p2 = [OptimizationTest._create_order("order_p2_" + str(o), list(range(num_plants)), 10) for o in range(num_orders_p2)]  # each order weighs 10t here
        orders_un = [OptimizationTest._create_order("order_un_" + str(o), list(range(num_plants)), 10) for o in range(num_orders_unassigned)]  # each order weighs 10t here
        orders = orders_p1 + orders_p2 + orders_un
        snapshot = Snapshot(timestamp=datetime(year=2025, month=6, day=25), orders=orders, material=OptimizationTest._create_coils_for_orders(orders, process_id),inline_material={}, lots={})
        planning_period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
        # groups p1, p2 and un each have low internal transition costs but between groups costs are costs
        transition_costs = {o1.id: {o2.id: 0 if o1.id == o2.id else 10 if o1.id[6:8] != o2.id[6:8] else 1 for o2 in orders} for o1 in orders}  #
        costs = SimpleCostProvider("simple:costs", test_site, transition_costs, minimum_possible_costs=1, missing_weight_costs=100, surplus_weight_costs=100)
        p1 = plants[0]
        p2 = plants[1]
        initial_lots: dict[int, Lot] = {
            p1.id: Lot(id=f"Lot_{p1.id}.1", equipment=p1.id, active=True, status=4, orders=[o.id for o in orders_p1[:2]]),
            p2.id: Lot(id=f"Lot_{p2.id}.1", equipment=p2.id, active=True, status=4,orders=[o.id for o in orders_p2[:2]])
        }
        orders_in_lots: list[str] = [o for lot in initial_lots.values() for o in lot.orders]
        target_weight: int = 100   # aim for 10 orders
        targets: ProductionTargets = ProductionTargets(process=process, target_weight={p.id: EquipmentProduction(equipment=p.id, total_weight=target_weight) for p in plants},period=planning_period)
        start_assignments: dict[str, OrderAssignment] = {o: OrderAssignment(order=o, lot=lot.id, equipment=lot.equipment, lot_idx=idx+1) for lot in initial_lots.values() for idx, o in enumerate(lot.orders)}
        start_assignments.update({o.id: OrderAssignment(equipment=-1, order=o.id, lot="", lot_idx=-1) for idx, o in enumerate(orders) if o.id not in orders_in_lots})
        initial_status: dict[int, EquipmentStatus] = {p.id: costs.evaluate_equipment_assignments(targets.target_weight.get(p.id), process, start_assignments, snapshot, planning_period) for p in plants}
        initial_solution: ProductionPlanning = ProductionPlanning(process=process, order_assignments=start_assignments,equipment_status=initial_status, previous_orders={p: lot.orders[-1] for p, lot in initial_lots.items()})
        algo: LotsOptimizationAlgo = TabuAlgorithm(test_site)
        optimization: LotsOptimizer = algo.create_instance(process, snapshot, costs, targets=targets, initial_solution=initial_solution, base_lots=initial_lots)

        def check_expected_lots(solution: ProductionPlanning, objective: float):
            all_lots = solution.get_lots()
            assert len(all_lots) == 2, f"Expected updated lots for two plants, got {len(all_lots)}"
            lots_flat = [lot for lots in all_lots.values() for lot in lots]
            assert len(all_lots) == 2, f"Expected two updated lots, got {len(lots_flat)}"
            for lot in lots_flat:
                initial_lot = initial_lots.get(lot.equipment)
                for idx, order in enumerate(initial_lot.orders):
                    assert order in lot.orders, f"Order {order} should have been preserved in lot {lot.id}"
                    assert lot.orders.index(order) == idx, f"Order {order} expected at position {idx} in lot {lot.id}, found it at position {lot.orders.index(order)}"
                assert len(lot.orders) > len(initial_lot.orders), f"Expected to append orders to lot"
                expected_orders = num_orders_p1 if lot.equipment == p1.id else num_orders_p2
                assert len(lot.orders) == expected_orders, f"Unexpected number of orders in lot {lot.id}: {len(lot.orders)}, expected: {expected_orders}"

        listener = InterruptionTestListener(check_expected_lots)
        optimization.add_listener(listener)
        optimization_state: LotsOptimizationState = optimization.run(max_iterations=25)   # will stop earlier when the target has been reached
        listener.check()


    @staticmethod
    def _create_order(id: str, plants: list[int], weight: float, due_date: datetime|None=None, priority: int=0):
        return Order(id=id, allowed_equipment=plants, target_weight=weight, actual_weight=weight, due_date=due_date, material_properties=TestMaterial(material_id="test"),
                     current_processes=[], active_processes={}, priority=priority)

    @staticmethod
    def _create_coils_for_orders(orders: list[Order], process: int) -> list[Material]:  # one coil per order
        return [Material(id=o.id + "1", order=o.id, weight=o.actual_weight, order_position=1, current_process=process) for o in orders]


class TestMaterial(Model):

    material_id: str


class InterruptionTestListener(OptimizationListener):  # FIXME this does not work because local functions cannot be pickled => we need to avoid passing the listener to the optimization processses

    def __init__(self, test_function: Callable[[ProductionPlanning, float], None]):
        super().__init__()
        self._test_function = test_function
        self._success: bool = False
        self._assertion_error = AssertionError("Test listener not executed")

    def update_solution(self, planning: ProductionPlanning, objective_value: float):
        try:
            self._test_function(planning, objective_value)
            self._success = True
        except AssertionError as e:
            self._assertion_error = e

    def update_iteration(self, iteration_cnt: int, lots_cnt: int, objective_value: float) -> bool:
        return not self._success

    def check(self):
        if not self._success:
            raise self._assertion_error



class TestListener(OptimizationListener):

    def update_solution(self, planning: ProductionPlanning, objective_value: float):
        print("~~ solution updated", objective_value, "assignments", planning.order_assignments.values())

    def update_iteration(self, iteration_cnt: int, lots_cnt: int, objective_value: float) -> bool:
        print("~~ iteration updated, iteration cnt", iteration_cnt, "num lots", lots_cnt, ", objective value", objective_value)
        return True


if __name__ == '__main__':
    unittest.main()

