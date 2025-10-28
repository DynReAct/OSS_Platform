import threading
import time
import traceback
from datetime import timedelta, datetime

from pydantic import BaseModel

from dynreact.app import state
from dynreact.app_config import DynReActSrvConfig
from dynreact.base.SnapshotProvider import OrderInitMethod
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Snapshot, ProcessLotCreationSettings, ProductionTargets, EquipmentProduction
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
            self._thread.start()

    def run(self):
        last_invocation: datetime|None = None
        next_planned_invocation = self._next_invocation(DatetimeUtils.now())
        snaps_provider = self._snapshot_provider
        wait_cnt: int = 0
        while True:
            now = DatetimeUtils.now()
            if next_planned_invocation > now:
                self._stopped.wait((next_planned_invocation-now).total_seconds())
                if self._stopped.is_set():
                    break
                now = DatetimeUtils.now()
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
        site = state.get_site()
        proc_settings: dict[str, ProcessLotCreationSettings] = site.lot_creation.processes if site.lot_creation is not None else {}
        planning_horizon: timedelta = self._config.period
        now = DatetimeUtils.now()
        period = (now, now + planning_horizon)  # TODO consider current lots horizon per plant/process
        default_tons = 1000     # FIXME would need to depend on process; better fail if no setting available?
        lot_size_to_tuple = lambda x: x if x is None else (x.min, x.max)
        all_orders = {o.id: o for o in snap.orders}
        for proc in self._config.processes:
            if self._stopped.is_set():
                break
            try:
                settings = proc_settings.get(proc.process) or ProcessLotCreationSettings(total_size=default_tons)    # XXX?
                equipment = site.get_process_equipment(proc.process)
                equipment_ids = [e.id for e in equipment]
                target_weights: dict[int, EquipmentProduction] = {equ: EquipmentProduction(equipment=equ, total_weight=settings.get_equipment_targets(equ, default_value=default_tons),
                                                                                lot_weight_range=lot_size_to_tuple(settings.get_equipment_lot_sizes(equ))) for equ in equipment_ids}
                # TODO option to set material structure settings
                targets = ProductionTargets(process=proc.process, period=period, target_weight=target_weights)
                # TODO: tbd
                method = [OrderInitMethod.ACTIVE_PROCESS, OrderInitMethod.OMIT_RELEASED_LOTS, OrderInitMethod.OMIT_ACTIVE_LOTS]
                # TODO: the planning horizon is currently not taken into account. For this purpose, also the range of the existing planning should be considered (period depending on process),
                #  in order to consider orders from the previous process stage which will be available for planning  => new OrderInitMethod?
                eligible_orders: list[str] = self._snapshot_provider.eligible_orders(snap, proc.process, period, method=method)
                eligible_orders = [o for o in eligible_orders if o in all_orders and any(e in equipment_ids for e in all_orders[o].allowed_equipment)]
                available_material = sum(all_orders[o].actual_weight for o in eligible_orders)
                total_targets = sum(w.total_weight for w in target_weights.values())
                if len(eligible_orders) <= 2:   # TODO configurable, maybe also minimum amount of material
                    print(f"Batch lot creation job for process {proc.process} has only {len(eligible_orders)} eligible orders, skipping it.")
                    continue
                if total_targets > available_material:
                    print(f"Batch lot creation for {proc.process}: available order backlog of {available_material}t does not cover the target of {total_targets}t.")
                # TODO start orders
                initial_solution, _ = algo.heuristic_solution(proc.process, snap, period[1]-period[0], costs, self._snapshot_provider, targets, eligible_orders)
                opti = algo.create_instance(proc.process, snap, costs, targets=targets, initial_solution=initial_solution, orders=eligible_orders)
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
                    print(f"  Objective value: {objective}, lots: {lots_cnt}, orders assigned: {orders_assigned}, total lot weights: {lots_weight}t (targeted: {total_targets}t).")
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



