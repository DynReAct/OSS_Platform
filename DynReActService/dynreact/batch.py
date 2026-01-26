import threading
import time
import traceback
from datetime import timedelta, datetime
from typing import Sequence

import numpy as np
from pydantic import BaseModel

from dynreact.app import state
from dynreact.app_config import DynReActSrvConfig
from dynreact.base.SnapshotProvider import OrderInitMethod
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
    period: timedelta = timedelta(days=1)   # TODO configurable
    test: bool=False
    "If set to true, a batch job will be run on startup"


class LotsBatchOptimizationJob:
    """
    TODO order backlog initialization based on expected available orders at the planned period start
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
        snap: Snapshot = self._state.get_snapshot(snapshot)
        algo = self._state.get_lots_optimization()
        costs = self._state.get_cost_provider()
        opti_state = state.get_lot_creator()
        persistence = state.get_results_persistence()
        shifts_provider = self._state.get_shifts_provider()
        site = state.get_site()
        proc_settings: dict[str, ProcessLotCreationSettings] = site.lot_creation.processes if site.lot_creation is not None else {}
        reference_duration: timedelta = site.lot_creation.duration if site.lot_creation is not None else timedelta(days=1)
        planning_horizon: timedelta = self._config.period
        now = DatetimeUtils.now()
        # this is the generic period, but we'll adapt it further for each process stage depending on the horizon of existing lots
        period = (now, now + planning_horizon)
        lot_size_to_tuple = lambda x: x if x is None else (x.min, x.max)
        all_orders = {o.id: o for o in snap.orders}
        for proc in self._config.processes:
            if self._stopped.is_set():
                break
            try:
                settings = proc_settings.get(proc.process) if proc_settings is not None else None
                equipment = site.get_process_equipment(proc.process)
                equipment_ids = [e.id for e in equipment]
                existing_lots: list[Lot] = [lot for eq, lots in snap.lots.items() if eq in equipment_ids for lot in lots if   # TODO lot status filter correct?
                        (lot.status > 1 and lot.start_time is not None and lot.end_time is not None and lot.start_time < period[1] and lot.end_time > period[0])]
                lots_horizon, equipment_horizons, last_orders = ModelUtils.lots_horizon(equipment_ids, existing_lots)
                if lots_horizon is not None and lots_horizon >= period[1]:
                    continue
                process_period: tuple[datetime, datetime] = period if lots_horizon is None or lots_horizon <= period[0] else (lots_horizon, period[1])
                planning_duration = process_period[1] - process_period[0]
                shifts: dict[int, Sequence[PlannedWorkingShift]] = shifts_provider.load_all(process_period[0], process_period[1], limit=None, equipments=equipment_ids)
                fractions_available: dict[int, float] = {e: sum((s.worktime for s in shift), start=timedelta())/planning_duration if len(shift) > 0 else 0 for e, shift in shifts.items()}
                equipment_ids = [e for e, frac in fractions_available.items() if frac > 0]
                if len(equipment_ids) == 0:
                    continue
                targets_weights0: dict[int, float] = {}
                for e in equipment_ids:
                    # these are targets per shift, or per day, for instance.
                    targets_0 = settings.get_equipment_targets(e) if settings is not None else None
                    if targets_0 is None or np.isnan(targets_0):
                        capacity_tons_per_hour: float | None = next(eq for eq in equipment if eq.id == e).throughput_capacity
                        if capacity_tons_per_hour is not None:
                            hours: float = planning_duration.total_seconds()/3_600
                            targets_0 = capacity_tons_per_hour * hours
                    else:
                        duration_factor: float = planning_duration / reference_duration
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
                sub_targets = {proc.process: [targets]}
                total_production = sum(t.total_weight for t in targets.target_weight.values())
                # these are the targets for the complete period (not process specific)
                full_targets = MidTermTargets(period=period, sub_periods=[period], production_sub_targets=sub_targets, total_production=total_production, production_targets={})
                final_targets: ProductionTargets = ModelUtils.mid_term_targets_from_ltp_result(full_targets, proc.process, process_period[0], process_period[1], existing_lots=existing_lots)
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
                # TODO start orders(?)
                initial_solution, _ = algo.heuristic_solution(proc.process, snap, process_period[1]-process_period[0], costs, self._snapshot_provider, final_targets, eligible_orders)
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
                print(f"Batch lot creation job finished for process {proc.process} with {len(eligible_orders)} orders after {len(history)} iterations and {int(seconds/60)} minutes.")
                if sol is not None:
                    all_lots = [lot for lots in sol.get_lots(orders=all_orders).values() for lot in lots]
                    lots_cnt = len(all_lots)
                    lots_weight = sum(lot.weight or 0 for lot in all_lots)
                    orders_assigned = sum(len(lot.orders) for lot in all_lots)
                    print(f"  Objective value: {objective}, lots: {lots_cnt}, orders assigned: {orders_assigned}, total lot weights: {lots_weight}t (targeted: {final_total_production}t).")
            except:
                print(f"Error in lots batch job for proc {proc.process}")
                traceback.print_exc()


    # TODO support multiple configs
    @staticmethod
    def _parse_config(cfg: str) -> BatchConfig:
        """
        Examples:
            06:00;PROC1:1000:15m,PROC2:250:10m
            06:00;PROC1:1000:15m,PROC2:250:10m;test
        """
        if any(c.isspace() for c in cfg):
            raise Exception("Multiple batch configs not supported yet")
        cmps = cfg.split(";")
        if len(cmps) <= 1:
            raise Exception(f"Invalid config {cfg}")
        dt: datetime = datetime.strptime(cmps[0], "%H:%M")
        processes: list[tuple[str, int, timedelta]] = [(prc[0], int(prc[1]), DatetimeUtils.parse_duration(prc[2])) for prc in (prc.split(":") for prc in cmps[1].split(","))]
        procs = [ProcessConfig(process=p[0], max_iterations=p[1], max_duration=p[2]) for p in processes]
        test = len(cmps) > 2 and cmps[2].strip().lower() == "test"
        config = BatchConfig(time=dt, processes=procs, test=test)
        return config

    def _next_invocation(self, now: datetime) -> datetime:
        if self._config.test and self._runs == 0:
            return now
        tm = self._config.time
        nxt = now.replace(hour=tm.hour, minute=tm.minute, second=0, microsecond=0)
        while nxt < now:
            nxt = nxt + timedelta(days=1)
        return nxt



