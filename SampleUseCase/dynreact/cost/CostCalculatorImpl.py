import os
from datetime import datetime

import dotenv
import numpy as np

from dynreact.base.CostProvider import CostProvider
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.model import Equipment, Material, Order, Snapshot, EquipmentStatus, Site, OrderAssignment, \
    PlanningData, ObjectiveFunction, EquipmentProduction
from dynreact.sample.model import SampleMaterial


class CostConfig:

    threshold_new_lot: float = 4
    "Create a new lot if transition costs between orders exceed this threshold"

    factor_weight_deviation: float = 75
    "A weight factor for the cost contribution of deviating from the target production weight"

    factor_transition_costs: float = 1
    "A weight factor for the cost contribution of transition costs between orders relative to the number of lots"

    factor_logistic_costs: float = 0.3

    factor_out_of_lot_range: float = 1
    "A weight factor for the cost contribution of lot size violations"

    def __init__(self,
                 threshold_new_lot: float|None = None,
                 factor_weight_deviation: float | None = None,
                 factor_transition_costs: float | None = None,
                 factor_out_of_lot_range: float | None = None,
                 factor_logistic_costs: float | None = None
                 ):
        dotenv.load_dotenv()
        if threshold_new_lot is None:
            threshold_new_lot = float(os.getenv("OBJECTIVE_MAX_TRANSITION_COST", CostConfig.threshold_new_lot))
        self.TAllowed = threshold_new_lot
        if factor_weight_deviation is None:
            factor_weight_deviation = float(os.getenv("OBJECTIVE_TARGET_WEIGHT", CostConfig.factor_weight_deviation))
        self.factor_weight_deviation = factor_weight_deviation
        if factor_transition_costs is None:
            factor_transition_costs = float(os.getenv("OBJECTIVE_LOT_TRANSITION_COSTS_SUM",  CostConfig.factor_transition_costs))
        self.factor_transition_costs = factor_transition_costs
        if factor_out_of_lot_range is None:
            factor_out_of_lot_range = float(os.getenv("OBJECTIVE_LOT_SIZE",  CostConfig.factor_out_of_lot_range))
        self.factor_out_of_lot_range = factor_out_of_lot_range
        if factor_logistic_costs is None:
            factor_logistic_costs = float(os.getenv("OBJECTIVE_LOGISTIC_COSTS", CostConfig.factor_logistic_costs))
        self.factor_logistic_costs = factor_logistic_costs


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
                                current_material: Material | None = None, next_material: Material | None = None) -> tuple[EquipmentStatus, ObjectiveFunction]:
        """
        Calculate an incremental update to the cost function
        """
        if plant.id != status.targets.equipment:
            raise Exception("Plant status for plant id " + str(status.targets.equipment) + " instead of expected " + str(plant.id))
        if status.current_order != current.id:
            raise Exception("Current order id in status object does not match provided order (" + str(status.current) + " - " + str(current.id) + ")")
        if status.snapshot_id != snapshot.timestamp:
            raise Exception("Snapshot ids do not match (expected " + str(snapshot.timestamp) + ", received: " + str(status.snapshot_id) + ")")
        old_planning: PlanningData = status.planning
        if current.id == next.id:
            return status, self.objective_function(status)
        is_incomplete_first_submission: bool = old_planning.lots_count == 0 and status.current_order is not None
        new_weight = next.actual_weight if next_material is None else next_material.weight
        delta_weight = old_planning.delta_weight - new_weight
        min_due_date = old_planning.min_due_date  # ?
        lots_cnt = old_planning.lots_count + 1 if new_lot else old_planning.lots_count
        old_order_cnt = old_planning.orders_count
        if old_order_cnt == 0 and status.current_order is not None:
            old_order_cnt = 1
        orders_cnt = old_order_cnt + 1
        crt_weight = current.actual_weight if current_material is None else current_material.weight
        lot_weights = None
        if new_lot:
            if is_incomplete_first_submission:  # catch initial submission with incomplete data
                delta_weight = status.targets.total_weight - crt_weight - new_weight
                lots_cnt = 2
            lot_weights = old_planning.lot_weights + [new_weight]
        else:
            lot_weights = list(old_planning.lot_weights)
            if not is_incomplete_first_submission:
                lot_weights[-1] += new_weight
            else:   # catch initial submission with incomplete data
                lot_weight = crt_weight + new_weight
                lots_cnt = 1
                delta_weight = status.targets.total_weight - lot_weight
                lot_weights = [lot_weight]
        transition_costs = old_planning.transition_costs + self.transition_costs(plant, current, next, current_material=current_material, next_material=next_material)
        logistic_costs = old_planning.logistic_costs + self._logistic_costs_for_order(next, plant.id)  # TODO differentiate between order and material based updates(?)
        # Note: if there were other cost components, we could use a custom sub-class of PlanningData
        new_planning: PlanningData = PlanningData(delta_weight=delta_weight, min_due_date=min_due_date,
                                                                lots_count=lots_cnt, lot_weights=lot_weights,
                                                                orders_count=orders_cnt, transition_costs=transition_costs,
                                                                logistic_costs=logistic_costs)
        current_coils = [next_material.id] if next_material is not None else []  # here we have a new order, so no need to track previous coils
        new_status = EquipmentStatus(targets=status.targets, snapshot_id=status.snapshot_id, planning=new_planning,
                                     planning_period=status.planning_period, current_order=next.id, previous_order=current.id,
                                     current_material=current_coils)
        target_fct = self.objective_function(new_status)
        new_planning.target_fct = target_fct.total_value
        return new_status, target_fct

    def objective_function(self, status: EquipmentStatus[PlanningData]) -> ObjectiveFunction:
        """
        Evaluate the target/objective function for a specific plant status
        """
        if status is None or status.targets.equipment not in self._plant_ids:  # TODO generate a warning?
            return ObjectiveFunction(total_value=float("inf"))
        params: CostConfig = self._config
        planning: PlanningData = status.planning
        # In our example there are 3 costs components: number of lots, deviation from target weight, and transition costs between individual orders
        # The relative weight of the components can be defined by the parameters
        weight_deviation = (abs(planning.delta_weight) / status.targets.total_weight) ** 2 if status.targets.total_weight > 0 else 0
        penalty_out_of_lot_range: float|None = None
        if status.targets.lot_weight_range is not None:

            def out_of_lot_range(lot_weight: float, target: tuple[float, float]):
                """Returns 1 if lot size is exactly equal to one of the boundaries"""
                diff = target[1] - target[0]
                center = (target[0] + target[1])/2
                relative_deviation = abs((lot_weight - center) / diff * 2)
                return relative_deviation ** 2

            out_of_lot_range = sum(out_of_lot_range(w, status.targets.lot_weight_range) for w in planning.lot_weights)
            penalty_out_of_lot_range = params.factor_out_of_lot_range * out_of_lot_range
        log_costs = params.factor_logistic_costs * planning.logistic_costs
        result = planning.lots_count + \
            params.factor_weight_deviation * weight_deviation + \
            params.factor_transition_costs * planning.transition_costs + \
            log_costs
        if penalty_out_of_lot_range is not None:
            result += penalty_out_of_lot_range
        return ObjectiveFunction(total_value=result, lots_count=planning.lots_count, weight_deviation=params.factor_weight_deviation * weight_deviation,
                                lot_size_deviation=penalty_out_of_lot_range, transition_costs=params.factor_transition_costs * planning.transition_costs,
                                logistic_costs=log_costs)

    def evaluate_equipment_assignments(self, equipment_targets: EquipmentProduction, process: str, assignments: dict[str, OrderAssignment],
                                       snapshot: Snapshot, planning_period: tuple[datetime, datetime],
                                       min_due_date: datetime|None=None, current_material: list[Material] | None=None,
                                       track_structure: bool=False) -> EquipmentStatus:
        plant_id = equipment_targets.equipment
        target_weight=equipment_targets.total_weight
        target_lot_size = equipment_targets.lot_weight_range
        plant = next((p for p in self._site.equipment if p.id == plant_id), None)
        if plant is None:
            raise Exception(f"Plant not found: {plant_id}")
        assignments = {order: assignment for order, assignment in assignments.items() if assignment.equipment == plant_id}
        if len(assignments) == 0:
            if current_material is not None and len(current_material) > 0:
                raise Exception("Current coils specified " + str([c.id for c in current_material]) + ", but no order assignments")
            status = EquipmentStatus(targets=equipment_targets, snapshot_id=snapshot.timestamp, planning_period=planning_period,
                                     planning=PlanningData(delta_weight=target_weight),
                                     current_material=[] if current_material is not None else None)
            target_fct = self.objective_function(status)
            status.planning.target_fct = target_fct.total_value
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
        logistic_costs: float = 0
        if self._site.logistic_costs is not None:
            orders_with_plants = (o for o in orders_sorted if o.current_equipment is not None and len(o.current_equipment) > 0)
            logistic_costs = sum(self._logistic_costs_for_order(o, plant_id) for o in orders_with_plants)
        # TODO in function
        planning: PlanningData = PlanningData(delta_weight=delta_weight, min_due_date=min_due_date,
                                                            lots_count=len(lots), lot_weights=list(lot_weights.values()),
                                                            orders_count=len(orders_sorted),
                                                            transition_costs=transition_costs,
                                                            logistic_costs=logistic_costs)
        status = EquipmentStatus(targets=equipment_targets, snapshot_id=snapshot.timestamp, planning=planning,
                                 planning_period=planning_period, current_order=last_order.id,  # current=last_order.id
                                 previous_order=previous_order.id if previous_order is not None else None,
                                 current_material=[c.id for c in current_material] if current_material is not None else None)
        # previous=previous_order.id if previous_order is not None else None)
        target_fct = self.objective_function(status).total_value
        planning.target_fct = target_fct
        return status

    # TODO: differentiate between individual material and complete orders
    def logistic_costs(self, new_equipment: Equipment, order: Order, material: Material | None = None) -> float:
        return self._logistic_costs_for_order(order, new_equipment.id)

    def _logistic_costs_for_order(self, o: Order, plant: int) -> float:
        log_costs: dict[int, dict[int, float]] = self._site.logistic_costs
        min_costs: float|None = None
        for p in o.current_equipment:
            if p == plant:
                return 0
            if p not in log_costs:
                continue
            costs = log_costs.get(p).get(plant)
            if costs is not None and (min_costs is None or costs < min_costs):
                min_costs = costs
        return min_costs if min_costs is not None else 0

    @staticmethod
    def _sort_dict(dictionary: dict[any, any]) -> dict[any, any]:
        keys_sorted = sorted(key for key in dictionary.keys())
        return {key: dictionary[key] for key in keys_sorted}

    def optimum_possible_costs(self, process: str, num_plants: int):
        return num_plants

