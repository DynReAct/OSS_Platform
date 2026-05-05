import random
from datetime import datetime
from typing import Sequence

import numpy as np

from dynreact.base.model import LongTermTargets, Site, StorageLevel, EquipmentAvailability, Process, Equipment, \
    MaterialClass
from dynreact.ltp.LtpException import LtpException
from dynreact.ltp.LtpUtils import LtpUtils


# FIXME the current LongTermPlanning results structure is insufficient.
#  * equipment production is not broken down into material classses
class ShiftAllocator:

    def __init__(self,
                 site: Site, structure: LongTermTargets,
                 #initial_storage_levels: dict[str, StorageLevel],
                 shifts: list[tuple[datetime, datetime]], plant_availabilities: dict[int, EquipmentAvailability],
                 #results: MidTermTargets,
                 storage_levels: dict[str, np.ndarray],
                 #equipment_targets: dict[int, np.ndarray],  # shape of all arrays: (num_classes + 1, num shifts), where num classes = number material classes
                 equipment_to_storages: dict[int, dict[str, np.ndarray]],
                 storages_to_equipment: dict[str, dict[int, np.ndarray]],
                 rand_seed: int|None = None
                 ):
        self._site = site
        self._targets = structure
        #self._initial_storage_levels = initial_storage_levels
        self._shifts = shifts
        self._plant_availabilities: dict[int, EquipmentAvailability] = plant_availabilities
        #self._results = results
        material_categories: dict[str, list[str]] = {cat.id: [clz.id for clz in cat.classes] for cat in self._site.material_categories}
        # flat material classes array
        material_classes: list[str] = [clz for classes in material_categories.values() for clz in classes]
        self._material_classes = material_classes
        self._equipment_targets: dict[int, np.ndarray] = {eq: sum(dct.values(), start=np.zeros(shape=(len(material_classes)+1, len(shifts)))) for eq, dct in equipment_to_storages.items()}
        self._equipment_to_storages = equipment_to_storages
        self._storages_to_equipment = storages_to_equipment
        self._storage_levels = storage_levels
        self._input_storages = [s for s in (stg.name_short for stg in site.storages) if not any(s in e.storages_out for e in site.equipment)]

        # results and intermediate results
        self._storage_levels_final: dict[str, np.ndarray] = {stg: np.copy(level) for stg, level in storage_levels.items()}   # shape: (num_classes + 1, num_shifts + 1)
        self._storages_to_equipment_final: dict[str, dict[int, np.ndarray]] = {}  # shape: (num_classes + 1, num_shifts)
        self._equipment_to_storages_final: dict[int, dict[str, np.ndarray]] = {}  # shape: (num_classes + 1, num_shifts)
        self._storage_in_flows_final: dict[str, np.ndarray] = {stg: np.zeros(shape=(len(material_classes)+1, len(shifts))) for stg in storage_levels.keys()}
        self._random = random.Random(x=rand_seed)

    def run(self):
        processes = self._site.processes
        procs_done = set()
        procs_open = [p for p in processes]
        while len(procs_open) > 0:
            next_proc = next((p for p in procs_open if not any(p2.next_steps is not None and p.name_short in p2.next_steps for p2 in procs_open)), None)
            if next_proc is None:
                raise Exception(f"Failed to find next connected process step among {[p.name_short for p in procs_open]}")
            procs_open.remove(next_proc)
            procs_done.add(next_proc.name_short)
            # FIXME
            print(f" PROCESS allocation starting {next_proc.name_short}")
            self._allocate_process(next_proc)
            # FIXME
            print(f"   PROCESS allocation DONE!")
        return LtpUtils.to_results(self._site, self._shifts, self._targets, self._storage_levels_final, self._storages_to_equipment_final, self._equipment_to_storages_final)

    def _allocate_process(self, process: Process):
        proc = process.name_short
        shifts = self._shifts
        material_classes = self._material_classes
        classes_cnt = len(material_classes)
        num_shifts = len(shifts)
        hours_per_shift = (shifts[0][-1] - shifts[0][0]).total_seconds() / 3600
        equipment_targets: dict[int, np.ndarray] = self._equipment_targets
        #results: MidTermTargets = self._results
        equipment_objects: list[Equipment] = list(self._site.get_process_equipment(proc, do_raise=True))
        equipment_ids: Sequence[int] = [e.id for e in equipment_objects]
        storages_in_ids = set([e.storage_in for e in equipment_objects if e.storage_in is not None])
        storages_out_ids: set[str] = set([stg if isinstance(stg, str) else next(iter(stg.keys())) for e in equipment_objects if e.storages_out is not None for stg in e.storages_out])
        if len(storages_in_ids) == 0:
            raise LtpException(f"No incoming storages found for process {proc}")
        if len(storages_out_ids) == 0:
            raise LtpException(f"No outgoing storages found for process {proc}")
        storages_in = {s.name_short: s for s in (self._site.get_storage(s, do_raise=True) for s in storages_in_ids)}
        storages_out = {s.name_short: s for s in (self._site.get_storage(s, do_raise=True) for s in storages_out_ids)}
        all_storage_ids = list(storages_in.keys()) + list(storages_out.keys())
        storage_levels: dict[str, np.ndarray] = \
            {s: self._storage_levels_final[s] if s in self._storage_levels_final else ShiftAllocator2._levels_for_storage(s, self._storage_levels, material_classes) for s in all_storage_ids}
        # key 1: equipment id, index: mat class idx
        total_equipment_flows: dict[int, list[float]] = {eq: [np.sum(flow[class_idx, :]) for class_idx in range(classes_cnt+1)] for eq, flow in equipment_targets.items()}
        allocated_equipment_flows: dict[int, list[float]] = {eq: [0. for _ in targets] for eq, targets in total_equipment_flows.items()}
        equipment_to_storages = {eq: {stg: np.zeros(shape=flow.shape, dtype=np.float64) for stg, flow in dct.items()} for eq, dct in self._equipment_to_storages.items() if eq in equipment_ids}
        storages_to_equipment = {stg: {eq: np.zeros(shape=flow.shape, dtype=np.float64) for eq, flow in dct.items() if eq in equipment_ids} for stg, dct in self._storages_to_equipment.items() if any(eq in equipment_ids for eq in dct.keys())}
        # array shape (num_classes + 1, 1)  # TODO append those to the final storage levels(?)
        storage_in_levels: dict[str, np.ndarray] = {s: self._storage_levels_final[s][:, 0] if s in self._storage_levels_final else self._storage_levels[s][:, 0] for s in storages_in_ids if s in self._storage_in_flows_final}  # ShiftAllocator2._levels_for_storage(s, self._storage_levels, material_classes)[:, 0] for s in storages_in_ids}
        storage_out_levels: dict[str, np.ndarray] = {s: self._storage_levels_final[s][:, 0] if s in self._storage_levels_final else self._storage_levels[s][:, 0] for s in storages_out_ids}  # ShiftAllocator2._levels_for_storage(s, self._storage_levels, material_classes)[:, 0] for s in storages_out_ids}
        equipment_production_delta: dict[int, np.ndarray] = {eq: np.zeros(shape=(classes_cnt+1, )) for eq in equipment_ids}
        final_storage_levels: dict[str, np.ndarray] = {s: np.zeros(shape=(classes_cnt+1, num_shifts+1)) for s in list(storages_in_ids) + (["DONE"] if "DONE" in storages_out_ids else [])}
        for stg in storages_in_ids:
            final_storage_levels[stg][:, 0] = storage_in_levels[stg]
        if "DONE" in storages_out_ids and "DONE" in self._storage_levels_final:
            final_storage_levels["DONE"][:, 0] = self._storage_levels_final["DONE"][:, 0]
        shift_zero = np.zeros(shape=(classes_cnt+1, ))
        for shift_idx, shift in enumerate(range(num_shifts)):
            equipment_flows: dict[int, np.ndarray] = {e: shift_zero for e in equipment_ids}
            storage_level_corrections: dict[str, np.ndarray] = {}  # memorize outgoing storage material allocated to some equipment to ensure that storages do not run empty
            self._random.shuffle(equipment_objects)    #  shuffle equipment order in each step, to avoid preferring the same equipment all the time
            for equipment in equipment_objects:
                if equipment.id not in self._plant_availabilities:
                    continue
                hours_by_shift: list[float] = LtpUtils._availability_to_hours(shifts, self._plant_availabilities[equipment.id])
                limited_shifts = {shift_idx: h for shift_idx, h in enumerate(hours_by_shift) if h < hours_per_shift}
                excluded_material: Sequence[str] | None = equipment.material_constraints.excluded if equipment.material_constraints is not None and len(equipment.material_constraints.excluded) > 0 else None
                prod_capacity = equipment.throughput_capacity * hours_per_shift
                target_prod: np.ndarray = self._equipment_targets[equipment.id][:, shift_idx]
                shift_targets = equipment_production_delta[equipment.id] + target_prod
                equipment_production_delta[equipment.id] += target_prod
                # the target production may become negative due to greater previous production for some materials
                if any(t < 0 for t in shift_targets):
                    problem_materials = [mat for idx, mat in enumerate(material_classes) if shift_targets[idx] < 0]
                    problem_cats = [cat for cat in self._site.material_categories if
                                    any(mat.id in problem_materials for mat in cat.classes)]
                    for cat in problem_cats:
                        materials: list[int] = [material_classes.index(cl.id) for cl in cat.classes]
                        total_amount = sum(max(0., float(shift_targets[mat])) for mat in materials)
                        factor = shift_targets[-1] / total_amount
                        for mat in materials:
                            old_prod = shift_targets[mat]
                            new_prod = old_prod * factor if old_prod >= 0 else 0.
                            shift_targets[mat] = new_prod
                            equipment_production_delta[equipment.id][mat] += (new_prod - old_prod)
                # TODO check that last shift is actually active => per equipment, pre-determine the last active shift! (But the capacity plays a role too!)
                if prod_capacity <= 1e-4 or shift_targets[-1] <= 1e-4 or (shift_targets[-1] < prod_capacity/2 and shift_idx < num_shifts-1):
                    # do not schedule a shift, unless at the very end
                    final_shift_targets = shift_zero
                else:
                    scaling_factor = prod_capacity / shift_targets[-1]
                    final_shift_targets: np.ndarray = scaling_factor * shift_targets
                    stg_cap = storages_in[equipment.storage_in].capacity_weight
                    # check there is enough material in the incoming storage => needs to be synchronized between equipments
                    if equipment.storage_in in storage_in_levels:
                        storage_level = storage_in_levels[equipment.storage_in]
                        if equipment.storage_in in storage_level_corrections:
                            storage_level = storage_level - storage_level_corrections[equipment.storage_in]
                        #if storage_level[-1] * stg_cap < prod_capacity:  # use all available material (but handle material constraints)
                        if excluded_material is not None:
                            available_mat_per_cat: dict[str, float] = {cat.id: sum(storage_level[material_classes.index(mat.id)] for mat in cat.classes
                                                                                   if mat.id in material_classes and mat.id not in excluded_material) for cat in self._site.material_categories}
                            min_available = min(available_mat_per_cat.values())
                        else:
                            min_available = storage_level[-1]
                        if min_available * stg_cap < prod_capacity / 2 and shift_idx < num_shifts-1:
                            # do not schedule a shift, unless at the very end
                            continue
                        if min_available * stg_cap < prod_capacity:  # use all available material
                            final_shift_targets = min_available * stg_cap / prod_capacity * final_shift_targets
                        if any(final_shift_targets[idx] > storage_level[idx] * stg_cap * 1.025 for idx in range(len(material_classes))):
                            # there is not enough material in storage
                            problem_materials = [mat for idx, mat in enumerate(material_classes) if (excluded_material is None or mat not in excluded_material) and
                                                 final_shift_targets[idx] > storage_level[idx] * stg_cap * 1.025]
                            problem_cats = [cat for cat in self._site.material_categories if any(mat.id in problem_materials for mat in cat.classes)]
                            for cat in problem_cats:
                                # both arrays must be non-empty here
                                cat_mat_prob: list[tuple[int, MaterialClass]] = [(material_classes.index(mat.id), mat) for mat in cat.classes if mat.id in problem_materials]
                                cat_mat_ok: list[tuple[int, MaterialClass]] = [(material_classes.index(mat.id), mat) for mat in cat.classes if mat.id not in problem_materials]
                                total_fraction_distributed = sum(final_shift_targets[idx]/stg_cap for (idx, mat) in cat_mat_ok)
                                target_fraction = final_shift_targets[-1] / stg_cap
                                for idx, mat in cat_mat_prob:
                                    final_shift_targets[idx] = storage_level[idx] * stg_cap
                                    total_fraction_distributed += storage_level[idx]
                                # try to fill the gap with the default class first
                                if total_fraction_distributed < target_fraction - 1e-3:
                                    default_class = next(((idx, mat) for idx, mat in cat_mat_ok if mat.is_default), None)
                                    if default_class is not None:
                                        idx = default_class[0]
                                        available: float = storage_level[idx] - final_shift_targets[idx]/stg_cap
                                        if available > 0:
                                            to_add = min([available, target_fraction-total_fraction_distributed])
                                            total_fraction_distributed += to_add
                                            final_shift_targets[idx] += to_add * stg_cap
                                missing_fraction = target_fraction - total_fraction_distributed
                                if missing_fraction > 1e-3:
                                    cat_mat_ok: [(idx, mat) for idx, mat in cat_mat_ok if not mat.is_default]
                                    available_fractions = [storage_level[idx] - final_shift_targets[idx]/stg_cap for idx, mat in cat_mat_ok]
                                    wanted_per_class = missing_fraction/len(available_fractions)
                                    fractions_to_add = [min([available, wanted_per_class]) for available in available_fractions]
                                    total_fraction_distributed += sum(fractions_to_add)
                                    for idx2, (idx, mat) in enumerate(cat_mat_ok):
                                        final_shift_targets[idx] += fractions_to_add[idx2] * stg_cap
                                    missing_fraction = target_fraction - total_fraction_distributed
                                    if missing_fraction > 1e-3:
                                        for idx, mat in cat_mat_ok:
                                            available = min([storage_level[idx] - final_shift_targets[idx]/stg_cap, missing_fraction])
                                            if available > 0:
                                                total_fraction_distributed += available
                                                final_shift_targets[idx] += available * stg_cap
                                                missing_fraction = missing_fraction - available
                                                if missing_fraction <= 1e-3:
                                                    break
                    equipment_flows[equipment.id] = final_shift_targets
                    storage_level_corrections[equipment.storage_in] = storage_level_corrections[equipment.storage_in] + (final_shift_targets / stg_cap) if equipment.storage_in in storage_level_corrections \
                            else final_shift_targets / stg_cap
                    eq_storages_out = equipment.storages_out
                    initial_out_flows: dict[str, np.ndarray] = {stg: flow[:, shift_idx] for stg, flow in self._equipment_to_storages[equipment.id].items()}
                    # remove actually scheduled production from the delta!
                    equipment_production_delta[equipment.id] = equipment_production_delta[equipment.id] - final_shift_targets
                    if len(initial_out_flows) == 1:
                        equipment_to_storages[equipment.id][next(iter(initial_out_flows.keys()))][:, shift_idx] = final_shift_targets
                    else:  # distribute to storages
                        for mat_idx in range(classes_cnt+1):
                            initial_mat_flows: dict[str, float] = {stg: flow[mat_idx] for stg, flow in initial_out_flows.items()}
                            total_initial_flow = sum(initial_mat_flows.values())
                            shares: dict[str, float] = {stg: flow/total_initial_flow if flow > total_initial_flow/1e4 else 0 for stg, flow in initial_mat_flows.items()}
                            for stg, share in shares.items():
                                equipment_to_storages[equipment.id][stg][mat_idx, shift_idx] = share * final_shift_targets[mat_idx]
            for stg in storages_out_ids:  # set outgoing storage levels
                in_flow = sum((equipment_to_storages[eq][stg][:, shift_idx] for eq in equipment_ids), start=shift_zero)
                if stg != "DONE":
                    out_flow_continuous = sum((flow[:, shift_idx] for flow in self._storages_to_equipment[stg].values()), start=shift_zero)
                    in_flow = in_flow/storages_out[stg].capacity_weight
                    new_storage_level = storage_out_levels[stg] + in_flow - out_flow_continuous
                else:
                    new_storage_level = storage_out_levels[stg] + in_flow
                new_storage_level += self._storage_in_flows_final[stg][:, shift_idx]  # if storage receives input from multiple process stages
                self._storage_in_flows_final[stg][:, shift_idx] += in_flow
                storage_out_levels[stg] = new_storage_level
                if stg in final_storage_levels:
                    final_storage_levels[stg][:, shift_idx + 1] = new_storage_level
            for stg in storages_in_ids:  # set incoming storage levels
                applicable_equipments: list[int] = [e.id for e in equipment_objects if e.storage_in == stg]
                out_flow: np.ndarray = sum((equipment_flows[e] for e in applicable_equipments), start=shift_zero) / storages_in[stg].capacity_weight
                for e in applicable_equipments:
                    storages_to_equipment[stg][e][:, shift_idx] = equipment_flows[e]
                if stg in self._input_storages:
                    final_storage_levels[stg][:, shift_idx] = out_flow  # not shift_idx + 1 !
                    continue
                if stg not in self._storages_to_equipment_final:
                    in_flow: np.ndarray = self._storage_in_flows_final[stg][:, shift_idx]
                    # anticipate other outgoing storage connections already
                    other_equipments = {eq: flow[:, shift_idx] for eq, flow in self._storages_to_equipment[stg].items() if eq not in equipment_ids} if stg in self._storages_to_equipment else {}
                    additional_out_flow = sum(other_equipments.values(), start=shift_zero) if len(other_equipments) > 1 else \
                                next(iter(other_equipments.values())) if len(other_equipments) == 1 else shift_zero
                    storage_in_levels[stg] += in_flow - out_flow - additional_out_flow/storages_in[stg].capacity_weight
                else:  # initial flow already anticipated, now consider only diff
                    initial = {eq: flow[:, shift_idx] for eq, flow in self._storages_to_equipment[stg].items() if eq in equipment_ids} if stg in self._storages_to_equipment else {}
                    initial_flow = sum(initial.values(), start=shift_zero) if len(initial) > 1 else next(iter(initial.values())) if len(initial) == 1 else shift_zero
                    diff = initial_flow/storages_in[stg].capacity_weight - out_flow
                    storage_in_levels[stg] += diff
                if stg in final_storage_levels:
                    final_storage_levels[stg][:, shift_idx+1] = storage_in_levels[stg]
        for eq, flow_dict in equipment_to_storages.items():
            self._equipment_to_storages_final[eq] = flow_dict
        for stg, level in final_storage_levels.items():
            self._storage_levels_final[stg] = level
        for stg, flow_dict in storages_to_equipment.items():
            if stg not in self._storages_to_equipment_final:
                self._storages_to_equipment_final[stg] = {}
            for eq, flow in flow_dict.items():
                self._storages_to_equipment_final[stg][eq] = flow
