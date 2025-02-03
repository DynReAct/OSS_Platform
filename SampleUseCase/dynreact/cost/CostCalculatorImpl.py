from datetime import datetime

import numpy as np

from dynreact.base.CostProvider import CostProvider
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.model import Equipment, Material, Order, Snapshot, EquipmentStatus, Site, OrderAssignment, PlanningData
from dynreact.cost.CostConfig import CostConfig
from dynreact.sample.model import SampleMaterial


class SampleCostProvider(CostProvider):

    def __init__(self, url: str|None, site: Site, config: CostConfig|None = None):
        super().__init__(url, site)
        if url is not None and not url.startswith("sampleuc:"):
            raise NotApplicableException("Unexpected URI for sample use case cost provider: " + str(url))
        self._plant_ids: list[int] = [p.id for p in site.equipment]
        self._config = config if config is not None else CostConfig()

    def transition_costs(self, plant: Equipment, current: Order[SampleMaterial], next: [SampleMaterial], current_material: Material | None = None, next_material: Material | None = None) -> float:
        process: str = plant.process
        if current is None or next is None or current == next:
            return 0
        material1: SampleMaterial = current.material_properties
        material2: SampleMaterial = next.material_properties
        if isinstance(material1, dict):
            material1 = SampleMaterial.model_validate(material1)
        if isinstance(material2, dict):
            material2 = SampleMaterial.model_validate(material2)
        # We create a new lot whenever costs exceed the threshold of 4
        costs = 1
        if process == "PKL":    # pickling
            width_diff: float = abs(material1.width - material2.width)
            # In our example, costs at the pickling line depend on the width difference between coils
            # a width difference > 9mm will force a new lot, since it raises the costs above the threshold of 4
            costs += width_diff * 0.3
        elif process == "CRL":  # cold rolling
            # In our example, costs at the cold rolling line depend on the thickness difference between coils
            thickness_initial_diff: float = abs(material1.thickness_initial - material2.thickness_initial)
            costs += thickness_initial_diff * 2
            thickness_final_diff: float = abs(material1.thickness_final - material2.thickness_final)
            costs += thickness_initial_diff * 10
            # in addition, width should only decrease within one production lot
            if material2.width > material1.width:
                costs += (material2.width - material1.width) * 3
        elif process == "FIN":  # finishing
            width_diff: float = abs(material1.width - material2.width)
            costs += width_diff * 0.1  # cost component 1: width difference
            # Here we have some plant-specific costs, in addition
            if plant.name_short == "FIN01":
                # finishing line 1 should always start with material of type "ftype1", if any, and then proceed with "ftype2"
                if material1.finishing_type == "ftype2" and material2.finishing_type == "ftype1":
                    costs += 10
            elif plant.name_short == "FIN02":
                # line 2 can only produce material of a single type within one production lot
                if material1.finishing_type != material2.finishing_type:
                    costs += 10
        else:
            raise ValueError(f"Unknown process {process}")
        return costs

    # This cannot be determined by the cost service only, because it requires the re-calculation of lots
    def update_transition_costs(self, plant: Equipment, current: Order, next: Order, status: EquipmentStatus, snapshot: Snapshot, new_lot: bool,
                                current_material: Material | None = None, next_material: Material | None = None) -> tuple[EquipmentStatus, float]:
        """
        Calculate an incremental update to the cost function
        """
        if plant.id != status.equipment:
            raise Exception("Plant status for plant id " + str(status.equipment) + " instead of expected " + str(plant.id))
        if status.current_order != current.id:
            raise Exception("Current order id in status object does not match provided order (" + str(status.current) + " - " + str(current.id) + ")")
        if status.snapshot_id != snapshot.timestamp:
            raise Exception("Snapshot ids do not match (expected " + str(snapshot.timestamp) + ", received: " + str(status.snapshot_id) + ")")
        old_planning: PlanningData = status.planning
        if current.id == next.id:
            return status, self.objective_function(status)
        new_weight = next.actual_weight if next_material is None else next_material.weight
        delta_weight = old_planning.delta_weight - new_weight
        min_due_date = old_planning.min_due_date  # ?
        lots_cnt = old_planning.lots_count + 1 if new_lot else old_planning.lots_count
        orders_cnt = old_planning.orders_count + 1
        lot_weights = None
        if new_lot:
            lot_weights = old_planning.lot_weights + [new_weight]
        else:
            lot_weights = list(old_planning.lot_weights)
            lot_weights[-1] += new_weight
        transition_costs = old_planning.transition_costs + self.transition_costs(plant, current, next, current_material=current_material, next_material=next_material)
        # Note: if there were other cost components, we could use a custom sub-class of PlanningData
        new_planning: PlanningData = PlanningData(delta_weight=delta_weight, min_due_date=min_due_date,
                                                                lots_count=lots_cnt, lot_weights=lot_weights,
                                                                orders_count=orders_cnt, transition_costs=transition_costs)
        current_coils = [next_material.id] if next_material is not None else []  # here we have a new order, so no need to track previous coils
        new_status = EquipmentStatus(equipment=plant.id, snapshot_id=status.snapshot_id, target_weight=status.target_weight,
                                     planning=new_planning,
                                     planning_period=status.planning_period,
                                     current_order=next.id, previous_order=current.id,
                                     current_material=current_coils)
        target_fct = self.objective_function(new_status)
        new_planning.target_fct = target_fct
        return new_status, target_fct

    def objective_function(self, status: EquipmentStatus[PlanningData]) -> float:
        """
        Evaluate the target/objective function for a specific plant status
        """
        if status is None or status.equipment not in self._plant_ids:  # TODO generate a warning?
            return float("inf")
        params: CostConfig = self._config
        planning: PlanningData = status.planning
        # In our example there are 3 costs components: number of lots, deviation from target weight, and transition costs between individual orders
        # The relative weight of the components can be defined by the parameters
        weight_deviation = (abs(planning.delta_weight) / status.target_weight) ** 2 if status.target_weight > 0 else 0
        return planning.lots_count + \
            params.factor_weight_deviation * weight_deviation + \
            params.factor_transition_costs * planning.transition_costs

    def evaluate_equipment_assignments(self, plant_id: id, process: str, assignments: dict[str, OrderAssignment], snapshot: Snapshot,
                                       planning_period: tuple[datetime, datetime], target_weight: float, min_due_date: datetime|None=None,
                                       current_material: list[Material] | None=None) -> EquipmentStatus:
        plant = next((p for p in self._site.equipment if p.id == plant_id), None)
        if plant is None:
            raise Exception(f"Plant not found: {plant_id}")
        assignments = {order: assignment for order, assignment in assignments.items() if assignment.equipment == plant_id}
        if len(assignments) == 0:
            if current_material is not None and len(current_material) > 0:
                raise Exception("Current coils specified " + str([c.id for c in current_material]) + ", but no order assignments")
            status = EquipmentStatus(equipment=plant_id, snapshot_id=snapshot.timestamp, target_weight=target_weight,
                                     planning_period=planning_period,
                                     planning=PlanningData(delta_weight=target_weight),
                                     current_material=[] if current_material is not None else None)
            target_fct = self.objective_function(status)
            status.planning.target_fct = target_fct
            return status
        orders: dict[str, Order | None] = {order_id: next((o for o in snapshot.orders if o.id == order_id), None) for
                                           order_id in assignments.keys()}
        none_orders = [order_id for order_id, order in orders.items() if order is None]
        if len(none_orders) > 0:
            raise Exception("Orders not found " + str(none_orders))
        sz: int = len(orders)
        # min_due_date: datetime|None = None if next((o for o in orders.values() if o.due_date is not None), None) is None \
        #    else min(o.due_date for o in orders.values() if o.due_date is not None)
        # orders sorted by lot if and lot idx
        lots: dict[int, dict[int, Order]] = {}
        for order_id, ass in assignments.items():
            if ass.lot not in lots:
                lots[ass.lot] = {}
            lots[ass.lot][ass.lot_idx] = orders[order_id]
        lots = SampleCostProvider._sort_dict({lot_id: SampleCostProvider._sort_dict(orders) for lot_id, orders in lots.items()})
        lot_weights = {lot_id: sum(order.actual_weight for order in lot.values()) for lot_id, lot in lots.items()}
        # TODO validate correct ordering
        orders_sorted = [order for lot in lots.values() for order in lot.values()]
        transition_costs: float = sum(c if not np.isnan(c) else 50 for c in   # TODO configurable?
                                (self.transition_costs(plant, orders_sorted[idx], orders_sorted[idx + 1]) for idx in range(sz - 1)))
        # TODO initial state: if sz > 0 and sT0 is not None: cclottot += sT0[spath[0]]
        coil_based_calc: bool = current_material is not None
        weight_orders = orders_sorted if not coil_based_calc else orders_sorted[:-1]
        total_weight = sum(o.actual_weight for o in weight_orders)
        if coil_based_calc:
            total_weight += sum(c.weight for c in current_material)
        delta_weight = abs(target_weight - total_weight)
        last_order = orders_sorted[-1]
        previous_order = orders_sorted[-2] if len(orders_sorted) > 1 else None
        # TODO in function
        planning: PlanningData = PlanningData(delta_weight=delta_weight, min_due_date=min_due_date,
                                                            lots_count=len(lots), lot_weights=list(lot_weights.values()),
                                                            orders_count=len(orders_sorted),
                                                            transition_costs=transition_costs)
        status = EquipmentStatus(equipment=plant_id, snapshot_id=snapshot.timestamp, target_weight=target_weight,
                                 #lot_weight_range=[22.0, 33.0],    #FIXME
                                 planning=planning,
                                 planning_period=planning_period, current_order=last_order.id,  # current=last_order.id
                                 previous_order=previous_order.id if previous_order is not None else None,
                                 current_material=[c.id for c in current_material] if current_material is not None else None)
        # previous=previous_order.id if previous_order is not None else None)
        target_fct = self.objective_function(status)
        planning.target_fct = target_fct
        return status

    @staticmethod
    def _sort_dict(dictionary: dict[any, any]) -> dict[any, any]:
        keys_sorted = sorted(key for key in dictionary.keys())
        return {key: dictionary[key] for key in keys_sorted}

    def optimum_possible_costs(self, process: str, num_plants: int):
        return num_plants

