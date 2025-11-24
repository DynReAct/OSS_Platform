import threading
import traceback
from datetime import datetime, timedelta

from dynreact.base.LotsOptimizer import OptimizationListener, LotsOptimizer, LotsOptimizationState
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import ProductionPlanning, ObjectiveFunction, Snapshot

_lot_creation_thread_name = "lot-creation"


class FrontendOptimizationListener(OptimizationListener):

    def __init__(self, id: str, persistence: ResultsPersistence|None, store_results: bool,
                 optimization: LotsOptimizer,
                 initial_state: LotsOptimizationState|None = None, parameters: dict[str, any]|None = None,
                 timeout: timedelta|None = None):
        super().__init__()
        self._active: bool = True
        self._id: str = id
        self._persistence = persistence
        self._state: LotsOptimizationState|None = initial_state
        self._store_results: bool = store_results
        self._parameters = parameters
        self._optimizer = optimization
        self._process = optimization.process()
        self._timeout = timeout
        self._start_time = DatetimeUtils.now()

    def update_solution(self, planning: ProductionPlanning, objective_value: ObjectiveFunction):
        if self._state is None:
            self._state = LotsOptimizationState(planning, objective_value, planning, objective_value, history=[objective_value],
                                                parameters=self._parameters)
        else:
            self._state.current_solution = planning
            self._state.current_object_value = objective_value
            self._state.history.append(objective_value)
            if objective_value.total_value < self._state.best_objective_value.total_value:
                self._state.best_solution = planning
                self._state.best_objective_value = objective_value
        if self._store_results and self._persistence is not None:
            self._persistence.store(self._id, self._state)

    def process(self) -> str:
        return self._process

    def update_iteration(self, iteration_cnt: int, lots_cnt: int, objective_value: ObjectiveFunction) -> bool:
        return self._active and (self._timeout is None or DatetimeUtils.now() - self._start_time < self._timeout)

    def stop(self):
        self._active = False

    def solution(self) -> tuple[ProductionPlanning, float]:
        if self._state is None:
            return None, None
        return self._state.current_solution, self._state.current_object_value.total_value

    def best_solution(self) -> tuple[ProductionPlanning, float]:
        if self._state is None:
            return None, None
        return self._state.best_solution, self._state.best_objective_value.total_value

    def history(self) -> list[float]:
        return [h.total_value for h in self._state.history] if self._state is not None else []

    def parameters(self) -> dict[str, any]|None:
        return self._parameters if self._state is None else self._state.parameters

    def optimization(self) -> LotsOptimizer:
        return self._optimizer

    def restart(self, store_results: bool):
        self.reset()
        self._active = True
        store_now: bool = store_results and not self._store_results
        self._store_results = store_results
        if store_now and self._persistence is not None and self._state is not None:
            try:
                self._persistence.store(self._id, self._state)
            except:
                traceback.print_exc()
                pass
        self._start_time = DatetimeUtils.now()


class KillableOptimizationThread(threading.Thread):

    def __init__(self, process: str, snapshot: datetime, optimization: LotsOptimizer[any], num_iterations: int|None=None, continued: bool=False):
        super().__init__(name=_lot_creation_thread_name)
        self._kill = threading.Event()
        self.daemon = True  # Allow main to exit even if still running.
        self._optimization = optimization
        self._process: str = process
        self._snapshot: datetime = snapshot
        self._iterations: int = num_iterations
        self._continued: bool = continued

    @staticmethod
    def from_existing_run(listener: FrontendOptimizationListener, num_iterations: int|None=None):
        optimizer = listener.optimization()
        return KillableOptimizationThread(optimizer.process(), optimizer.snapshot(), optimizer, num_iterations=num_iterations, continued=True)

    def kill(self):
        self._kill.set()

    def process(self):
        return self._process

    def snapshot(self):
        return self._snapshot

    def num_iterations(self):
        return self._iterations

    def run(self):
        return self._optimization.run(max_iterations=self._iterations, continued=self._continued)


class LotCreator:
    """
    Enables a single optimization to run at a time. Used by the frontend (user-initiated) and batch processing.
    """

    def __init__(self):
        self._lot_creation_thread: threading.Thread | None = None
        self._lot_creation_listener: FrontendOptimizationListener | None = None
        self._lock = threading.RLock()

    def stop(self):
        with self._lock:
            thread = self._lot_creation_thread
            listener = self._lot_creation_listener
            if thread is not None:
                thread.kill()
                self._lot_creation_thread = None
            if listener is not None:
                listener.stop()   # do not set to None, may continue later

    def start(self, process: str, snapshot: datetime, listener: FrontendOptimizationListener, opti: LotsOptimizer[any], iterations: int) -> tuple[bool, str|None]:
        """Returns: is_running, error_msg"""
        with self._lock:
            if self.is_running()[0]:
                return True, "Already running"
            try:
                lot_creation_thread = KillableOptimizationThread(process, snapshot, opti, num_iterations=iterations)
                opti.add_listener(listener)
                self._lot_creation_listener = listener
                self._lot_creation_thread = lot_creation_thread
                lot_creation_thread.start()
                return True, None
            except Exception as e:
                traceback.print_exc()
                error_msg = str(e)
                return self.is_running()[0], error_msg

    def wait_for_completion(self, timeout: timedelta|None=None):
        with self._lock:
            thread = self._lot_creation_thread
        if thread is None or not thread.is_alive():
            return
        thread.join(timeout=timeout.total_seconds() if timeout is not None else None)


    def is_running(self) -> tuple[bool, str|None]:
        """Returns: is_running, active process"""
        with self._lock:
            if self._lot_creation_thread is not None:
                if not self._lot_creation_thread.is_alive():
                    self._lot_creation_thread = None
                    if self._lot_creation_listener is not None:
                        self._lot_creation_listener.stop()
                        # self._lot_creation_listener = None # do not remove the listener, since we may want to continue the optimization
                if self._lot_creation_thread is not None:
                    return True, self._lot_creation_thread.process()
            return False, None

    def continue_possible(self) -> tuple[bool, str|None]:
        """Returns: is_possible, active process"""
        with self._lock:
            active, proc = self.is_running()
            if active:
                return False, proc
            l = self._lot_creation_listener
            return l is not None, l.process() if l is not None else None

    def continue_optimization(self, iterations: int, store_results: bool) -> tuple[bool, str|None]:
        """Returns: is_running, error message"""
        with self._lock:
            try:
                is_possible, proc = self.continue_possible()
                if not is_possible:
                    running, proc2 = self.is_running()
                    return running, "Already running" if running else "No active optimization"
                listener = self._lot_creation_listener
                listener.restart(store_results)
                lot_creation_thread = KillableOptimizationThread.from_existing_run(listener, iterations)
                self._lot_creation_thread = lot_creation_thread
                lot_creation_thread.start()
                return True, None
            except Exception as e:
                traceback.print_exc()
                return self.is_running()[0], f"Internal error {e}"

    def listener(self) -> FrontendOptimizationListener|None:
        with self._lock:
            return self._lot_creation_listener


