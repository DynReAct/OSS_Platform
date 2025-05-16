from copy import deepcopy
from datetime import datetime

from dynreact.base.CostProvider import CostProvider
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.model import Site, Equipment, Order, Material, EquipmentStatus, Snapshot, OrderAssignment, \
    PlanningData, EquipmentProduction, ObjectiveFunction


class SimpleCostProvider(CostProvider):
    """
    A simple cost calculation function that takes into account transition costs between orders
    (configurable via a dictionary passed to the constructor), the number of lots, and weight deviations from
    the target.

    Note: instead of providing the transition costs in the constructor, it is also possible to create a subclass
    that overrides the *transition_costs* method.
    """

    def __init__(self, url: str|None, site: Site,
                 # Keys (inner and outer): order ids, values: costs
                 transition_costs: dict[str, dict[str, float]] = {},
                 new_lot_costs: float = 3,
                 missing_weight_costs: float = 1,  # per t
                 surplus_weight_costs: float = 3,  # per t
                 minimum_possible_costs: float = 0):
        super().__init__(url, site)
        if url is not None and not url.startswith("simple:"):
            raise NotApplicableException("Unexpected URI for simple cost provider: " + str(url))
        self._transition_costs = transition_costs
        self._new_lot_costs = new_lot_costs
        self._missing_weight_costs = missing_weight_costs
        self._surplus_weight_costs = surplus_weight_costs
        self._minimum_possible_costs = minimum_possible_costs

    def transition_costs(self, plant: Equipment, current: Order | None, next: Order, current_material: Material | None = None,
                         next_material: Material | None = None) -> float:
        if current is None:
            return 0
        costs = self._transition_costs.get(current.id, {})
        return costs.get(next.id, 0)

    def _weight_deviation_costs(self, delta_weight: float) -> float:
        return delta_weight * self._missing_weight_costs if delta_weight >= 0 else -delta_weight * self._surplus_weight_costs

    def update_transition_costs(self, plant: Equipment, current: Order | None, next: Order, status: EquipmentStatus, snapshot: Snapshot,
                                new_lot: bool, current_material: Material | None = None, next_material: Material | None = None) -> tuple[EquipmentStatus, float]:
        current_id: str|None = None if current is None else current.id
        if status.current_order == "":
            status.current_order = None
        if (current is None and status.current_order is not None) or (current is not None and status.current_order != current_id):
            raise Exception("Invalid current order; expected " + str(status.current_order) + ", got " + str(current_id))
        new_status = deepcopy(status)
        costs = self.transition_costs(plant, current, next, current_material=current_material, next_material=next_material)
        new_status.planning.transition_costs += costs
        new_status.planning.target_fct += costs
        new_status.current_order = next.id
        new_status.previous = current_id
        new_order: bool = current.id != next.id
        if next_material is not None:
            if new_status.current_material is None or new_order:
                new_status.current_material = []
                if not new_order and current_material is not None:
                    new_status.current_material.append(current_material.id)
            new_status.current_material.append(next_material.id)
        if new_lot or status.planning.lots_count == 0:
            new_status.planning.lots_count += 1
            if status.planning.lots_count > 0:
                new_status.planning.target_fct += self._new_lot_costs
        if new_order:
            new_status.planning.orders_count += 1
        next_weight = next.actual_weight if next_material is None else next_material.weight
        new_delta_weight = status.planning.delta_weight - next_weight
        new_status.planning.delta_weight = new_delta_weight
        new_status.planning.target_fct = new_status.planning.target_fct - self._weight_deviation_costs(status.planning.delta_weight) \
                + self._weight_deviation_costs(new_delta_weight)
        return new_status, new_status.planning.target_fct

    def evaluate_equipment_assignments(self, equipment_targets: EquipmentProduction, process: str, assignments: dict[str, OrderAssignment], snapshot: Snapshot,
                                       planning_period: tuple[datetime, datetime], min_due_date: datetime|None=None, current_material: list[Material] | None=None, track_structure: bool=False, main_category: str|None=None) -> EquipmentStatus:
        target_weight = equipment_targets.total_weight
        equipment = equipment_targets.equipment
        num_assignments = len(assignments)
        if num_assignments <= 1:
            delta_weight = target_weight
            order_id: str|None = next(iter(assignments.keys())) if num_assignments==1 else None
            min_due_date = None
            if num_assignments == 1:
                order = snapshot.get_order(order_id, do_raise=True)
                delta_weight = delta_weight - order.actual_weight
                min_due_date = order.due_date
            target_fct = self._weight_deviation_costs(target_weight)
            return EquipmentStatus(targets=equipment_targets, snapshot_id=snapshot.timestamp, planning_period=planning_period, current_order=order_id,
                                   planning=PlanningData(target_fct=target_fct, transition_costs=0, lots_count=num_assignments, orders_count=num_assignments,
                                              delta_weight=delta_weight, min_due_date=min_due_date))
        plant_obj: Equipment = next(p for p in self._site.equipment if p.id == equipment and p.process == process)
        plant_assignments: list[OrderAssignment] = [a for a in assignments.values() if a.equipment == equipment]
        plant_assignments = sorted(plant_assignments, key=lambda a: (a.lot, a.lot_idx))  # FIXME uses deprecated lot field
        transition_costs: float = 0
        total_weight: float = 0
        previous_lot: str = ""
        num_lots: int = 0
        prev_prev_oder: Order|None = None
        previous_order: Order|None = None
        min_due_date: datetime|None = None
        for assignment in plant_assignments:
            order: Order = snapshot.get_order(assignment.order, do_raise=True)
            new_lot = assignment.lot
            if new_lot != previous_lot:
                num_lots += 1
                previous_lot = new_lot
            total_weight += order.actual_weight
            if previous_order is not None:
                transition_costs += self.transition_costs(plant_obj, previous_order, order)
            if order.due_date is not None and (min_due_date is None or order.due_date < min_due_date):
                min_due_date = order.due_date
            prev_prev_oder = previous_order
            previous_order = order
        weight_diff = target_weight - total_weight
        weight_diff_costs = self._weight_deviation_costs(weight_diff)
        total_costs = transition_costs + (num_lots-1) * self._new_lot_costs + weight_diff_costs
        return EquipmentStatus(targets=equipment_targets, snapshot_id=snapshot.timestamp, planning_period=planning_period,
                               current_order=previous_order.id if previous_order is not None else None, previous_order=prev_prev_oder.id if prev_prev_oder is not None else None,
                               planning=PlanningData(target_fct=total_costs, transition_costs=transition_costs, lots_count=num_lots, orders_count=num_assignments,
                                                     current_material=[c.id for c in current_material] if current_material is not None else None,
                                                     delta_weight=weight_diff, min_due_date=min_due_date))

    def optimum_possible_costs(self, process: str, num_plants: int):
        return self._minimum_possible_costs

    def objective_function(self, status: EquipmentStatus) -> ObjectiveFunction:
        planning: PlanningData = status.planning
        transition_costs = planning.transition_costs  # TODO parameters
        log_costs = planning.logistic_costs
        weight_deviation = 10 * abs(planning.delta_weight) / status.targets.total_weight
        result = transition_costs + log_costs + weight_deviation
        return ObjectiveFunction(total_value=result, lots_count=planning.lots_count, weight_deviation=weight_deviation,
                                 transition_costs=transition_costs, logistic_costs=log_costs)

