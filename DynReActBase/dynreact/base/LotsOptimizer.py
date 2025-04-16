"""
The LotsOptimizer module contains the interface specification for the mid-term planning
algorithm. It is possible to provide a custom implementation, but the DynReAct software
already contains an implementation (in the MidTermPlanning folder).
"""

from datetime import timedelta, datetime
from typing import TypeVar, Generic, Sequence

import numpy as np

from dynreact.base.CostProvider import CostProvider
from dynreact.base.PlantPerformanceModel import PlantPerformanceModel
from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.impl.ModelUtils import ModelUtils
from dynreact.base.model import ProductionPlanning, PlanningData, ProductionTargets, Snapshot, OrderAssignment, Site, \
    EquipmentStatus, Equipment, Order, Material, Lot, EquipmentProduction, ObjectiveFunction, MaterialClass


class OptimizationListener:

    def __init__(self):
        self._done: bool = False

    def update_solution(self, planning: ProductionPlanning, objective_value: ObjectiveFunction):
        pass

    def update_iteration(self, iteration_cnt: int, lots_cnt: int, objective_value: ObjectiveFunction) -> bool:
        """
        :return: false to interrupt the iteration
        """
        return True

    def _completed(self):
        self._done = True

    def is_done(self) -> bool:
        return self._done


P = TypeVar("P", bound=PlanningData)


# Note: contrary to most other classes, this one is not meant to be immutable, rather the optimization should
# update the values in every iteration
class LotsOptimizationState(Generic[P]):

    def __init__(self, current_solution: ProductionPlanning[P], current_objective_value: ObjectiveFunction,
                 best_solution: ProductionPlanning[P], best_objective_value: ObjectiveFunction,
                 num_iterations: int=0,  # deprecated
                 history: list[ObjectiveFunction]|None = None,
                 parameters: dict[str, any]|None = None):
        self.current_solution: ProductionPlanning[P] = current_solution
        self.current_object_value: ObjectiveFunction = current_objective_value
        self.best_solution: ProductionPlanning[P] = best_solution
        self.best_objective_value: ObjectiveFunction = best_objective_value
        self.num_iterations: int = num_iterations
        "deprecated"
        self.history: list[ObjectiveFunction] = list(history) if history is not None else [current_objective_value]
        self.parameters: dict[str, any]|None = parameters


