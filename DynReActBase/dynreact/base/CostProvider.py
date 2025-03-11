"""
The CostProvider module defines the CostProvider class, which should be thought of as an
interface that must be implemented for each specific scheduling use-case. It contains all
the custom logic for building an objective function for schedules.
"""

from datetime import datetime

from dynreact.base.model import Equipment, Order, Material, Snapshot, EquipmentStatus, Site, ProductionPlanning, OrderAssignment, \
    ProductionTargets, EquipmentProduction, ObjectiveFunction


class CostProvider:
    """
    An interface that must be implemented for each specific scheduling use-case. It contains all
    the custom logic for building an objective function for schedules.
    Implementation expected in package dynreact.cost.CostCalculatorImpl
    """

    def __init__(self,  url: str|None, site: Site):
        self._url = url
        self._site = site

    def transition_costs(self, plant: Equipment, current: Order, next: Order, current_material: Material | None = None, next_material: Material | None = None) -> float:
        """
        Calculates the transition costs for two orders at a given plant. If materials are specified,
        then the transition costs between individual materials are evaluated instead.
        This function does not take into account global constraints and objectives.
        """
        raise Exception("not implemented")

    def logistic_costs(self, new_equipment: Equipment, order: Order, material: Material | None = None) -> float:
        """
        Calculates the transition costs for an order or individual material from an order to be transported to a new
        equipment.
        """
        return 0

    def evaluate_order_assignments(self, process: str, assignments: dict[str, OrderAssignment], targets: ProductionTargets, snapshot: Snapshot) -> ProductionPlanning:
        """
        :param process:
        :param assignments:
        :return:
        """
        #plants = [p for p in self._site.plants if p.process == process]
        plant_ids = list(targets.target_weight.keys())
        plants = [p for p in self._site.equipment if p.process == process and p.id in plant_ids]

        status: dict[int, EquipmentStatus] = \
            {plant.id: self.evaluate_equipment_assignments(targets.target_weight.get(plant.id, EquipmentProduction(equipment=plant.id, total_weight=0.0)),
                                                process, assignments, snapshot, targets.period) for plant in plants}
        order_assignments = {o: ass for o, ass in assignments.items() if ass.equipment in plant_ids}
        unassigned = {o: ass for o, ass in assignments.items() if ass.equipment < 0}
        order_assignments.update(unassigned)
        return ProductionPlanning(process=process, order_assignments=order_assignments, equipment_status=status)

    def evaluate_equipment_assignments(self, equipment_targets: EquipmentProduction, process: str, assignments: dict[str, OrderAssignment], snapshot: Snapshot,
                                       planning_period: tuple[datetime, datetime], min_due_date: datetime|None=None,
                                       current_material: list[Material] | None=None) -> EquipmentStatus:
        """
        Main function to be implemented in derived class taking into account global status.
        Note that this must set the PlantStatus.planning.target_fct value.
        :param equipment:
        :param assignments: order assignments; keys: order ids
        :param target_weight:
        :param snapshot:
        :param: current_coils: should only be present if the last order is not assumed to be processed entirely
        :return:
        """
        raise Exception("Not implemented")

    # TODO this is meant to be an incremental version of the evaluate_order_assignment method above
    #def transition_costs_stateful(self, plant: Plant, current: Order, next: Order, status: PlantStatus, current_coil: Coil|None = None, next_coil: Coil|None = None) -> tuple[PlantStatus, float]:
    #    """
    #    Calculates the change in the global target function. Needs the current status as input, and delivers the new status as output, alongside the
    #    value of the target function. Typically, the resulting costs will include the stateless transition costs plus
    #    additional global costs.
    #    """
    #    raise Exception("not implemented")

    def update_transition_costs(self, plant: Equipment, current: Order, next: Order, status: EquipmentStatus, snapshot: Snapshot,
                                new_lot: bool, current_material: Material | None = None, next_material: Material | None = None) -> tuple[EquipmentStatus, ObjectiveFunction]:
        """
        Intended to be called by the lot creation, which first needs to check whether a new lot has to be created
        """
        raise Exception("not implemented")

    def objective_function(self, status: EquipmentStatus) -> ObjectiveFunction:
        "Evaluate the target/objective function for a specific plant status"
        raise Exception("not implemented")

    def process_objective_function(self, planning: ProductionPlanning) -> ObjectiveFunction:
        """
        Evaluate the objective function for one process. By default, this is the sum of all objective functions
        evaluated on the individual plants, but it is possible to override this behaviour in a derived implementation
        """
        process = planning.process
        all_plants: dict[int, Equipment] = {p.id: p for p in self._site.equipment}
        process_plants: list[EquipmentStatus] \
            = [status for status in planning.equipment_status.values() if status.targets.equipment in all_plants and all_plants[status.targets.equipment].process == process]
        objectives: list[ObjectiveFunction] = [self.objective_function(s) for s in process_plants]
        return CostProvider.sum_objectives(objectives)

    def optimum_possible_costs(self, process: str, num_plants: int):
        return 0

    def relevant_fields(self, equipment: Equipment) -> None|list[str]:
        """
        Optional method, for display purposes only. To be overridden in derived class.
        Convention: "order.material_properties.<$FIELD_NAME>", "material.properties.<$FIELD_NAME>"
        :param equipment:
        :return:
        """
        return None

    def equipment_status(self, snapshot: Snapshot, plant: Equipment, planning_period: tuple[datetime, datetime], target_weight: float,
                         coil_based: bool = False,
                         current: Order|None=None, previous: Order|None=None,
                         current_material: list[Material] | None = None) -> EquipmentStatus:
        """
        :param snapshot:
        :param plant:
        :param planning_period  TODO validate that planning_period starts with current snapshot?
        :param target_weight
        :param coil_based: treat coils as basic unit or orders (default)?
        :param current: current order; by default this will be determined from the snapshot, but it can also be provided explicitly
        :param previous: previous order;  by default this will be determined from the snapshot (if this information is available), but it can also be provided explicitly
        :param: current_coils: should only be present if the last order is not assumed to be processed entirely
        :return:
        """
        process = self._site.get_process(plant.process, do_raise=True).name_short
        if current is None and current_material is not None and len(current_material) > 0:
            current = snapshot.get_order(current_material[-1].order, do_raise=True)
        if current is None or (coil_based and current_material is None):
            inline_coils = snapshot.inline_material.get(plant.id)
            if inline_coils is not None and len(inline_coils) > 0:
                if current is not None and current.id != inline_coils[-1].order:
                    raise Exception("Specified current order does not match current coils' order")
                current = snapshot.get_order(inline_coils[-1].order, do_raise=True)
                current_material = [snapshot.get_material(ocd.material, do_raise=True) for ocd in inline_coils]
            else:
                current_material = []
        if coil_based and current_material is None:
            raise Exception("Could not determine current coils")
        assignments: dict[str, OrderAssignment] = {}
        if previous is not None:
            prev_lot = previous.lots.get(process) if previous.lots is not None else None
            prev_lot_idx = previous.lot_positions.get(process) if prev_lot is not None else None
            assignments[previous.id] = OrderAssignment(equipment=plant.id, order=previous.id, lot=prev_lot if prev_lot is not None else plant.name_short + "_X",
                                                      lot_idx=prev_lot_idx if prev_lot_idx is not None else 1)
        if current is not None:
            curr_lot = current.lots.get(process) if current.lots is not None else None
            curr_lot_idx = current.lot_positions.get(process) if curr_lot is not None else None
            assignments[current.id] = OrderAssignment(equipment=plant.id, order=current.id, lot=curr_lot if curr_lot is not None else plant.name_short + "_X",
                                                      lot_idx=curr_lot_idx if curr_lot_idx is not None else 1)
        return self.evaluate_equipment_assignments(EquipmentProduction(equipment=plant.id, total_weight=target_weight),
                                        plant.process, assignments, snapshot, planning_period, current_material=current_material if coil_based else None)

    @staticmethod
    def sum_objectives(objective_functions:list[ObjectiveFunction]) -> ObjectiveFunction:
        all_fields: set[str] = {field for obj in objective_functions for field in obj.model_fields_set}
        field_values = {field: sum(getattr(o, field) or 0 if hasattr(o, field) else 0 for o in objective_functions) for field in all_fields}
        if "total_value" not in field_values:
            field_values["total_value"] = 0
        result = ObjectiveFunction(**field_values)
        return result
