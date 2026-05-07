import threading
from datetime import datetime, timedelta, date
from typing import Sequence, Mapping

import numpy as np
import picos as pc

from dynreact.base.InterruptedException import InterruptedException
from dynreact.base.model import LongTermTargets, StorageLevel, EquipmentAvailability, MidTermTargets, Site, Lot
from dynreact.ltp.LtpException import LtpException
from dynreact.ltp.LtpUtils import LtpUtils
from dynreact.ltp.ShiftAllocator import ShiftAllocator


# TODO timeout via run parameters(?)
# TODO report results of optimization (optimal solution found? Problem feasible? Option to continue; etc.)
class LtpInstance:

    _zero_delta: timedelta = timedelta(days=0)

    def __init__(self, id0: str, site: Site, structure: LongTermTargets, initial_storage_levels: dict[str, StorageLevel]|None=None,
                 shifts: list[tuple[datetime, datetime]]|None=None, plant_availabilities: dict[int, EquipmentAvailability] | None=None,
                 frozen_lots: dict[int, Sequence[Lot]] | None = None):
        self._id = id0
        self._site = site
        self._structure = structure
        self._initial_storage_levels = initial_storage_levels
        self._shifts = shifts
        self._availabilities = plant_availabilities
        self._frozen_lots = frozen_lots
        # state
        self._interrupted = threading.Event()
        self._done = threading.Event()

    def start(self) -> tuple[MidTermTargets, list[dict[str, StorageLevel]]]:
        model, storages, storages_to_equipment, equipment_to_storages, objective_components, frozen_horizons = self._build_model()
        # print("  MODEL", model)
        self._check_interrupted()
        # FIXME
        print("  MODEL built successfully, now starting the optimization")
        solution: pc.Solution = model.solve(solver="ecos", primals=None, max_iterations=250)  # default maxit: 100
        # FIXME
        print("   OPTIMIZATION DONE, status ", solution.claimedStatus, "time", solution.searchTime, solution.lastStatus)
        print("    Objective components", {key: exp.value for key, exp in objective_components.items()} )
        #print("    Shift by equipment", {e: exp.value for e, exp in shifts_by_equipment.items()})
        classes_cnt = sum(len(cat.classes) for cat in self._site.material_categories)
        storage_levels = {stg: level.np2d for stg, level in storages.items()}
        storages_to_equipment_flow = {stg: {key: val.np2d for key, val in dct.items()} for stg, dct in storages_to_equipment.items()}
        equipment_to_storages_flow = {e: {key: val.np2d for key, val in dct.items()} for e, dct in equipment_to_storages.items()}
        ## store results for later evaluation
        # LtpUtils.store_results(self._site, self._structure, self._shifts, self._availabilities,
        #                       storage_levels, storages_to_equipment_flow, equipment_to_storages_flow, "ltp_result.json")
        # return LtpUtils.to_results(self._site, self._shifts, self._structure, storages, storages_to_equipment, equipment_to_storages)
        shifts_allocator = ShiftAllocator(self._site, self._structure, self._shifts, self._availabilities, storage_levels,
                                          equipment_to_storages_flow, storages_to_equipment_flow, frozen_horizons=frozen_horizons)
        return shifts_allocator.run()

    def interrupt(self) -> bool:
        if not self._done.is_set():
            self._interrupted.set()
            return True
        return False

    def is_interrupted(self) -> bool:
        return not self._done.is_set() and self._interrupted.is_set()

    def is_done(self) -> bool:
        return self._done.is_set()

    def _check_interrupted(self):
        if self._interrupted.is_set():
            raise InterruptedException(f"LongTermPlanning interrupted: {self._id}")

    def _determine_frozen_ranges(self) -> dict[int, datetime]|None:
        frozen_lots = self._frozen_lots
        if frozen_lots is None:
            return None
        lot_without_endtime = next((lt for lots in frozen_lots.values() for lt in lots if lt.end_time is None or lt.start_time is None), None)
        if lot_without_endtime is not None:
            raise LtpException(f"Lot without start and/or end time set: {lot_without_endtime.id}")
        lot_without_weight = next((lt for lots in frozen_lots.values() for lt in lots if lt.weight is None), None)
        if lot_without_weight is not None:
            raise LtpException(f"Lot without weight: {lot_without_weight.id}")
        start_time = self._structure.period[0]
        end_time = self._structure.period[1]
        frozen_lots = {e: [lt for lt in lots if lt.end_time > start_time] for e, lots in frozen_lots.items()}
        frozen_horizons = {e: max(lt.end_time for lt in lots) for e, lots in frozen_lots.items() if len(lots) > 0}
        return frozen_horizons if len(frozen_horizons) > 0 else None


    def _build_model(self) -> tuple[pc.Problem, dict[str, pc.RealVariable], dict[str, dict[int, pc.RealVariable]], dict[int, dict[str, pc.RealVariable]], dict[str, pc.expressions.Expression], dict[int, datetime]|None]:
        """
        Returns:
                the model, dict of storage variables, dict of [storage->equipment] flow variables, dict of [equipment->storage] flow variables, objective components, frozen horizons per equipment (if applicable)
        """
        frozen_horizons: dict[int, datetime]|None = self._determine_frozen_ranges()
        # TODO config
        alpha_storage_level_input = 0.01
        alpha_storage_level = 1
        alpha_class_target = 10
        # 0.1 too low, 1 better but still too low, 10 ok, though still not perfect [negative values occur]
        alpha_storage_level_material_final = 10
        alpha_storage_level_material = 0.1

        material_categories: dict[str, list[str]] = {cat.id: [clz.id for clz in cat.classes] for cat in self._site.material_categories}
        # flat material classes array
        material_classes: list[str] = [clz for classes in material_categories.values() for clz in classes]
        classes_cnt = len(material_classes)
        shifts = self._shifts
        num_shifts = len(shifts)
        num_storages = len(self._site.storages)
        num_equipment = len(self._site.equipment)
        total_amount = self._structure.total_production
        flow_problem = pc.Problem()
        # represent the storage filling level
        storages: dict[str, pc.RealVariable] = {}
        # represent the equipment capacity usage, values between 0 and 1
        equipments: dict[int, pc.RealVariable] = {}
        # represents the material flow from storages to equipments
        storage_to_equipment: dict[str, dict[int, pc.RealVariable]] = {}
        # represents the material flow from equipments to storages
        equipment_to_storage: dict[int, dict[str, pc.RealVariable]] = {}
        hours_per_shift = (self._shifts[0][-1] - self._shifts[0][0]).total_seconds()/3600
        storage_material_constraints: dict[str, Sequence[str]] = {}
        # shifts_by_equipment: dict[int, pc.expressions.Expression] = {}  # shifts are optimized in a second step
        # outer key: storage id, inner key: material class
        initial_storage_levels: dict[str, dict[str, float]] = {}
        for stg in self._site.storages:
            if stg.name_short == "DONE":  # xxx
                continue
            if stg.material_constraints is not None and len(stg.material_constraints.excluded) > 0:
                storage_material_constraints[stg.name_short] = stg.material_constraints.excluded
            # represents the filling level of the storage
            x_storage = pc.RealVariable(name=f"x_store_{stg.name_short}", shape=(classes_cnt + 1, num_shifts + 1), lower=0.0, upper=1.0)
            # initial filling levels for storages
            initial_storage_level = 0.5
            indices_covered: set[int] = set()
            stg_initial = {}
            initial_storage_levels[stg.name_short] = stg_initial
            if stg.name_short in self._initial_storage_levels:
                init: StorageLevel = self._initial_storage_levels[stg.name_short]
                initial_storage_level = init.filling_level
                if init.material_levels is not None and len(init.material_levels) > 0:
                    for mat, level in init.material_levels.items():
                        mat_idx = material_classes.index(mat)
                        flow_problem.require(x_storage[mat_idx, 0] == level)
                        stg_initial[mat] = level
                        indices_covered.add(mat_idx)
                    for mat_idx, mat in enumerate(material_classes):
                        if mat_idx not in indices_covered:
                            flow_problem.require(x_storage[mat_idx, 0] == 0.)
                            stg_initial[mat] = 0
            if len(indices_covered) == 0 and len(material_classes) > 0:
                mat_start_idx = 0
                for cat in self._site.material_categories:
                    cat_cl = len(cat.classes)
                    shares = [cl.default_share if cl.default_share is not None else 1. if cl.is_default else 0. for cl in cat.classes]
                    for idx, share in enumerate(shares):
                        flow_problem.require(x_storage[mat_start_idx + idx, 0] == share * initial_storage_level)
                        stg_initial[cat.classes[idx].id] = share * initial_storage_level
                    mat_start_idx += cat_cl
            # Init the overall material variable to the initial storage level
            flow_problem.require(x_storage[-1, 0] == initial_storage_level)
            # material constraints
            LtpUtils._set_material_constraints(flow_problem, x_storage, material_categories)
            storages[stg.name_short] = x_storage
        # Note: this one is in weight relative to the target production, whereas the other storage variables are relative filling levels
        x_storage_done = pc.RealVariable(name="x_store_DONE", shape=(classes_cnt + 1, num_shifts + 1), lower=0.0)
        LtpUtils._set_material_constraints(flow_problem, x_storage_done, material_categories)
        storages["DONE"] = x_storage_done
        # initial value for the DONE storage = 0
        flow_problem.require([x_storage_done[cl, 0] == 0.0 for cl in range(classes_cnt+1)])
        self._check_interrupted()
        for eq in self._site.equipment:
            if eq.id not in self._availabilities:
                continue
            hours_by_shift: list[float] = LtpUtils._availability_to_hours(shifts, self._availabilities[eq.id])
            limited_shifts = {shift_idx: h for shift_idx, h in enumerate(hours_by_shift) if h < hours_per_shift}
            excluded_material: Sequence[str]|None = eq.material_constraints.excluded if eq.material_constraints is not None and len(eq.material_constraints.excluded) > 0 else None
            prod_capacity = eq.throughput_capacity * hours_per_shift
            eq_lots: Sequence[Lot]|None = self._frozen_lots.get(eq.id) if frozen_horizons is not None else None
            # For each lot we need to determine its share per shift. Outer keys: lot ids, inner keys: shift index, value: share (0-1)
            shift_shares_by_lot: dict[str, dict[int, float]]|None = {lot.id: LtpInstance._shift_shares_for_lot((lot.start_time, lot.end_time), shifts, hours_by_shift) for lot in eq_lots} \
                    if eq_lots is not None else None
            # constraints for flow into and out of equipment
            in_flow = None
            if eq.storage_in is not None:
                u_flow = pc.RealVariable(name=f"u_flow_stg_eq_{eq.storage_in}_{eq.id}", shape=(classes_cnt + 1, num_shifts), lower=0.0, upper=prod_capacity)
                LtpUtils._set_material_constraints(flow_problem, u_flow, material_categories)
                if frozen_horizons is not None and eq.id in frozen_horizons:
                    frozen_horizon: datetime = frozen_horizons[eq.id]
                    lots: Sequence[Lot] = self._frozen_lots[eq.id]
                    for shift_idx, shift in enumerate(shifts):
                        if shift[0] >= frozen_horizon:
                            break
                        # constrain the shifts covered by lots already TODO tests for this setting
                        # step 1: determine applicable lots
                        shift_lots = [lt for lt in lots if lt.start_time < shift[1] and lt.end_time > shift[0] and shift_idx in shift_shares_by_lot[lt.id]]
                        if len(shift_lots) == 0:  # no production
                            flow_problem.require(u_flow[-1, shift_idx] == 0)
                            continue
                        # step 2: determine resulting production
                        total_weight = sum(lt.weight * shift_shares_by_lot[lt.id][shift_idx] for lt in shift_lots)
                        # determine if this exceeds the theoretical maximum => then need to reduce
                        max_capacity = eq.throughput_capacity * hours_by_shift[shift_idx]  # TODO material-dependent capacity
                        factor = 1
                        if total_weight > max_capacity:
                            total_weight = max_capacity
                            factor = max_capacity / total_weight
                        all_lots_have_mat_info = all(lt.material_weights is not None for lt in shift_lots)
                        partly_covered_shift: bool = shift[1] > frozen_horizon
                        # step 3: set constraints
                        if all_lots_have_mat_info:
                            weight_vector = np.array([sum(lt.material_weights.get(mat, 0.) * shift_shares_by_lot[lt.id][shift_idx] * factor for lt in shift_lots) for mat in material_classes] + [total_weight])
                            if partly_covered_shift:
                                flow_problem.require(u_flow[:, shift_idx] >= weight_vector)
                            else:
                                flow_problem.require(u_flow[:, shift_idx] == weight_vector)
                        else:
                            if partly_covered_shift:
                                flow_problem.require(u_flow[-1, shift_idx] >= total_weight)
                            else:
                                flow_problem.require(u_flow[-1, shift_idx] == total_weight)
                if eq.storage_in not in storage_to_equipment:
                    storage_to_equipment[eq.storage_in] = {}
                storage_to_equipment[eq.storage_in][eq.id] = u_flow
                in_flow = u_flow
                # shift constraints
                if len(limited_shifts) > 0:
                    # applied to the full production (class index -1)
                    flow_problem.require([u_flow[-1, shift_idx] <= shift_hours * eq.throughput_capacity for shift_idx, shift_hours in limited_shifts.items()])
                # equipment material constraints
                if excluded_material is not None:
                    flow_problem.require([u_flow[material_classes.index(mat), :] == 0 for mat in excluded_material])
            out_flows = []
            if eq.id not in equipment_to_storage:
                equipment_to_storage[eq.id] = {}
            storages_out = eq.storages_out or ("DONE",)
            for stg in storages_out:
                out_mat_classes: Sequence[str]|None = None
                if isinstance(stg, Mapping):
                    out_mat_classes = next(iter(stg.values()))
                    stg = next(iter(stg.keys()))
                u_flow = pc.RealVariable(name=f"u_flow_eq_stg_{eq.id}_{stg}", shape=(classes_cnt + 1, num_shifts), lower=0.0, upper=prod_capacity)
                LtpUtils._set_material_constraints(flow_problem, u_flow, material_categories)
                forbidden_classes = None
                if out_mat_classes is not None:  # only specific material is allowed to flow via this edge
                    affected_cats: list[str] = [cat for cat, cat_classes in material_categories.items() if any(cl in cat_classes for cl in out_mat_classes)]
                    forbidden_classes = [cl for cat, cat_classes in material_categories.items() if cat in affected_cats for cl in cat_classes if cl not in out_mat_classes]
                # storage material constraints
                if stg in storage_material_constraints:
                    forbidden_classes = forbidden_classes or []
                    forbidden_classes = forbidden_classes + [mat for mat in storage_material_constraints[stg] if mat not in forbidden_classes]
                if forbidden_classes is not None:
                    flow_problem.require([u_flow[material_classes.index(mat), :] == 0 for mat in forbidden_classes])
                equipment_to_storage[eq.id][stg] = u_flow
                out_flows.append(u_flow)
            # in flow == out flow, per mat class and shift
            #flow_problem.require([in_flow[cl, sh] == pc.sum([fl[cl, sh] for fl in out_flows]) for cl in range(classes_cnt) for sh in range(num_shifts)])
            sum_flow_out = pc.sum(out_flows) if len(out_flows) > 1 else out_flows[0]
            flow_problem.require(in_flow == sum_flow_out)
        input_storages: list[str] = []
        self._check_interrupted()
        # constraints for flow into and out of storage
        for stg in self._site.storages:
            if stg.name_short == "DONE":
                continue
            in_flow = [entries[stg.name_short] for entries in equipment_to_storage.values() if stg.name_short in entries]
            out_flow = list(storage_to_equipment[stg.name_short].values())
            out_flow = pc.sum(out_flow) if len(out_flow) > 1 else out_flow[0]
            level = storages[stg.name_short]
            capacity = stg.capacity_weight
            flow_problem.require(out_flow <= capacity * level[:, :-1])
            if len(in_flow) == 0:
                input_storages.append(stg.name_short)
                flow_problem.require(capacity * level[:, 1:] >= capacity * level[:, :-1] - out_flow)  # nothing gets lost
                # Material that is not scheduled for the month must not enter the initial storage(s)  (??)
                missing_material = [mat for mat, target in self._structure.production_targets.items() if target <= 0]
                if self._frozen_lots is not None and len(missing_material) > 0:
                    # Filter for material not scheduled in any frozen lots
                    missing_material = [mat for mat in missing_material if all(next((lt for lt in lots if
                            lt.material_weights is not None and lt.material_weights.get(mat, 0) > 0), None) is None for lots in self._frozen_lots.values())]
                if len(missing_material) > 0:  # we cannot change the start constraint
                    flow_problem.require([out_flow[material_classes.index(mat), :] == 0 for mat in missing_material])
                    flow_problem.require([level[material_classes.index(mat), 1:] == initial_storage_levels[stg.name_short][mat] for mat in missing_material])
            else:
                in_flow = pc.sum(in_flow) if len(in_flow) > 1 else in_flow[0]
                #flow_problem.require([capacity * level[:, sh + 1] == capacity * level[:, sh] + in_flow[:, sh] - out_flow[:, sh] for sh in range(num_shifts)])
                flow_problem.require(capacity * level[:, 1:] == capacity * level[:, :-1] + in_flow - out_flow)
        in_flow_done = [entries["DONE"] for entries in equipment_to_storage.values() if "DONE" in entries]
        in_flow_done = pc.sum(in_flow_done) if len(in_flow_done) > 1 else in_flow_done[0]
        if len(in_flow_done) > 0:
            level = storages["DONE"]
            #flow_problem.require([total_amount * level[cl, sh + 1] == total_amount * level[cl, sh] + in_flow_done[cl, sh] for cl in range(classes_cnt) for sh in range(num_shifts)])
            flow_problem.require([total_amount * level[:, sh + 1] == total_amount * level[:, sh] + in_flow_done[:, sh] for sh in range(num_shifts)])
        self._check_interrupted()
        # objectives per material class and overall
        material_class_targets: dict[str, float] = self._structure.production_targets
        objective_components: dict[str, pc.expressions.Expression] = {}
        ## to be interpreted relative to total_amount planned
        mat_targets_arr = np.array([material_class_targets.get(clzz, 0.0) / total_amount for clzz in material_classes] + [1.])
        clzz_amount = alpha_class_target / max(classes_cnt, 1) * pc.Norm(x_storage_done[:, -1] - mat_targets_arr)
        objective_components["classes_amount"] = clzz_amount
        objective = clzz_amount
        #main_objective = pc.Norm(x_storage_done[-1, -1] - 1)
        #objective_components["total_amount"] = main_objective
        #objective = main_objective
        #for idx, clzz in enumerate(material_classes):
        #    clzz_amount = alpha_class_target/classes_cnt * pc.Norm(x_storage_done[idx, -1] - material_class_targets.get(clzz, 0.0)/total_amount)
        #    objective_components["classes_amount"] = clzz_amount if "classes_amount" not in objective_components else objective_components["classes_amount"] + clzz_amount
        #    objective += clzz_amount
        for stg, stg_level in storages.items():
            # print("   Now setting storage for ", stg, " is input storage ", stg in input_storages)
            if stg in input_storages:
                # keep the initial storage level at the minimum
                init_storage_level = alpha_storage_level_input/num_shifts * pc.Norm(stg_level[-1, :])
                objective_components["input_storage_level"] = init_storage_level
                objective += init_storage_level
            elif stg != "DONE":
                # keep other storages around half filled (TODO: configurable?)
                stg_level_objective = alpha_storage_level/num_storages * pc.Norm(stg_level[-1, :] - 0.5)
                objective_components["stg_levels"] = stg_level_objective if "stg_levels" not in objective_components else objective_components["stg_levels"] + stg_level_objective
                objective += stg_level_objective
                # after the last shift, aim for an even material distribution in the storages
                mat_start_idx = 0
                mat_constraints: Sequence[str]|None = storage_material_constraints.get(stg)
                targets: dict[str, float] = self._structure.production_targets
                for cat, classes in material_categories.items():
                    if mat_constraints is not None:
                        classes = [c for c in classes if c not in mat_constraints and c in targets]
                    for c in classes:
                        target_level = targets[c]/total_amount/2
                        # after the final shift aim for an evenly distributed mix of materials in the storages
                        stg_level_final_class_objective = alpha_storage_level_material_final / classes_cnt/num_storages * pc.max([target_level - stg_level[material_classes.index(c), -1], 0])
                        objective_components["stg_levels_class_final"] = stg_level_final_class_objective if "stg_levels_class_final" not in objective_components else objective_components["stg_levels_class_final"] +stg_level_final_class_objective
                        objective += stg_level_final_class_objective
                        # try to keep relative material content in storages above 1/8th of the share of overall production
                        # slowing down things... prefer the vectorized exp form
                        # stg_level_class_not_none = alpha_storage_level_material / classes_cnt / num_storages / num_shifts * pc.sum([pc.max([target_level/4 - stg_level[material_classes.index(c), j], 0]) for j in range(1, num_shifts+1)])
                        #stg_level_class_not_none = alpha_storage_level_material / classes_cnt / num_storages / num_shifts * pc.exp(target_level/4 * np.ones(shape=(1, num_shifts)) - stg_level[material_classes.index(c), 1:])
                        #objective_components["stg_levels_class_not_none"] = stg_level_class_not_none if "stg_levels_class_not_none" not in objective_components else objective_components["stg_levels_class_not_none"] + stg_level_class_not_none
                        #objective += stg_level_class_not_none
        flow_problem.set_objective("min", objective)
        return flow_problem, storages, storage_to_equipment, equipment_to_storage, objective_components, frozen_horizons

    @staticmethod
    def _shift_shares_for_lot(lot_period: [datetime, datetime], shifts: Sequence[tuple[datetime, datetime]], working_hours_by_shift: Sequence[float]) -> dict[int, float]:
        """Determines how a lot that spans multiple shifts must be distributed to those shifts"""
        # the third argument is the number of hours actually applicable to the lot
        overlapping_shifts: list[tuple[int, tuple[datetime, datetime], float]] = [(shift_idx, shift, (min(lot_period[1], shift[1]) - max(lot_period[0], shift[0]))/(shift[1] - shift[0]) * hours)
                                                for shift_idx, (shift, hours) in enumerate(zip(shifts, working_hours_by_shift)) if shift[0] < lot_period[1] and shift[1] > lot_period[0] and hours > 0]
        if len(overlapping_shifts) == 0:
            return {}
        total_hours = sum(hours for _, __, hours in overlapping_shifts)
        share_per_shift = {idx: hours/total_hours for idx, __, hours in overlapping_shifts}
        return share_per_shift


