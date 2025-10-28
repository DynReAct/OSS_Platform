import threading
import time
import traceback
from datetime import timedelta, datetime

from pydantic import BaseModel

from dynreact.app import state
from dynreact.app_config import DynReActSrvConfig
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Snapshot
from dynreact.lots_optimization import FrontendOptimizationListener
from dynreact.state import DynReActSrvState


class ProcessConfig(BaseModel, frozen=True, use_attribute_docstrings=True):
    process: str
    max_duration: timedelta
    max_iterations: int


class BatchConfig(BaseModel, frozen=True, use_attribute_docstrings=True):
    time: datetime
    processes: list[ProcessConfig]


class LotsBatchOptimizationJob:

    def __init__(self, config: DynReActSrvConfig, state: DynReActSrvState):
        self._thread = None
        self._config = None
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
        while True:
            now = DatetimeUtils.now()
            if next_planned_invocation > now:
                self._stopped.wait((next_planned_invocation-now).total_seconds())
                if self._stopped.is_set():
                    break
                now = DatetimeUtils.now()
            try:
                snap = next(snaps_provider.snapshots(next_planned_invocation - timedelta(minutes=5), now, order="desc"))
            except StopIteration:
                self._stopped.wait(60_000)  # TODO ?
                if self._stopped.is_set():
                    break
                continue
            last_invocation = now
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
        for proc in self._config.processes:
            if self._stopped.is_set():
                break
            try:
                targets = None  # TODO
                initial_solution = None  # TODO
                opti = algo.create_instance(proc.process, snap, costs, targets=targets, initial_solution=initial_solution)
                # TODO parameters
                time_id: str = DatetimeUtils.format(DatetimeUtils.now(), use_zone=False).replace("-", "").replace(":","").replace("T", "")
                listener = FrontendOptimizationListener(proc.process + "_" + time_id + "_batch", persistence, True, opti, timeout=proc.max_duration)
                t0 = time.time()
                opti_state.start(proc.process, snapshot, listener, opti, proc.max_iterations)
                opti_state.wait_for_completion(timeout=proc.max_duration + timedelta(minutes=5))  # TODO test
                seconds = time.time() - t0
                history = listener.history()
                sol, objective = listener.best_solution()
                print(f"Batch lot creation job finished for process {proc.process} after {len(history)} iterations and {int(seconds/60)} minutes.")
                if sol is not None:
                    lots_cnt = len([l for lots in sol.get_lots().values() for l in lots])
                    print(f"  Objective value: {objective}, lots: {lots_cnt}")
            except:
                print(f"Error in lots batch job for proc {proc.process}")
                traceback.print_exc()


    # TODO support multiple configs
    @staticmethod
    def _parse_config(cfg: str) -> BatchConfig:
        """
        Example: 06:00;PROC1:1000:15m,PROC2:250:10m;
        """
        if any(c.isspace() for c in cfg):
            raise Exception("Multiple batch configs not supported yet")
        cmps = cfg.split(";")
        if len(cmps) <= 1:
            raise Exception(f"Invalid config {cfg}")
        dt: datetime = datetime.strptime(cmps[0], "%H:%M")
        processes: list[tuple[str, int, timedelta]] = [(prc[0], int(prc[1]), DatetimeUtils.parse_duration(prc[2])) for prc in (prc.split(":") for prc in cmps[1].split(","))]
        procs = [ProcessConfig(process=p[0], max_iterations=p[1], max_duration=p[2]) for p in processes]
        config = BatchConfig(time=dt, processes=procs)
        return config

    def _next_invocation(self, now: datetime) -> datetime:
        tm = self._config.time
        nxt = now.replace(hour=tm.hour, minute=tm.minute, second=0, microsecond=0)
        while nxt < now:
            nxt = nxt + timedelta(days=1)
        return nxt



