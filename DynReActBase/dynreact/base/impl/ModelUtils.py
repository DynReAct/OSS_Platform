from datetime import datetime, timedelta, date
from typing import Mapping, Sequence

from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.model import MidTermTargets, ProductionTargets, EquipmentProduction, ProductionPlanning, Site, \
    EquipmentAvailability, MaterialCategory, SUM_MATERIAL, Lot, PlannedWorkingShift, Snapshot, StorageLevel, Storage, \
    Material, LotTimes, Order


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
            snapshot: Snapshot|None,
            horizon: timedelta,
            num_shifts: int,
            site: Site,
            snapshot_provider: SnapshotProvider,
            equipment_ids: Sequence[int]|None=None,
            interval: tuple[datetime, datetime]|None=None,
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
            interval: if interval is specified, then snapshot is optional; the plannign interval is considered fixed then
            max_horizon: maximum time horizon to consider (w.r.t. the snapshot timestamp)

        Returns:
            a tuple consisting of: production targets, earliest start time over all equipments, start times by equipment
        """
        equipment_ids = equipment_ids if equipment_ids is not None else [p.id for p in site.get_process_equipment(process)]
        if len(equipment_ids) == 0:
            raise Exception("No equipment specified")
        max_planning_time = snapshot.timestamp + max_horizon if interval is None else interval[1]
        material_by_equipment_targets: dict[int, dict[str, float]] = {}
        material_by_equipment_existing: dict[int, dict[str, float]] = {}
        scale_factor_by_equipment: dict[int, float] = {}
        total_weight_by_equipment: dict[int, float] = {}
        min_start: datetime = max_planning_time
        max_end: datetime = snapshot.timestamp + horizon if interval is None else interval[1]
        start_time_by_equipment: dict[int, datetime] = {}
        start_time = snapshot.timestamp if interval is None else interval[0]
        for equipment in equipment_ids:
            lots = [lot for lot in snapshot.lots.get(equipment, tuple()) if lot.active and lot.end_time is not None] if snapshot is not None else []
            eq_horizon = max(lt.end_time for lt in lots) if len(lots) > 0 else interval[0] if interval is not None else snapshot.timestamp
            if eq_horizon >= max_planning_time:  # nothing to be planned for this equipment, lots already covered the planning horizon
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
            applicable: dict[int, float] = ModelUtils.applicable_periods(result.sub_periods, start_time, planning_end)
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
            # prod capacity in tons  # TODO consider shifts here?
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
            # step 1: correction for cases where the frozen material already exceeds the planned material
            surpluses_by_mat: dict[str, float] = {mat: eq_existing.get(mat, 0) - weight for mat, weight in mat_targets.items() if eq_existing.get(mat, 0) > weight}
            surpluses_by_cat: dict[str, float] = {cat.id: sum(surpluses_by_mat[cl.id] for cl in cat.classes if cl.id in surpluses_by_mat) for cat in site.material_categories if any(cl.id in surpluses_by_mat for cl in cat.classes)}
            for cat_id, surplus in surpluses_by_cat.items():
                cat = next(c for c in site.material_categories if c.id == cat_id)
                available_classes: dict[str, float] = {cl.id: mat_targets[cl.id] for cl in cat.classes if cl.id in mat_targets and cl.id not in surpluses_by_mat}
                total_available = sum(available_classes.values())
                for mat, weight in available_classes.items():
                    fraction = weight / total_available
                    new_weight = max(weight - fraction * surplus, 0.)
                    mat_targets[mat] = new_weight
            for mat, weight in mat_targets.items():
                existing = eq_existing.get(mat, 0.)
                # corrections for negative values already applied above
                delta = max(weight - existing, 0.) * scale_factor
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
    def merge_targets(targets: Sequence[ProductionTargets], require_same_period: bool=True, require_same_process: bool=True) -> ProductionTargets:
        """
        Note: all input targets must have the same process and period, otherwise an exception is thrown.
        Furthermore, either all targets must support material structure or none.
        :param targets:
        :return:
        """
        if len(targets) == 0:
            raise Exception("No targets specified")
        if len(targets) == 1:
            return targets[0]
        period: tuple[datetime, datetime]|None = None
        process: str|None = None
        equipment_targets: dict[int, EquipmentProduction]|None = None
        has_mat_structure: bool|None = None
        has_equipment_mat_structure: bool|None = None
        mat_structure: dict[str, float|dict[str, float]] | None = None
        equipment_mat_structure: dict[int, dict[str, float]]|None = None
        for t in targets:
            if period is None:
                period = t.period
                process = t.process
                equipment_targets = {e: t.model_copy() for e, t in t.target_weight.items()}
                has_mat_structure = t.material_weights is not None and len(t.material_weights) > 0
                if has_mat_structure:
                    mat_structure = {cl: {cl2: w2 for cl2, w2 in weight.items()} if isinstance(weight, Mapping) else weight
                                 for cl, weight in t.material_weights.items()}
                has_equipment_mat_structure = all(w.material_weights is not None for w in t.target_weight.values())
                if has_equipment_mat_structure:
                    equipment_mat_structure = {e: dict(w.material_weights) for e, w in t.target_weight.items()}
            elif require_same_period and (t.period[0] != period[0] or t.period[1] != period[1]):
                raise Exception(f"Production targets have different periods: {period}: {t.period}")
            elif require_same_process and process != t.process:
                raise Exception(f"Production targets have different processes: {process}: {t.process}")
            elif (t.material_weights is not None and len(t.material_weights) > 0) != has_mat_structure:
                raise Exception(f"Trying to merge targets with and without material structure")
            elif all(w.material_weights is not None for w in t.target_weight.values()) != has_equipment_mat_structure:
                raise Exception(f"Trying to merge equipment targets with and without material structure")
            else:
                for eq, eq_target in t.target_weight.items():
                    if eq not in equipment_targets:
                        equipment_targets[eq] = eq_target.model_copy()
                    else:
                        new_weight = equipment_targets[eq].total_weight + eq_target.total_weight
                        mat_by_equipment: dict[str, float]|None = None
                        if has_equipment_mat_structure:
                            mat_by_equipment = equipment_mat_structure[eq]
                            for cl, weight in eq_target.material_weights.items():
                                if cl not in mat_by_equipment:
                                    mat_by_equipment[cl] = 0.
                                mat_by_equipment[cl] = mat_by_equipment[cl] + weight
                        equipment_targets[eq] = equipment_targets[eq].model_copy(update=
                                    {"total_weight": new_weight, "material_weights": mat_by_equipment})
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
        if not require_same_period:
            min_time = min(t.period[0] for t in targets)
            max_time = max(t.period[1] for t in targets)
            period = (min_time, max_time)
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

    @staticmethod
    def storage_content_from_snapshot(snapshot: Snapshot, site: Site) -> dict[str, StorageLevel]:
        material_by_orders: dict[str, list[Material]] = {}
        for mat in snapshot.material:
            if mat.order not in material_by_orders:
                material_by_orders[mat.order] = []
            material_by_orders[mat.order].append(mat)
        storage_by_equipment: dict[int, Storage] = \
            {e.id: site.get_storage(e.storage_in, do_raise=True) for e in site.equipment if e.storage_in is not None}
        # outer key: storage, inner key: material class
        material_levels: dict[str, dict[str, float]] = {}
        total_weight: dict[str, float] = {}  # by storage
        for order in snapshot.orders:
            equipment = order.current_equipment
            storages = [s for s in (storage_by_equipment.get(e) for e in equipment) if s is not None] \
                                        if equipment is not None else tuple()
            if len(storages) == 0:
                continue
            shares: dict[str, float] = {}  # share by storage
            materials = material_by_orders.get(order.id)
            if len(storages) == 1:
                shares[storages[0].name_short] = 1
            elif materials is None or len(materials) == 0:
                for stg in storages:
                    shares[stg.name_short] = 1/len(storages)
            else:
                for mat in materials:
                    storage = storage_by_equipment.get(mat.current_equipment)
                    if storage is not None:
                        stg_id = storage.name_short
                        if stg_id not in shares:
                            shares[stg_id] = 0.
                        shares[stg_id] += mat.weight / order.actual_weight
            for storage in storages:
                stg_id = storage.name_short
                share = shares.get(stg_id)
                if share is None or share <= 0:
                    continue
                if stg_id not in total_weight:
                    total_weight[stg_id] = 0.
                total_weight[stg_id] += order.actual_weight * share
                ml = order.material_classes
                if ml is not None:
                    if stg_id not in material_levels:
                        material_levels[stg_id] = {}
                    mat_levels: dict[str, float] = material_levels[stg_id]
                    for clzz in ml.values():
                        if clzz == "_sum":
                            continue
                        if clzz not in mat_levels:
                            mat_levels[clzz] = 0.
                        mat_levels[clzz] += order.actual_weight * share
        storage_levels: dict[str, StorageLevel] = {}
        for storage, total in total_weight.items():
            if total <= 0:
                continue
            stg_obj = site.get_storage(storage, do_raise=True)
            capacity = stg_obj.capacity_weight  # may be None
            filling_level = total if capacity is None else total/capacity
            mat_levels = material_levels.get(storage)
            relative_mat_levels = {mat: level/capacity for mat, level in mat_levels.items()} \
                if mat_levels is not None and capacity is not None and len(mat_levels) > 0 \
                else mat_levels if mat_levels is not None and len(mat_levels) > 0 \
                else None
            level = StorageLevel(storage=storage, filling_level=filling_level,
                                 timestamp=snapshot.timestamp, material_levels=relative_mat_levels)
            storage_levels[storage] = level
        return storage_levels

    @staticmethod
    def get_order_lot_times_with_fallback(site: Site, snapshot_provider: SnapshotProvider, snapshot: datetime | None = None,
                                          order: str|Sequence[str]|None=None, process: str|None=None) -> dict[str, dict[str, LotTimes]]|None:
        """
        Provides the same functionality as SnapshotProvider.get_order_lot_times(), but with a fallback in case this method is not implemented

        Parameters:
            site:
            snapshot_provider:
            snapshot: snapshot timestamp
            order:    optional order(s) filter
            process:  optional process filter

        Returns:
            A nested dictionary order id -> process -> lot times object
        """
        try:
            return snapshot_provider.get_order_lot_times(snapshot=snapshot, order=order)
        except NotImplementedError:
            pass
        snap_obj = snapshot_provider.load(time=snapshot)
        if not snap_obj:
            return None
        if order is not None and isinstance(order, str):
            order = (order, )
        elif order is None:
            order = [o.id for o in snap_obj.orders]
        order_objects: dict[str, Order] = {o.id: o for o in snap_obj.orders}
        result: dict[str, dict[str, LotTimes]] = {}
        for equipment, lots in snap_obj.lots.items():
            eq_obj = site.get_equipment(equipment)
            lot_process = eq_obj.process if eq_obj else None
            if not lot_process or (process is not None and lot_process != process):
                continue
            for lot in lots:
                if not lot.active or not lot.start_time or not lot.end_time or not any(o in lot.orders for o in order):
                    continue
                lot_weight = lot.weight if lot.weight is not None else sum(order_objects[o].actual_weight for o in lot.orders if o in order_objects)
                if lot_weight < 1e-2:
                    continue
                start_time = lot.start_time
                lot_delta = lot.end_time - lot.start_time
                for l_order in lot.orders:
                    if l_order not in order_objects:
                        continue
                    order_obj = order_objects[l_order]
                    share = order_obj.actual_weight / lot_weight
                    end_time = start_time + share * lot_delta
                    if l_order in order:
                        lot_times = LotTimes(id=l_order, process=lot_process, start=start_time, end=end_time, processing_time=end_time-start_time)
                        if l_order not in result:
                            result[l_order] = {}
                        result[l_order][lot_process] = lot_times
                    start_time = end_time
        return result

    @staticmethod
    def get_material_lot_times_with_fallback(site: Site, snapshot_provider: SnapshotProvider, snapshot: datetime | None = None,
                                          material: str|Sequence[str]|None=None, process: str|None=None) -> dict[str, dict[str, LotTimes]]|None:
        """
        Provides the same functionality as SnapshotProvider.get_material_lot_times(), but with a fallback in case this method is not implemented

        Parameters:
            site:
            snapshot_provider:
            snapshot: snapshot timestamp
            material:    optional material id(s) filter
            process:  optional process filter

        Returns:
            A nested dictionary order id -> process -> lot times object
        """
        try:
            return snapshot_provider.get_material_lot_times(snapshot=snapshot, material=material)
        except NotImplementedError:
            pass
        snap_obj = snapshot_provider.load(time=snapshot)
        if not snap_obj:
            return None
        material_objects: dict[str, Material] = {m.id: m for m in snap_obj.material}
        if material is not None and isinstance(material, str):
            material = (material, )
        elif material is None:
            material = material_objects.keys()
        order_objects = {o.id: o for o in snap_obj.orders}
        mat_by_orders: dict[str, list[Material]] = {}  # Note: unsorted
        for mat_id in material:
            mat = material_objects[mat_id]
            if mat.order not in mat_by_orders:
                mat_by_orders[mat.order] = []
            mat_by_orders[mat.order].append(mat)
        result: dict[str, dict[str, LotTimes]] = {}
        for equipment, lots in snap_obj.lots.items():
            eq_obj = site.get_equipment(equipment)
            lot_process = eq_obj.process if eq_obj else None
            if not lot_process or (process is not None and lot_process != process):
                continue
            for lot in lots:
                if not lot.active or not lot.start_time or not lot.end_time or not any(o in lot.orders for o in mat_by_orders.keys()):
                    continue
                lot_duration = lot.end_time - lot.start_time
                lot_orders = sorted([o for o in mat_by_orders.keys() if o in lot.orders], key=lambda o: lot.orders.index(o))
                lot_weight = lot.weight or sum(order_objects[o].actual_weight for o in lot.orders)
                if lot_weight < 1e-2:
                    continue
                for order in lot_orders:
                    order_idx = lot.orders.index(order)
                    prev_orders = [order_objects[o] for o in lot.orders[:order_idx]]
                    prev_weight = sum(o.actual_weight for o in prev_orders)
                    prev_share = prev_weight/lot_weight
                    start_time = lot.start_time + prev_share * lot_duration
                    order_materials = sorted(mat_by_orders[order], key=lambda mat: (mat.current_process, mat.order_positions.get(lot_process, mat.order_position) if mat.order_positions is not None else mat.order_position))
                    for mat in order_materials:
                        end_time = start_time + (mat.weight / lot_weight * lot_duration)
                        if mat.id in material:
                            if mat.id not in result:
                                result[mat.id] = {}
                            result[mat.id][lot_process] = LotTimes(id=mat.id, process=lot_process, start=start_time, end=end_time, processing_time=end_time-start_time)
                        start_time = end_time
        return result