class LotsOptimizer(Generic[P]):
    """
    Stateful optimization, remembers current best solution
    """

    def __init__(self, site: Site, process: str, costs: CostProvider, snapshot: Snapshot, targets: ProductionTargets,
                 # Note: we should accept None for the initial solution, for instances only used to assign lots
                 initial_solution: ProductionPlanning[P], min_due_date: datetime|None = None,
                 # the next two are for initialization from a previous optimization run
                 best_solution: ProductionPlanning[P]|None = None,
                 history: list[ObjectiveFunction] | None = None,
                 parameters: dict[str, any]|None = None,
                 performance_models: list[PlantPerformanceModel]|None = None
                 ):
        self._listeners: list[OptimizationListener] = []
        self._site: Site = site
        self._process: str = process
        self._snapshot = snapshot
        self._costs: CostProvider = costs
        self._targets = targets
        self._min_due_date: datetime|None = min_due_date
        main_cat = ModelUtils.main_category_for_targets(targets.material_weights, site.material_categories)
        self._main_category = main_cat.id if main_cat is not None else None
        self._performance_models = [pm for pm in performance_models if process in pm.applicable_processes_and_plants()[0]] if performance_models is not None else None
        target_plants: list[int] = list(targets.target_weight.keys())
        assigned_plants: set[int] = set(ass.equipment for ass in initial_solution.order_assignments.values()) \
            if initial_solution is not None else set()
        status_plants = list(initial_solution.equipment_status.keys()) if initial_solution is not None else []
        zombie_plant_assigned: int|None = next((p for p in assigned_plants if p not in target_plants and p >= 0), None)
        if zombie_plant_assigned is not None:
            raise Exception("Plant " + str(zombie_plant_assigned) + " has been assigned an order but has no defined target value")
        zombie_plant_status = next((p for p in status_plants if p not in target_plants), None)
        if zombie_plant_status is not None:
            raise Exception("Plant " + str(zombie_plant_status) + " has a status but no defined target value")
        self._plants: list[Equipment] = [site.get_equipment(p, do_raise=True) for p in target_plants]
        self._plant_ids: list[int] = target_plants
        invalid_plant = next((plant for plant in self._plants if plant.process != process), None)
        if invalid_plant is not None:
            raise Exception("Configured plant " + str(invalid_plant.name_short if invalid_plant.name_short is not None else invalid_plant.id)  \
                            + " belongs to process " + str(invalid_plant.process) + ", not " + process)
        self._orders: dict[str, Order]|None = None
        if initial_solution is not None:
            self._orders = {o: snapshot.get_order(o) for o in initial_solution.order_assignments.keys()}
        initial_costs = costs.process_objective_function(initial_solution) if initial_solution is not None else None
        best_costs = initial_costs if best_solution is None else costs.process_objective_function(best_solution)
        best_solution = initial_solution if best_solution is None else best_solution
        initial_costs_value = initial_costs.total_value if initial_costs is not None else None
        best_costs_value = best_costs
        history = [initial_costs] if history is None and initial_costs is not None else history if history is not None else []
        # state
        self._state: LotsOptimizationState[P] = LotsOptimizationState(current_solution=initial_solution, best_solution=best_solution,
                                        current_objective_value=initial_costs, best_objective_value=best_costs_value, history=history, parameters=parameters)

    def parameters(self) -> dict[str, any]|None:
        return self._state.parameters

    # side effects on state
    def run(self, max_iterations: int|None = None, debug: bool=False) -> LotsOptimizationState[P]:
        raise Exception("Not implemented")

    def state(self) -> LotsOptimizationState[P]:
        return self._state

    def assign_lots(self, order_plant_assignments: dict[str, int]) -> dict[int, list[Lot]]:
        raise Exception("Not implemented")

    def update_transition_costs(self, plant: Equipment, current: Order, next: Order, status: EquipmentStatus, snapshot: Snapshot,
                                current_material: Material | None = None, next_material: Material | None = None) -> tuple[EquipmentStatus, ObjectiveFunction]:
        """
        Note: this is intended to forward to the cost service, the lot optimizer only needs to determine whether this
        leads to a new lot or not
        """
        raise Exception("not implemented")

    def add_listener(self, listener: OptimizationListener):
        if listener not in self._listeners:
            self._listeners.append(listener)

    def remove_listener(self, listener: OptimizationListener):
        self._listeners.remove(listener)


