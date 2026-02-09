from __future__ import annotations
import threading
import time
import traceback
from datetime import timedelta, datetime, timezone
from typing import Sequence

import numpy as np
import pandas as pd
from pydantic import BaseModel

from dynreact.app_config import DynReActSrvConfig
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.ModelUtils import ModelUtils
from dynreact.base.model import Snapshot, ProcessLotCreationSettings, ProductionTargets, EquipmentProduction, Lot, \
    MidTermTargets, PlannedWorkingShift
from dynreact.lots_optimization import FrontendOptimizationListener
from dynreact.state import DynReActSrvState


class ProcessConfig(BaseModel, frozen=True, use_attribute_docstrings=True):
    process: str
    max_duration: timedelta
    max_iterations: int


class BatchConfig(BaseModel, frozen=True, use_attribute_docstrings=True):
    time: datetime
    processes: list[ProcessConfig]
    period: timedelta = timedelta(days=1)
    append_period: bool = False
    """
    If set to true, the period covered will start after the end of the last scheduled lot, per equipment.
    If no shifts are currently planned for some equipment, or all shifts are covered by lots already, then the 
    setting max_equipment_horizon controls how far into the future lots are created at most. 
    """
    max_equipment_horizon: timedelta = timedelta(days=7)
    """
    This setting controls how far into the future lots are created, at most, if append_period is true.
    """
    test: bool = False
    "If set to true, a batch job will be run on startup"


