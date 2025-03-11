from datetime import datetime

from dynreact.base.model import MidTermTargets, ProductionTargets, EquipmentProduction, ProductionPlanning, Site


class ModelUtils:

    @staticmethod
    def mid_term_targets_from_ltp_result(result: MidTermTargets, process: str, start_time: datetime, end_time: datetime) -> ProductionTargets:
        overlapping_fractions: dict[int, float] = ModelUtils.applicable_periods(result.sub_periods, start_time, end_time)
        sub_targets: list[ProductionTargets] = result.production_sub_targets.get(process)
        if len(overlapping_fractions) == 0 or sub_targets is None:
            return ProductionTargets(process=process, target_weight={}, period=(start_time, end_time))
        total_target_weights: dict[int, EquipmentProduction] = {}
        mat_target: dict[str, dict[str, float]] = {}
        for period_idx, overlap in overlapping_fractions.items():
            target: ProductionTargets = sub_targets[period_idx]
            if target.material_weights is not None:
                for material, strct in target.material_weights.items():
                    if material not in mat_target:
                        mat_target[material] = {}
                    for cl, weight in strct.items():
                        if cl not in mat_target[material]:
                            mat_target[material][cl] = 0
                        mat_target[material][cl] = mat_target[material][cl] + weight * overlap
            for plant_id, plant_targets in target.target_weight.items():
                if plant_id not in total_target_weights:
                    total_target_weights[plant_id] = EquipmentProduction(equipment=plant_id, total_weight=0) # material_weights=)
                aggregated_target: EquipmentProduction = total_target_weights[plant_id]
                added_total = plant_targets.total_weight * overlap
                aggregated_target.total_weight += added_total
        return ProductionTargets(process=process, period=(start_time, end_time), target_weight=total_target_weights)

    @staticmethod
    def aggregated_structure(site: Site, planning: ProductionPlanning) -> dict[str, dict[str, float]]:
        total: dict[str, dict[str, float]] = {cat.id: {cl.id: 0 for cl in cat.classes} for cat in site.material_categories}
        for status in (stat for stat in planning.equipment_status.values() if
                        stat.planning is not None and stat.planning.material_structure is not None):
            structure = status.planning.material_structure
            for cat, cat_dict in structure.items():
                target: dict[str, float] = total[cat]
                for cl, value in cat_dict.items():
                    target[cl] += value
        return total

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