class LotsOptimizationAlgo:
    """
    Implementation expected in module dynreact.lotscreation.LotsOptimizerImpl
    """

    def __init__(self, site: Site):
        self._site = site

    # TODO clarify: should we consider the planning horizon here? => would need some information about planned lot execution time
    def snapshot_solution(self, process: str, snapshot: Snapshot, planning_horizon: timedelta, costs: CostProvider,
                                targets: ProductionTargets|None = None,
                                orders: list[str] | None = None,
                                include_inactive_lots: bool=False) -> tuple[ProductionPlanning, ProductionTargets]:
        assignments: dict[str, OrderAssignment] = {}
        target_weights_by_plant: dict[int, float] = {}
        order_objs = snapshot.orders
        for plant_id, lots in snapshot.lots.items():
            plant = next((p for p in self._site.equipment if p.id == plant_id), None)
            if plant is None or plant.process != process or (targets is not None and plant.id not in targets.target_weight):
                continue
            weight_sum: float = 0.
            for lot in lots:
                if not lot.active and not include_inactive_lots:
                    continue
                for lot_idx, order_id in enumerate(lot.orders):
                    if orders is not None and order_id not in orders:
                        continue
                    assignments[order_id] = OrderAssignment(equipment=plant_id, order=order_id, lot=lot.id, lot_idx=lot_idx + 1)
                    order = next((o for o in order_objs if o.id == order_id), None)
                    if order is not None:
                        weight_sum += order.actual_weight
            target_weights_by_plant[plant_id] = weight_sum
        if orders is not None:
            unassigned: Sequence[str] = (order for order in orders if order not in assignments)
            assignments.update({order: OrderAssignment(order=order, equipment=-1, lot="", lot_idx=-1) for order in unassigned})
        targets: ProductionTargets = targets if targets is not None else \
            ProductionTargets(process=process, target_weight={p: EquipmentProduction(equipment=p, total_weight=weight) for p, weight in target_weights_by_plant.items()},
                              period=(snapshot.timestamp, snapshot.timestamp + planning_horizon))
        planning = costs.evaluate_order_assignments(process, assignments, targets=targets, snapshot=snapshot) if costs is not None else None
        return planning, targets

    def _random_start_orders(self, plants: dict[int, Equipment], targets: ProductionTargets, orders: dict[str, Order],
                             snapshot_provider: SnapshotProvider, start_orders: dict[int, str]|None) -> dict[int, str]:
        start_orders = start_orders or {}
        if targets.material_weights is not None:
            # try to assign start orders corresponding to different targeted material classes
            cats = self._site.material_categories
            total_targets_by_cat = {cat.id: sum(targets.material_weights[cl.id] for cl in cat.classes if cl.id in targets.material_weights
                                                and isinstance(targets.material_weights[cl.id], (int, float))) for cat in cats}
            class_by_order: dict[str, dict[str, MaterialClass]] = {oid: {cat.id: snapshot_provider.material_class_for_order(o, cat) for cat in cats} for oid, o in orders.items()}
            start_orders_by_class: dict[str, Order] = {}  # key: class id, target order id
            for cat in cats:
                if total_targets_by_cat[cat.id] == 0:
                    continue
                relevant_classes = [cl for cl in cat.classes if cl.id in targets.material_weights and isinstance(targets.material_weights[cl.id], (int, float)) and
                                                targets.material_weights[cl.id] >= total_targets_by_cat[cat.id]/4]
                if len(relevant_classes) == 0:
                    continue
                for clazz in relevant_classes:
                    if clazz.id in start_orders_by_class:
                        continue
                    some_order = next((o for o, cat_dict in class_by_order.items() if cat_dict.get(cat.id) == clazz and orders.get(o) not in start_orders_by_class.values()), None)
                    if some_order is not None:
                        start_orders_by_class[clazz.id] = orders.get(some_order)
                        for cat2 in cats:
                            if cat == cat2:
                                continue
                            other_class = class_by_order[some_order].get(cat2.id)
                            if other_class is not None and other_class.id not in start_orders_by_class:
                                start_orders_by_class[other_class.id] = orders.get(some_order)
            # sort start orders by available equipment
            start_orders_by_class = dict(sorted(start_orders_by_class.items(), key=lambda t: len([p for p in t[1].allowed_equipment if p in plants and p not in start_orders])))
            for o in start_orders_by_class.values():
                plants1 = sorted([p for p in o.allowed_equipment if p in plants and p not in start_orders], key=lambda p: targets.target_weight.get(p).total_weight, reverse=True)
                if len(plants1) > 0:
                    if o.id not in start_orders.values():
                        start_orders[plants1[0]] = o.id
        plants2 = [p for p in plants.keys() if p not in start_orders]
        for p in plants2:
            random_order: Order | None = next((o for o in orders.values() if p in o.allowed_equipment), None)
            if random_order is not None:
                start_orders[p] = random_order.id
        return start_orders

    def heuristic_solution(self, process: str, snapshot: Snapshot, planning_horizon: timedelta, costs: CostProvider, snapshot_provider: SnapshotProvider,
                           targets: ProductionTargets, orders: list[str], start_orders: dict[int, str]|None=None) -> tuple[ProductionPlanning, ProductionTargets]:
        """
        If orders is not specified, this method will only consider as many orders for scheduling as are required to
        fulfill the targets per plant. Otherwise unassigned orders may occur.
        :param process:
        :param snapshot:
        :param planning_horizon:
        :param costs:
        :param targets:
        :param orders:
        :param start_orders: keys: plant id, values: order
        :return:
        """
        # We remove orders from this dict as they are assigned to plants
        order_objects: dict[str, Order] = {order.id: order for order in snapshot.orders if order.id in orders}
        # for faster access, remember assigned orders
        orders_done: dict[str, Order] = {}
        # We remove plants from this list as soon as there are no more orders available for them (by checking available_tons_per_plant[plant] > 0)
        plants: dict[int, Equipment] = {p.id: p for p in self._site.get_process_equipment(process) if p.id in targets.target_weight}
        #assignments: dict[str, int] = {}
        assignments_by_plant: dict[int, list[str]] = {p: [] for p in plants.keys()}
        plant_weights: dict[int, float] = {}
        if start_orders is None:
            start_orders = {}
        # Here we keep track of available tons (from as yet unassigned orders) per plant
        available_tons_by_plant: dict[int, float] = {p: 0 for p in plants.keys()}
        # here we keep track of how many tons are still missing per plant
        missing_tons_by_plant: dict[int, float] = {p: targets.target_weight[p].total_weight for p in plants.keys()}
        for order in order_objects.values():
            orders_plants = [p for p in plants.keys() if p in order.allowed_equipment]
            for p in orders_plants:
                available_tons_by_plant[p] += order.actual_weight
                # TODO better initialization algo?

        def assign_to_plant(o: Order, plant: int):
            assignments_by_plant[plant].append(o.id)
            order_objects.pop(o.id)
            orders_done[o.id] = o
            missing_tons_by_plant[plant] = missing_tons_by_plant[plant] - o.actual_weight
            for other_plant in o.allowed_equipment:
                if other_plant in available_tons_by_plant:
                    available_tons_by_plant[other_plant] = available_tons_by_plant[other_plant] - o.actual_weight

        start_orders = self._random_start_orders(plants, targets, order_objects, snapshot_provider, start_orders)
        for plant in [plant for plant in plants.keys() if plant not in start_orders]:
            plants.pop(plant)
        for plant, order_id in start_orders.items():
            assign_to_plant(order_objects[order_id], plant)

        # The main loop
        while len(plants) > 0 and len(order_objects) > 0:
            diff_by_plant: dict[int, float] = {p: available_tons_by_plant[p] - missing_tons_by_plant[p] for p in plants.keys()}
            plant: int = min(diff_by_plant, key=diff_by_plant.get) # the plant most in need of more orders
            if available_tons_by_plant[plant] < 0.00001:
                plants.pop(plant)
                continue
            plant_obj: Equipment = plants[plant]
            current_order: str = assignments_by_plant[plant][-1] if len(assignments_by_plant[plant]) > 0 else start_orders[plant]
            current_order_obj: Order = orders_done[current_order] if current_order in orders_done else snapshot.get_order(current_order, do_raise=True)
            # applicable_orders = {oid: order for oid, order in order_objects.items() if plant in order.allowed_plants}
            transition_costs: dict[str, float] = \
                {oid: costs.transition_costs(plant_obj, current_order_obj, order) for oid, order in order_objects.items() if plant in order.allowed_equipment}
            applicable_orders_cnt: int = len(transition_costs)
            transition_costs: dict[str, float] = {oid: cost for oid, cost in transition_costs.items() if np.isfinite(cost)}
            if len(transition_costs) == 0:  # ideally this should not happen
                if applicable_orders_cnt > 0:
                    print("No valid transition to a new order found for plant", plant.id, "out of", applicable_orders_cnt, "applicable orders")
                plants.pop(plant)
                continue
            lowest_transition_order: str = min(transition_costs, key=transition_costs.get)
            assign_to_plant(order_objects[lowest_transition_order], plant)
            if missing_tons_by_plant[plant] < 0.01:  # TODO configurable threshold
                plants.pop(plant)
        # keys: orders, values: plants
        assignments: dict[str, int] = {order: plant for plant, orders in assignments_by_plant.items() for order in orders}

        instance = self._create_instance_internal(process, snapshot, targets, costs, None)
        plant_lots: dict[int, list[Lot]] = instance.assign_lots(assignments)
        order_assignments: dict[str, OrderAssignment] = {}
        for order, plant in assignments.items():
            if plant not in plant_lots:
                continue
            lots = plant_lots[plant]
            lot: Lot | None = next((lot for lot in lots if order in lot.orders), None)
            if lot is None:
                continue
            order_assignments[order] = OrderAssignment(order=order, equipment=plant, lot=lot.id,
                                                       lot_idx=lot.orders.index(order) + 1)
        if orders is not None:
            unassigned: Sequence[str] = (order for order in orders if order not in assignments)
            order_assignments.update(
                {order: OrderAssignment(order=order, equipment=-1, lot="", lot_idx=-1) for order in unassigned})
        planning = costs.evaluate_order_assignments(process, order_assignments, targets=targets, snapshot=snapshot)
        return planning, targets


    def due_dates_solution(self, process: str, snapshot: Snapshot, planning_horizon: timedelta, costs: CostProvider,
                           targets: ProductionTargets|None = None, orders: list[str] | None = None,
                           include_inactive_lots: bool=False) -> tuple[ProductionPlanning, ProductionTargets]:
        """
        If orders is not specified, this method will only consider as many orders for scheduling as are required to
        fulfill the targets per plant. Otherwise unassigned orders may occur.
        :param process:
        :param snapshot:
        :param planning_horizon:
        :param costs:
        :param targets:
        :param orders:
        :return:
        """
        if targets is None:  # TODO long term planning targets?
            _, targets = self.snapshot_solution(process, snapshot, planning_horizon, None, include_inactive_lots=include_inactive_lots)
        orders_sorted: list[Order] = sorted([o for o in snapshot.orders if o.due_date is not None and
                                             (orders is None or o.id in orders)], key=lambda order: order.due_date)
        #assignments: dict[str, OrderAssignment] = {}
        assignments: dict[str, int] = {}
        plant_weights: dict[int, float] = {}
        plants: list[int] = [p.id for p in self._site.get_process_equipment(process) if p.id in targets.target_weight]
        for order in orders_sorted:
            # TODO filter orders eligible for the current process stage => non-trivial!
            next_eligible_plant: int|None = next((p for p in order.allowed_equipment if p in plants and
                                                  (p not in plant_weights or (p in targets.target_weight and plant_weights[p] < targets.target_weight[p].total_weight))), None)
            if next_eligible_plant is None:
                # TODO check if all plant target weights are already exhausted, then break
                continue
            if next_eligible_plant not in plant_weights:
                plant_weights[next_eligible_plant] = 0
            plant_weights[next_eligible_plant] = plant_weights[next_eligible_plant] + order.actual_weight
            assignments[order.id] = next_eligible_plant # OrderAssignment(order=order.id, plant=next_eligible_plant, lot=..., lot_idx=...)
        instance = self._create_instance_internal(process, snapshot, targets, costs, None)
        plant_lots: dict[int, list[Lot]] = instance.assign_lots(assignments)
        order_assignments: dict[str, OrderAssignment] = {}
        for order, plant in assignments.items():
            if plant not in plant_lots:
                continue
            lots = plant_lots[plant]
            lot: Lot|None = next((lot for lot in lots if order in lot.orders), None)
            if lot is None:
                continue
            order_assignments[order] = OrderAssignment(order=order, equipment=plant, lot=lot.id, lot_idx=lot.orders.index(order)+1)
        if orders is not None:
            unassigned: Sequence[str] = (order for order in orders if order not in assignments)
            order_assignments.update({order: OrderAssignment(order=order, equipment=-1, lot="", lot_idx=-1) for order in unassigned})
        planning = costs.evaluate_order_assignments(process, order_assignments, targets=targets, snapshot=snapshot)
        return planning, targets

    def create_instance(self, process: str, snapshot: Snapshot, cost_provider: CostProvider,
                        targets: ProductionTargets | None = None, initial_solution: ProductionPlanning | None = None,
                        min_due_date: datetime|None = None,
                        # optionally, specify the orders to be planned explicitly
                        # TODO option to specify the urgency(?)
                        orders: list[str]|None = None,
                        # the next two are for initialization from a previous optimization run
                        best_solution: ProductionPlanning[P] | None = None,
                        history: list[ObjectiveFunction] | None = None,
                        performance_models: list[PlantPerformanceModel] | None = None,
                        parameters: dict[str, any] | None = None,
                        include_inactive_lots: bool = False
                        ) -> LotsOptimizer:
        if initial_solution is None or targets is None:
            planning_horizon = targets.period[1] - targets.period[0] if targets is not None else timedelta(hours=8)  # XXX?
            initial_solution0, targets0 = self.snapshot_solution(process, snapshot, planning_horizon, cost_provider, targets=targets,
                                                                 orders=orders, include_inactive_lots=include_inactive_lots)
            if initial_solution is None:
                initial_solution = initial_solution0
            if targets is None:
                targets = targets0
        return self._create_instance_internal(process, snapshot, targets, cost_provider, initial_solution, min_due_date=min_due_date,
                                              best_solution=best_solution, history=history, parameters=parameters, performance_models=performance_models)

    def _create_instance_internal(self, process: str, snapshot: Snapshot, targets: ProductionTargets,
                                  cost_provider: CostProvider, initial_solution: ProductionPlanning, min_due_date: datetime|None = None,
                                  # the next two are for initialization from a previous optimization run
                                  best_solution: ProductionPlanning[P] | None = None, history: list[ObjectiveFunction] | None = None,
                                  performance_models: list[PlantPerformanceModel] | None = None,
                                  parameters: dict[str, any] | None = None
                                  ) -> LotsOptimizer:
        raise Exception("not implemented")
