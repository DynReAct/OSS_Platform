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
            file: str,
            frozen_horizons:  dict[int, datetime] | None = None):
        from dynreact.ltp.ResultSerialization import SerializableResult
        result = SerializableResult(site=site, structure=structure, shifts=shifts, storage_levels=storage_levels,
                   availabilities=availabilities, storages_to_equipment=storages_to_equipment, equipment_to_storages=equipment_to_storages, frozen_horizons=frozen_horizons)
        json = result.model_dump_json(exclude_unset=True, exclude_none=True)
        with open(file, mode="w") as fl:
            fl.write(json)
        print("Written results to", file)

    @staticmethod
    def load_results(file: str):
        with open(file, mode="r") as fl:
            json = fl.read()
        from dynreact.ltp.ResultSerialization import SerializableResult
        result = SerializableResult.model_validate_json(json)
        return result

    @staticmethod
    def analyze_flows(equipment_to_storages: dict[int, dict[str, np.ndarray]], storages_to_equipment: dict[str, dict[int, np.ndarray]], site: Site, num_shifts: int, process: str|None=None,
                      fail_on_error: bool = False, error_threshold: float = 1., prefix: str=""):
        all_mats = [clzz.id for cat in site.material_categories for clzz in cat.classes]
        cat_indices: dict[str, Sequence[int]] = {cat.id: [all_mats.index(cl.id) for cl in cat.classes] for cat in site.material_categories}
        cats = {cat.id: cat for cat in site.material_categories}
        classes_cnt = len(all_mats)
        equipments = list(equipment_to_storages.keys())
        zero_start = np.zeros(shape=(classes_cnt + 1, num_shifts))
        if not fail_on_error:
            print(f"{prefix} Equipments to be analyzed", f"for process {process}" if process else "", f": {equipments}")
        for equipment in equipments:
            outgoing_flows = sum(equipment_to_storages[equipment].values(), start=zero_start)
            incoming_flows = sum((dct[equipment] for stg, dct in storages_to_equipment.items() if equipment in dct), start=zero_start)
            total_flow_dev: bool = False
            cat_in_dev: dict[str, bool] = {cat: False for cat in cats.keys()}
            cat_out_dev: dict[str, bool] = {cat: False for cat in cats.keys()}
            for shift in range(num_shifts):
                total_flow_in = incoming_flows[-1, shift]
                total_flow_out = outgoing_flows[-1, shift]
                if not total_flow_dev and abs(total_flow_in - total_flow_out) > error_threshold:
                    total_flow_dev = True
                    msg = f"{prefix}  Total flow in != total flow out for equipment {equipment} in shift {shift}. In: {total_flow_in:.2f}, out: {total_flow_out:.2f}"
                    if fail_on_error:
                        raise Exception(msg)
                    print(msg)
                for cat, indices in cat_indices.items():
                    cat_sum_in = sum(incoming_flows[indices, shift])
                    cat_sum_out = sum(outgoing_flows[indices, shift])
                    if not cat_in_dev[cat] and abs(cat_sum_in - total_flow_in) > error_threshold:
                        cat_in_dev[cat] = True
                        msg = f"{prefix}   Category in flow != total in flow for equipment {equipment}, category {cat}, in shift {shift}: Total: {total_flow_in:.2f}, catgory flow: {cat_sum_in}"
                        if fail_on_error:
                            raise Exception(msg)
                        print(msg)
                    if not cat_out_dev[cat] and abs(cat_sum_out - total_flow_out) > error_threshold:
                        cat_out_dev[cat] = True
                        msg = f"{prefix}   Category out flow != total out flow for equipment {equipment}, category {cat}, in shift {shift}: Total: {total_flow_out:.2f}, catgory flow: {cat_sum_out}"
                        if fail_on_error:
                            raise Exception(msg)
                        print(msg)