class LotsBatchOptimizationJob:
    """
    TODO timezone handling
    TODO metrics reporting
    TODO use logging over print
    """

    def __init__(self, config: DynReActSrvConfig, state: DynReActSrvState):
        self._thread = None
        self._config = None
        self._runs: int = 0
        self._state = state
        self._snapshot_provider = state.get_snapshot_provider()
        self._stopped = threading.Event()
        if config.lots_batch_config:
            self._config = LotsBatchOptimizationJob._parse_config(config.lots_batch_config.strip())
            self._thread = threading.Thread(name="batch-lot-creation", target=self.run)
            self._thread.daemon = True
            self._thread.start()

    def run(self):
        last_invocation: datetime|None = None
        next_planned_invocation = self._next_invocation(DatetimeUtils.now())
        snaps_provider = self._snapshot_provider
        wait_cnt: int = 0
        while True:
            now = DatetimeUtils.now()
            while next_planned_invocation > now:
                self._stopped.wait((next_planned_invocation-now).total_seconds())
                if self._stopped.is_set():
                    break
                now = DatetimeUtils.now()
            if self._stopped.is_set():
                break
            try:
                start = next_planned_invocation - timedelta(minutes=5) if not (self._config.test and self._runs == 0) else now - timedelta(days=10*365)
                snap = next(snaps_provider.snapshots(start, now, order="desc"))
            except StopIteration:
                if wait_cnt > 30:   # TODO  configurable?
                    prev_next = next_planned_invocation
                    next_planned_invocation = self._next_invocation(now)
                    wait_cnt = 0
                    print(f"Lot creation batch job aborted waiting for snapshot at {prev_next}. Next invocation scheduled for {next_planned_invocation}")
                    continue
                self._stopped.wait(60_000)
                if self._stopped.is_set():
                    break
                wait_cnt += 1
                continue
            wait_cnt = 0
            last_invocation = now
            self._runs += 1
            next_planned_invocation = self._next_invocation(now)
            self._process(snap)
        print("Lot creation batch job exiting")

    def stop(self):
        self._stopped.set()

    def is_active(self) -> bool:
        return self._thread is not None and not self._stopped.is_set()

    def _process(self, snapshot: datetime):
        state = self._state
        snap: Snapshot = state.get_snapshot(snapshot)
        algo = state.get_lots_optimization()
        costs = state.get_cost_provider()
        opti_state = state.get_lot_creator()
        persistence = state.get_results_persistence()
        shifts_provider = state.get_shifts_provider()
        site = state.get_site()
        proc_settings: dict[str, ProcessLotCreationSettings] = site.lot_creation.processes if site.lot_creation is not None else {}
        reference_duration: timedelta = site.lot_creation.duration if site.lot_creation is not None else timedelta(days=1)
        planning_horizon: timedelta = self._config.period
        now = DatetimeUtils.now()
        # this is the generic period, but we'll adapt it further for each process stage depending on the horizon of existing lots
        period = (now, now + planning_horizon)
        lot_size_to_tuple = lambda x: x if x is None else (x.min, x.max)
        all_orders = {o.id: o for o in snap.orders}
        do_append: bool = self._config.append_period
        if do_append:
            period = (now, now + self._config.max_equipment_horizon)
        for proc in self._config.processes:
            if self._stopped.is_set():
                break
            try:
                settings: ProcessLotCreationSettings = proc_settings.get(proc.process) if proc_settings is not None else None
                equipment = site.get_process_equipment(proc.process)
                equipment_ids = [e.id for e in equipment]
                # Here the hours=8 offset in the lot.end_time condition is added to ensure that the last order of an existing lot that is about to be finished can be considered
                existing_lots: list[Lot] = [lot for eq, lots in snap.lots.items() if eq in equipment_ids for lot in lots if   # TODO lot status filter correct?
                        (lot.status > 1 and lot.start_time is not None and lot.end_time is not None and lot.end_time > period[0] - timedelta(hours=8) and lot.start_time < period[1])]
                lots_horizon, equipment_horizons, last_orders = ModelUtils.lots_horizon(equipment_ids, existing_lots)
                if lots_horizon is not None and lots_horizon >= period[1]:
                    continue
                process_period = period
                if not do_append and lots_horizon is not None and lots_horizon > period[0]:
                    process_period = (lots_horizon, period[1])
                elif do_append:
                    start = lots_horizon if lots_horizon is not None and lots_horizon >= period[0] else period[0]
                    end = (max(equipment_horizons.values()) if len(equipment_horizons) > 0 else period[0]) + planning_horizon
                    process_period = (start, min(end, period[1]))
                planning_duration = process_period[1] - process_period[0]
                shifts: dict[int, Sequence[PlannedWorkingShift]] = shifts_provider.load_all(process_period[0], process_period[1], limit=None, equipments=equipment_ids)
                # need a planning period per equipment plus fraction available
                fractions_available: dict[int, float] = {}
                equipment_durations: dict[int, timedelta] = {}
                for plant in equipment_ids:
                    equipment_period = process_period
                    if do_append:
                        if plant in equipment_horizons:
                            horizon = equipment_horizons.get(plant, process_period[0])
                            if horizon >= process_period[1]:
                                continue
                            equipment_period = (equipment_horizons[plant], equipment_horizons[plant] + planning_horizon)
                        else:
                            equipment_period = (period[0], period[0] + planning_horizon)
                    eq_end = equipment_period[1]
                    eq_start = equipment_period[0]
                    equipment_duration = eq_end - eq_start
                    fraction_available = timedelta()
                    eq_shifts = [s for s in shifts.get(plant, tuple()) if s.period[1] > equipment_period[0] and s.period[0] < equipment_period[1]]
                    if len(eq_shifts) > 0:
                        shift_periods = [s.worktime * ((min(s.period[1], eq_end) - max(s.period[0], eq_start))/(s.period[1]-s.period[0])) for s in eq_shifts]
                        fraction_available = sum(shift_periods, start=timedelta()) / equipment_duration
                    fractions_available[plant] = fraction_available
                    equipment_durations[plant] = equipment_duration
                equipment_ids = [e for e, frac in fractions_available.items() if frac > 0]
                if len(equipment_ids) == 0:
                    print(f"No equipment available for process {proc.process} (or available equipment already covered by lots).")
                    continue
                targets_weights0: dict[int, float] = {}
                for e in equipment_ids:
                    # these are targets per shift, or per day, for instance.
                    targets_0 = settings.get_equipment_targets(e) if settings is not None else None
                    equipment_duration = equipment_durations[e]
                    if targets_0 is None or np.isnan(targets_0):
                        capacity_tons_per_hour: float | None = next(eq for eq in equipment if eq.id == e).throughput_capacity
                        if capacity_tons_per_hour is not None:
                            hours: float = equipment_duration.total_seconds()/3_600
                            targets_0 = capacity_tons_per_hour * hours
                    else:
                        duration_factor: float = equipment_duration / reference_duration
                        targets_0 = duration_factor * targets_0
                    if targets_0 is not None and not np.isnan(targets_0):
                        targets_weights0[e] = fractions_available[e] * targets_0
                if len(targets_weights0) == 0:
                    print(f"Batch MTP: no plants available or no configuration found for process {proc.process}")
                    continue
                target_weights: dict[int, EquipmentProduction] = {equ: EquipmentProduction(equipment=equ, total_weight=weight, lot_weight_range=lot_size_to_tuple(settings.get_equipment_lot_sizes(equ)))
                                                                  for equ, weight in targets_weights0.items()}
                # TODO option to set material structure settings
                targets = ProductionTargets(process=proc.process, period=period, target_weight=target_weights)
                ## original method to determine the final amount of material
                # these are the targets for the complete period (not process specific) #
                # sub_targets = {proc.process: [targets]}
                # total_production = sum(t.total_weight for t in targets.target_weight.values())
                # full_targets = MidTermTargets(period=period, sub_periods=[period], production_sub_targets=sub_targets, total_production=total_production, production_targets={})
                # final_targets: ProductionTargets = ModelUtils.mid_term_targets_from_ltp_result(full_targets, proc.process, process_period[0], process_period[1], existing_lots=existing_lots)
                ##
                final_targets = targets
                final_total_production = sum(t.total_weight for t in final_targets.target_weight.values())
                if final_total_production <= 0:  # process already covered completely
                    continue
                # eligible_orders: list[str] = self._snapshot_provider.eligible_orders(snap, proc.process, process_period, method=method)
                fixed_transport_duration = timedelta(hours=4)
                transport_times = lambda eq1, eq2: fixed_transport_duration    # TODO configurable transport times
                eligible_orders: list[str] = self._snapshot_provider.eligible_orders2(snap, proc.process, process_period, equipment=equipment_ids, transport_times=transport_times)
                eligible_orders = [o for o in eligible_orders if o in all_orders and any(e in equipment_ids for e in all_orders[o].allowed_equipment)]
                available_material = sum(all_orders[o].actual_weight for o in eligible_orders)
                if len(eligible_orders) <= 2:   # TODO configurable, maybe also minimum amount of material
                    print(f"Batch lot creation job for process {proc.process} has only {len(eligible_orders)} eligible orders, skipping it.")
                    continue
                if final_total_production > available_material:
                    print(f"Batch lot creation for {proc.process}: available order backlog of {available_material}t does not cover the target of {final_total_production}t.")
                initial_solution, _ = algo.heuristic_solution(proc.process, snap, process_period[1]-process_period[0], costs, self._snapshot_provider, final_targets, eligible_orders, previous_orders=last_orders)
                opti = algo.create_instance(proc.process, snap, costs, targets=final_targets, initial_solution=initial_solution, orders=eligible_orders)
                # TODO parameters
                time_id: str = DatetimeUtils.format(DatetimeUtils.now(), use_zone=False).replace("-", "").replace(":","").replace("T", "")
                listener = FrontendOptimizationListener(proc.process + "_" + time_id + "_batch", persistence, True, opti, timeout=proc.max_duration)
                t0 = time.time()
                opti_state.start(proc.process, snapshot, listener, opti, proc.max_iterations)
                opti_state.wait_for_completion(timeout=proc.max_duration + timedelta(minutes=5))
                seconds = time.time() - t0
                history = listener.history()
                sol, objective = listener.best_solution()
                print(f"Batch lot creation job finished for process {proc.process} with {len(eligible_orders)} orders after {len(history)} iterations and {int(seconds/60)} minutes. Id: {listener._id}")
                if sol is not None:
                    all_lots = [lot for lots in sol.get_lots(orders=all_orders).values() for lot in lots]
                    lots_cnt = len(all_lots)
                    lots_weight = sum(lot.weight or 0 for lot in all_lots)
                    orders_assigned = sum(len(lot.orders) for lot in all_lots)
                    print(f"  Objective value: {objective}, lots: {lots_cnt}, orders assigned: {orders_assigned}/{len(eligible_orders)}, " +
                          f"total lot weights: {lots_weight}t (targeted: {final_total_production}t).")
            except:
                print(f"Error in lots batch job for proc {proc.process}")
                traceback.print_exc()


    # TODO support multiple configs
    @staticmethod
    def _parse_config(cfg: str) -> BatchConfig:
        """
        Examples:
            06:00;P1D;PROC1:1000:PT15M,PROC2:250:PT10M
            06:00;P1D;PROC1:1000:PT15M,PROC2:250:PT10M;test
            06:00,append,P5D;P1D;PROC1:1000:PT15M,PROC2:250:PT10M;
        """
        if any(c.isspace() for c in cfg):
            raise Exception("Multiple batch configs not supported yet")
        cmps = cfg.split(";")
        if len(cmps) <= 2:
            raise Exception(f"Invalid config {cfg}")
        first_comp = cmps[0]
        append = False
        horizon = timedelta(days=7)
        if "," in first_comp:
            first_split = first_comp.split(",")
            if first_split[1].lower().strip() == "append":
                append = True
                if len(first_split) > 2:
                    horizon = pd.Timedelta(first_split[2]).to_pytimedelta()
            first_comp = first_split[0]
        dt: datetime = datetime.strptime(first_comp, "%H:%M")
        planning_duration = pd.Timedelta(cmps[1]).to_pytimedelta()
        processes: list[tuple[str, int, timedelta]] = [(prc[0], int(prc[1]), pd.Timedelta(prc[2]).to_pytimedelta()) for prc in (prc.split(":") for prc in cmps[2].split(","))]
        procs = [ProcessConfig(process=p[0], max_iterations=p[1], max_duration=p[2]) for p in processes]
        test = len(cmps) > 3 and cmps[3].strip().lower() == "test"
        config = BatchConfig(time=dt, processes=procs, test=test, period=planning_duration, append_period=append, max_equipment_horizon=horizon)
        return config

    def _next_invocation(self, now: datetime) -> datetime:
        if self._config.test and self._runs == 0:
            return now
        now = now.astimezone()  # convert to local time
        tm = self._config.time
        nxt = now.replace(hour=tm.hour, minute=tm.minute, second=0, microsecond=0)
        while nxt < now:
            nxt = nxt + timedelta(days=1)
        nxt = nxt.astimezone(tz=timezone.utc)
        return nxt



