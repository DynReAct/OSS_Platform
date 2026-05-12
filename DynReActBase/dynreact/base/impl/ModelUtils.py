from datetime import datetime, timedelta, date
from typing import Mapping, Sequence

from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.model import MidTermTargets, ProductionTargets, EquipmentProduction, ProductionPlanning, Site, \
    EquipmentAvailability, MaterialCategory, SUM_MATERIAL, Lot, PlannedWorkingShift, Snapshot


class ModelUtils:

    @staticmethod
    def mid_term_targets_from_ltp_result_deprecated(result: MidTermTargets | Sequence[MidTermTargets], process: str,
                                                    start_time: datetime, end_time: datetime,
                                                    existing_lots: Sequence[Lot]|None=None) -> ProductionTargets:
        # TODO consider material structure
        """
        @deprecated

        Determines the actual amount of material to be produced by the equipment belonging to the considered
        process stage in the specified time interval.
        Note: equipment capacity is ignored here, it is assumed, in particular,
        that equipment downtimes have already been considered in the generation of the passed MidTermTargets results.

        :param result: the targets applicable to the period
        :param process: process id
        :param start_time: planning period start
        :param end_time: planning period end
        :param existing_lots: lots to consider in the planning; the returned targets are reduced by the amount of
            material already covered in these lots during the considered time interval. Note that this requires the
            lot start and end time to be set; lots without start and/or end time are ignored. The same applies to
            the weight field of the lots, it is assumed to be set.
        :return: production targets for the passed time interval and process stage
        """
        if isinstance(result, Sequence):
            # existing lots must only be subtracted once, therefore we cannot pass them to all instances here
            output = ModelUtils.merge_targets([ModelUtils.mid_term_targets_from_ltp_result_deprecated(inp, process, start_time, end_time) for inp in result])
            total_target_weights: dict[int, EquipmentProduction] = output.target_weight
            mat_target: dict[str, float]|None = output.material_weights
        else:
            overlapping_fractions: dict[int, float] = ModelUtils.applicable_periods(result.sub_periods, start_time, end_time)
            sub_targets: list[ProductionTargets] = result.production_sub_targets.get(process)
            if len(overlapping_fractions) == 0 or sub_targets is None:
                return ProductionTargets(process=process, target_weight={}, period=(start_time, end_time))
            total_target_weights = {}
            mat_target = {}
            for period_idx, overlap in overlapping_fractions.items():
                target: ProductionTargets = sub_targets[period_idx]
                if target.material_weights is not None:
                    for material, weight in target.material_weights.items():
                        if isinstance(weight, dict):
                            raise Exception("Hierarchical structure not supported yet in mid_term_targets_from_ltp_results")
                        if material not in mat_target:
                            mat_target[material] = 0
                        mat_target[material] += weight * overlap
                for plant_id, plant_targets in target.target_weight.items():
                    if plant_id not in total_target_weights:
                        total_target_weights[plant_id] = EquipmentProduction(equipment=plant_id, total_weight=0) # material_weights=)
                    aggregated_target: EquipmentProduction = total_target_weights[plant_id]
                    added_total = plant_targets.total_weight * overlap
                    aggregated_target.total_weight += added_total
        has_material_structure: bool = mat_target is not None and len(mat_target) > 0
        if existing_lots is not None:
            if has_material_structure:
                raise Exception("Handling existing lots with material structure not implemented yet")  # TODO
            for lot in existing_lots:
                if lot.equipment not in total_target_weights or lot.start_time is None or lot.end_time is None or lot.weight is None:
                    continue
                if lot.end_time <= start_time or lot.start_time >= end_time:
                    continue
                overlap_period = lot.end_time - lot.start_time if lot.end_time <= end_time and lot.start_time >= start_time else \
                        lot.end_time - start_time if lot.end_time <= end_time else \
                        end_time - lot.start_time if lot.start_time >= start_time else \
                        end_time - start_time
                overlap = overlap_period / (lot.end_time - lot.start_time)
                lot_weight = lot.weight * overlap
                new_weight = max(0., total_target_weights[lot.equipment].total_weight - lot_weight)
                if new_weight <= 0:
                    total_target_weights.pop(lot.equipment)
                else:
                    total_target_weights[lot.equipment] = total_target_weights[lot.equipment].model_copy(update={"total_weight": new_weight})
        return ProductionTargets(process=process, period=(start_time, end_time), target_weight=total_target_weights, material_weights=mat_target if has_material_structure else None)

    @staticmethod
    def mid_term_targets_from_ltp_result(
            result: MidTermTargets,
            process: str,
            snapshot: Snapshot,
            horizon: timedelta,
            num_shifts: int,
            site: Site,
            snapshot_provider: SnapshotProvider,
            equipment_ids: Sequence[int]|None=None,
            max_horizon: timedelta = timedelta(days=8)) -> tuple[ProductionTargets, datetime, dict[int, datetime]]:
        """
        Determines the actual amount of material to be produced by the equipment belonging to the considered
        process stage in the specified time interval, considering the targets defined by the long-term planning
        algorithm and the existing, complete lots.

        Parameters

            result: long-term planning results
            process: process stage the planning applies to
            snapshot: determines the start time and existing lots
            horizon: planning horizon, such as 1 day
            num_shifts: specifies into how many shifts the planning horizon is to be divided
            site: generic site configuration
            snapshot_provider: the snapshot provider
            equipment_ids: optional equipments ids to be included. If not specified, all equipment for the considered
                process stage is included
            max_horizon: maximum time horizon to consider (w.r.t. the snapshot timestamp)

        Returns:
            a tuple consisting of: production targets, earliest start time over all equipments, start times by equipment
        """
        equipment_ids = equipment_ids if equipment_ids is not None else [p.id for p in site.get_process_equipment(process)]
        if len(equipment_ids) == 0:
            raise Exception("No equipment specified")
        max_planning_time = snapshot.timestamp + max_horizon
        material_by_equipment_targets: dict[int, dict[str, float]] = {}
        material_by_equipment_existing: dict[int, dict[str, float]] = {}
        scale_factor_by_equipment: dict[int, float] = {}
        total_weight_by_equipment: dict[int, float] = {}
        min_start: datetime = max_planning_time
        max_end: datetime = snapshot.timestamp + horizon
        start_time_by_equipment: dict[int, datetime] = {}
        for equipment in equipment_ids:
            lots = [lot for lot in snapshot.lots.get(equipment, tuple()) if snapshot_provider.is_lot_complete(lot) and lot.end_time is not None]
            eq_horizon = max(lt.end_time for lt in lots) if len(lots) > 0 else snapshot.timestamp
            if eq_horizon >= max_planning_time:  # nothing to be planned for this equipment, lots already cover the planning horizon
                continue
            planning_end = min(eq_horizon + horizon, max_planning_time)
            if eq_horizon < min_start:
                min_start = eq_horizon
            if planning_end > max_end:
                max_end = planning_end
            #applicable = ModelUtils.applicable_periods(result.sub_periods, eq_horizon, planning_end)
            #if len(applicable) == 0:
            #    continue
            # need to sum up all targets from now, and then subtract the existing lots
            equipment_horizon: timedelta = planning_end - eq_horizon
            applicable: dict[int, float] = ModelUtils.applicable_periods(result.sub_periods, snapshot.timestamp, planning_end)
            if len(applicable) == 0:  # nothing planned for this equipment?
                continue
            mats_existing: dict[str, float] = {}
            total_existing = 0.
            for lot in lots:
                if lot.material_weights is None:
                    raise Exception(f"Lot without material weights specified {lot.id}: {lot}")
                for mat, weight in lot.material_weights.items():
                    if mat not in mats_existing:
                        mats_existing[mat] = 0.
                    mats_existing[mat] = mats_existing[mat] + weight
                total_existing += lot.weight
            mats: dict[str, float] = {}
            total_targets = 0.
            for period_idx, fraction in applicable.items():
                targets: ProductionTargets = result.production_sub_targets[process][period_idx]
                if equipment not in targets.target_weight:
                    continue
                equipment_targets: EquipmentProduction = targets.target_weight[equipment]
                if equipment_targets.material_weights is None:
                    raise Exception(f"Equipment targets without material weights specified: {equipment_targets}")
                for mat, weight in equipment_targets.material_weights.items():
                    if isinstance(weight, Mapping):
                        raise Exception(f"Cannot handle nested material structure for equipment {equipment}: {targets}")
                    if mat not in mats:
                        mats[mat] = 0.
                    mats[mat] = mats[mat] + (weight * fraction)
                total_targets += equipment_targets.total_weight * fraction
            # TODO material class specific capacity
            equipment_obj = site.get_equipment(equipment, do_raise=True)
            # prod capacity in tons
            capacity = equipment_obj.throughput_capacity * equipment_horizon.total_seconds() / 3_600
            planned_production: float = total_targets - total_existing
            if planned_production <= capacity * 0.05:
                # negative or very small: already scheduled more material than what is foreseen by the long-term planning
                continue
            scaling = 1.
            total_weight = planned_production
            if planned_production >= capacity * 0.08:
                scaling = capacity / planned_production
                total_weight = capacity
            else:
                best_number_shifts: int = min((sh for sh in range(num_shifts+1)), key=lambda sh: abs(capacity/num_shifts * sh - planned_production))
                if best_number_shifts == 0:
                    continue
                total_weight = capacity / num_shifts * best_number_shifts
                scaling = total_weight / planned_production
            scale_factor_by_equipment[equipment] = scaling
            total_weight_by_equipment[equipment] = total_weight
            material_by_equipment_targets[equipment] = mats
            material_by_equipment_existing[equipment] = mats_existing
            start_time_by_equipment[equipment] = eq_horizon
        equipment_weights: dict[int, EquipmentProduction] = {}
        material_targets_overall: dict[str, float] = {}
        _empty = {}
        total = 0.
        for equipment, mat_targets in material_by_equipment_targets.items():
            eq_existing = material_by_equipment_existing.get(equipment, _empty)
            scale_factor = scale_factor_by_equipment.get(equipment, 1.)
            final_equipment_mat_weights: dict[str, float] = {}
            for mat, weight in mat_targets.items():
                existing = eq_existing.get(mat, 0.)
                delta = max(weight - existing, 0.) * scale_factor  # TODO might need to handle negative values specifically, since the material class values do not add up in this case
                final_equipment_mat_weights[mat] = delta
                material_targets_overall[mat] = material_targets_overall.get(mat, 0.) + delta
            eq_total = total_weight_by_equipment.get(equipment, 0.)
            eq_prod = EquipmentProduction(equipment=equipment, total_weight=eq_total, material_weights=final_equipment_mat_weights)
            equipment_weights[equipment] = eq_prod
            total += eq_total
        prod_targets = ProductionTargets(process=process, target_weight=equipment_weights, period=(min_start, max_end), material_weights=material_targets_overall)
        return prod_targets, min_start, start_time_by_equipment

    @staticmethod
    def aggregated_structure(site: Site, planning: ProductionPlanning) -> dict[str, dict[str, float]]:
        """
        Aggregate material structure for one process step over equipments
        :param site:
        :param planning:
        :return:
        """
        total: dict[str, dict[str, float]] = {cat.id: {cl.id: 0 for cl in cat.classes} for cat in site.material_categories}
        for status in (stat for stat in planning.equipment_status.values() if
                        stat.planning is not None and stat.planning.material_structure is not None):
            structure = status.planning.material_structure
            for cat, cat_dict in structure.items():
                target: dict[str, float] = total[cat]
                for cl, value in cat_dict.items():
                    target[cl] = target[cl] + value
        return total

    @staticmethod
    def aggregated_structure_nested(site: Site, planning: ProductionPlanning, main_category: str) -> dict[str, dict[str, dict[str, float]]]:
        """
        Aggregate nested material structure for one process step over equipments
        :param site:
        :param planning:
        :param main_category:
        :return: Outermost key: class id for main category, middle key: sub category id, innermost key: class id; (special keys \"_sum\" represent the total/aggregated values).
        """
        # TODO
        #  - first adapt planning.material_structure to contain the required nested structure (rather add a new field?),
        #  - then adapt the aggregation => DONE
        #  - then adapt the cost function
        main_cat: MaterialCategory = next(cat for cat in site.material_categories if cat.id == main_category)
        total: dict[str, dict[str, dict[str, float]]] = \
                {main.id: {cat.id: {cl.id: 0 for cl in cat.classes} for cat in site.material_categories if cat != main_cat} for main in main_cat.classes}
        for status in (stat for stat in planning.equipment_status.values() if
                       stat.planning is not None and stat.planning.nested_material_structure is not None):
            structure: dict[str, dict[str, dict[str, float]]] = status.planning.nested_material_structure
            "Outermost key: class id for main category, middle key: sub category id, innermost key: class id; special keys \"_sum\" represent the total/aggregated values."
            for main_class, cat_dict in structure.items():
                if main_class == SUM_MATERIAL:
                    continue
                targets: dict[str, dict[str, float]] = total[main_class]
                for cat, cl_dict in cat_dict.items():
                    if cat == SUM_MATERIAL:
                        continue
                    target: dict[str, float] = targets[cat]
                    for cl, value in cl_dict.items():
                        target[cl] = target[cl] + value
        return total

    @staticmethod
    def main_category_for_targets(material_weight_targets: dict[str, float|dict[str, float]] | None, categories: list[MaterialCategory]) -> MaterialCategory|None:
        if material_weight_targets is None or not any(isinstance(target, Mapping) for target in material_weight_targets.values()):
            return None
        target_classes: list[str] = [cl for cl in material_weight_targets.keys() if cl != SUM_MATERIAL]
        for cat in categories:
            missing_class: bool = any(not any(sub.id == cl for sub in cat.classes) for cl in target_classes)
            if not missing_class:
                return cat
        return None

    @staticmethod
    def applicable_periods(sub_periods: list[tuple[datetime, datetime]], start_time: datetime, end_time: datetime) -> dict[int, float]:
        """
        Returns a dictionary with keys = indices of sub_periods, values: share (0-1) of period that overlaps with the interval start_time - end_time.
        It is assumed that sub_periods are ordered chronologically.
        """
        result: dict[int, float] = {}
        for idx, period in enumerate(sub_periods):
            if period[0] >= end_time:
                break
            if period[1] <= start_time:
                continue
            if period[0] >= start_time and period[1] <= end_time:
                result[idx] = 1
            else:
                overlap: tuple[datetime, datetime] = (max(period[0], start_time), min(period[1], end_time))
                overlapping_fraction = (overlap[1] - overlap[0])/(period[1]-period[0])
                result[idx] = overlapping_fraction
        return result

    @staticmethod
    def aggregate_availabilities(plant_data: list[EquipmentAvailability], start: date, end: date) -> timedelta:
        start0 = start
        availability = timedelta()
        for data in plant_data:
            end1 = data.period[1]
            if end1 <= start0:
                continue
            start1 = data.period[0]
            if start1 >= end:
                break
            end1 = min(end, end1)
            if start1 < start0:
                start1 = start0
            elif start0 < start1:  # here we have a period without availability data => assume full availability
                availability += start1 - start0
            if start1 >= end1:
                break
            start0 = end1
            days_diff: int = (end1 - start1).days
            baseline: timedelta = data.daily_baseline or timedelta(days=1)
            availability += days_diff * baseline
            if data.deltas is not None:
                for day, delta in data.deltas.items():
                    if day < start1 or day >= end1:
                        continue
                    availability += delta
        if len(plant_data) == 0 or end > plant_data[-1].period[1]:
            last_start = plant_data[-1].period[1] if len(plant_data) > 0 else start
            availability += end - last_start
        return availability

    @staticmethod
    def shifts_working_duration(shifts: Sequence[PlannedWorkingShift], start: datetime, end: datetime) -> timedelta:
        zero_duration = timedelta()
        result = zero_duration
        for shift in shifts:
            if shift.period[1] <= start or shift.period[0] >= end or shift.worktime <= zero_duration:
                continue
            overlap = (min(shift.period[1], end) - max(shift.period[0], start)) /  (shift.period[1] - shift.period[0])
            result += overlap * shift.worktime
        return result

    @staticmethod
    def merge_targets(targets: Sequence[ProductionTargets]) -> ProductionTargets:
        """
        Note: all input targets must have the same process and period, otherwise an exception is thrown.
        Furthermore, either all targets must support material structure or none.
        :param targets:
        :return:
        """
        period: tuple[datetime, datetime]|None = None
        process: str|None = None
        equipment_targets: dict[int, EquipmentProduction]|None = None
        has_mat_structure: bool|None = None
        mat_structure: dict[str, float|dict[str, float]] | None = None
        for t in targets:
            if period is None:
                period = t.period
                process = t.process
                equipment_targets = {e: t.model_copy() for e, t in t.target_weight.items()}
                has_mat_structure = t.material_weights is not None and len(t.material_weights) > 0
                if has_mat_structure:
                    mat_structure = {cl: {cl2: w2 for cl2, w2 in weight.items()} if isinstance(weight, Mapping) else weight
                                 for cl, weight in t.material_weights.items()}
            elif t.period[0] != period[0] or t.period[1] != period[1]:
                raise Exception(f"Production targets have different periods: {period}: {t.period}")
            elif process != t.process:
                raise Exception(f"Production targets have different processes: {process}: {t.process}")
            elif (t.material_weights is not None and len(t.material_weights) > 0) != has_mat_structure:
                raise Exception(f"Trying to merge targets with and without material structure")
            else:
                for eq, eq_target in t.target_weight.items():
                    if eq not in equipment_targets:
                        equipment_targets[eq] = eq_target.model_copy()
                    else:
                        new_weight = equipment_targets[eq].total_weight + eq_target.total_weight
                        equipment_targets[eq] = equipment_targets[eq].model_copy(update={"total_weight": new_weight})
                if has_mat_structure:
                    for cl, weight in t.material_weights.items():
                        if cl not in mat_structure:
                            mat_structure[cl] = {cl2: w2 for cl2, w2 in weight.items()} if isinstance(weight, Mapping) else weight
                        else:
                            if isinstance(weight, Mapping):
                                existing_mats = mat_structure[cl]
                                old_keys = list(existing_mats.keys())
                                all_keys = old_keys + [key for key in weight.keys() if key not in old_keys]
                                mat_structure[cl] = {key: existing_mats.get(key, 0) + weight.get(key, 0) for key in all_keys}
                            else:
                                mat_structure[cl] += weight
        return ProductionTargets(process=process, target_weight=equipment_targets, period=period, material_weights=mat_structure)

    @staticmethod
    def lots_horizon(equipment: list | tuple[int], lots: Sequence[Lot]) -> tuple[datetime | None, dict[int, datetime], dict[int, str]]:
        """
        Lots are only considered if they have start and end time set, the weight field set, and status > 1.
        :param process:
        :param site:
        :param lots:
        :return:
            - The common planning horizon of all equipments, i.e., the time until which all equipments are covered by lots.
                None if some equipment has no applicable lots at all. Note that the horizon may be earlier than the current timestamp.
            - Horizon by equipment id
            - last order id scheduled by equipment id.
        """
        if len(equipment) == 0:
            return None, {}, {}
        horizons: dict[int, datetime] = {}
        last_orders: dict[int, str] = {}
        for lot in lots:
            # status and weight filters ok?
            if lot.equipment not in equipment or lot.start_time is None or lot.end_time is None or lot.weight is None or lot.status <= 1:
                continue
            if lot.equipment in horizons and horizons[lot.equipment] >= lot.end_time:
                continue
            horizons[lot.equipment] = lot.end_time
            last_orders[lot.equipment] = lot.orders[-1]
        common_horizon = None if any(e not in horizons for e in equipment) else min(horizons.values())
        return common_horizon, horizons, last_orders




