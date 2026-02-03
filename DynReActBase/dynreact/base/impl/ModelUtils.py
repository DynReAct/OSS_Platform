from datetime import datetime, timedelta, date
from typing import Mapping

from dynreact.base.model import MidTermTargets, ProductionTargets, EquipmentProduction, ProductionPlanning, Site, \
    EquipmentAvailability, MaterialCategory, SUM_MATERIAL


class ModelUtils:

    @staticmethod
    def mid_term_targets_from_ltp_result(result: MidTermTargets, process: str, start_time: datetime, end_time: datetime) -> ProductionTargets:
        overlapping_fractions: dict[int, float] = ModelUtils.applicable_periods(result.sub_periods, start_time, end_time)
        sub_targets: list[ProductionTargets] = result.production_sub_targets.get(process)
        if len(overlapping_fractions) == 0 or sub_targets is None:
            return ProductionTargets(process=process, target_weight={}, period=(start_time, end_time))
        total_target_weights: dict[int, EquipmentProduction] = {}
        mat_target: dict[str, float] = {}
        for period_idx, overlap in overlapping_fractions.items():
            target: ProductionTargets = sub_targets[period_idx]
            if target.material_weights is not None:
                for material, weight in target.material_weights.items():
                    if isinstance(weight, dict):
                        print("Hierarchical structure not supported yet in mid_term_targets_from_ltp_results")
                        continue
                    if material not in mat_target:
                        mat_target[material] = 0
                    mat_target[material] += weight * overlap
            for plant_id, plant_targets in target.target_weight.items():
                if plant_id not in total_target_weights:
                    total_target_weights[plant_id] = EquipmentProduction(equipment=plant_id, total_weight=0) # material_weights=)
                aggregated_target: EquipmentProduction = total_target_weights[plant_id]
                added_total = plant_targets.total_weight * overlap
                aggregated_target.total_weight += added_total
        return ProductionTargets(process=process, period=(start_time, end_time), target_weight=total_target_weights, material_weights=mat_target)

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
