from datetime import datetime, timedelta, date
from typing import Sequence

import numpy as np
import picos as pc

from dynreact.base.model import EquipmentAvailability, MidTermTargets, StorageLevel, Site, ProductionTargets, \
    LongTermTargets, EquipmentProduction


class LtpUtils:

    _zero_delta: timedelta = timedelta(days=0)

    @staticmethod
    def _set_material_constraints(flow_problem: pc.Problem, var: pc.RealVariable, material_categories: dict[str, list[str]]):
        num_shifts = var.shape[1]
        mat_start_idx = 0
        # material constraints  # Note: here we assume the capacity to be the same for all material classes; this is an oversimplification
        for cat, classes in material_categories.items():
            cat_classes = len(classes)
            # for each material category, the sum of material in the corresponding classes must add up to the overall material weight
            flow_problem.require([pc.sum(var[mat_start_idx:mat_start_idx + cat_classes, k]) == var[-1, k] for k in range(num_shifts)])
            mat_start_idx += cat_classes

    @staticmethod
    def _availability_to_hours(periods: list[tuple[datetime, datetime]], avail: EquipmentAvailability) -> list[float]:
        hours = [LtpUtils._availability_for_period(p, avail.daily_baseline, avail.deltas).total_seconds()/3600 for p in periods]
        return hours

    @staticmethod
    def _availability_for_period(period: tuple[datetime, datetime], base: timedelta, deltas: dict[date, timedelta] | None) -> timedelta:
        timedeltas = LtpUtils._zero_delta
        start_time = period[0]
        while start_time < period[1]:
            # end of day or end of period
            end_time = min(period[1], start_time.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1))
            fraction_of_day = (end_time - start_time) / timedelta(days=1)
            timedeltas += fraction_of_day * base
            current_date = start_time.date()
            if deltas is not None and current_date in deltas:
                delta: timedelta = deltas.get(current_date)
                timedeltas += fraction_of_day * delta
            start_time = end_time
        return timedeltas

    @staticmethod
    def to_results(
            site: Site,
            shifts: list[tuple[datetime, datetime]],
            targets: LongTermTargets,
            storages: dict[str, pc.RealVariable|np.ndarray],
            storages_to_equipment: dict[str, dict[int, pc.RealVariable|np.ndarray]],
            equipment_to_storages: dict[int, dict[str, pc.RealVariable|np.ndarray]],
            shift_results: dict[int, pc.BinaryVariable|np.ndarray]|None = None) -> tuple[MidTermTargets, list[dict[str, StorageLevel]]]:
        done_stg = storages["DONE"]
        num_shifts = done_stg.shape[1] - 1
        num_materials = done_stg.shape[0]-1
        # every array has shape [num_material_classes+1, num_shifts+1]
        storage_values: dict[str, np.ndarray] = {stg: stg_var.np2d if isinstance(stg_var, pc.RealVariable) else stg_var for stg, stg_var in storages.items()}
        materials = [clzz.id for cat in site.material_categories for clzz in cat.classes]
        storage_levels: list[dict[str, StorageLevel]] = []
        for shift_idx in range(num_shifts+1):
            timestamp = shifts[shift_idx][0] if shift_idx < num_shifts else shifts[shift_idx-1][1]
            levels = {stg: LtpUtils._storage_result(stg, stg_var, shift_idx, timestamp, materials) for stg, stg_var in storage_values.items()}
            storage_levels.append(levels)
        equipment_by_proc: dict[str, list[int]] = {proc.name_short: [eq.id for eq in site.get_process_equipment(proc.name_short, do_raise=True)] for proc in site.processes}
        result: dict[str, list[ProductionTargets]] = {}
        for proc, equipments in equipment_by_proc.items():
            equipment_targets: list[dict[int, EquipmentProduction]] = [{} for _ in range(num_shifts)]
            material_weights: list[dict[str, float]] = [{mat: 0. for mat in materials} for _ in range(num_shifts)]
            for eq in equipments:
                if eq not in equipment_to_storages:  # ?
                    continue
                #outgoing_flows = list(equipment_to_storages[eq].values())  # TODO check
                outgoing_flows: list[np.ndarray] = [flow.np2d if isinstance(flow, pc.RealVariable) else flow for flow in equipment_to_storages[eq].values()]
                for shift_idx in range(num_shifts):
                    total_weight = sum(fl[-1, shift_idx] for fl in outgoing_flows)
                    eq_material = {}
                    for mat_idx, material in enumerate(materials):
                        mat_weight = sum(fl[mat_idx, shift_idx] for fl in outgoing_flows)
                        material_weights[shift_idx][material] += mat_weight
                        eq_material[material] = mat_weight
                    eq_prod = EquipmentProduction(equipment=eq, total_weight=total_weight, material_weights=eq_material)
                    equipment_targets[shift_idx][eq] = eq_prod
            proc_result: list[ProductionTargets] = [ProductionTargets(process=proc, target_weight=eq_target_dct, material_weights=mat_target_dct, period=shifts[shift_idx])
                                                    for shift_idx, (eq_target_dct, mat_target_dct) in enumerate(zip(equipment_targets, material_weights))]
            result[proc] = proc_result
        mtp_result = MidTermTargets(period=targets.period, production_targets=targets.production_targets, total_production=targets.total_production,
                       sub_periods=shifts, production_sub_targets=result)
        return mtp_result, storage_levels

    @staticmethod
    def _storage_result(stg: str, stg_var: np.ndarray, shift_idx: int, timestamp: datetime, materials: Sequence[str]) -> StorageLevel:
        material_levels = {mat: stg_var[idx, shift_idx] for idx, mat  in enumerate(materials)}
        return StorageLevel(storage=stg, filling_level=stg_var[-1, shift_idx], timestamp=timestamp, material_levels=material_levels)

    @staticmethod
    def store_results(
            site: Site,
            structure: LongTermTargets,
            shifts: list[tuple[datetime, datetime]],
            availabilities: dict[int, EquipmentAvailability],
            storage_levels: dict[str, np.ndarray],
            storages_to_equipment: dict[str, dict[int, np.ndarray]],
            equipment_to_storages: dict[int, dict[str, np.ndarray]],
            file: str):
        from dynreact.ltp2.ResultSerialization import SerializableResult
        result = SerializableResult(site=site, structure=structure, shifts=shifts, storage_levels=storage_levels,
                   availabilities=availabilities, storages_to_equipment=storages_to_equipment, equipment_to_storages=equipment_to_storages)
        json = result.model_dump_json(exclude_unset=True, exclude_none=True)
        with open(file, mode="w") as fl:
            fl.write(json)
        print("Written results to", file)

    @staticmethod
    def load_results(file: str):
        with open(file, mode="r") as fl:
            json = fl.read()
        from dynreact.ltp2.ResultSerialization import SerializableResult
        result = SerializableResult.model_validate_json(json)
        return result

