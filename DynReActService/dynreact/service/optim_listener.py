from datetime import datetime

from dynreact.base.LotsOptimizer import OptimizationListener
from dynreact.base.model import ProductionPlanning, ProductionTargets, ObjectiveFunction
from dynreact.service.model import LotsOptimizationResults


class LotsOptimizationListener(OptimizationListener):

    def __init__(self, snapshot: datetime, targets: ProductionTargets, orders: list[str], trace_results: bool):
        super().__init__()
        self._snapshot: datetime = snapshot
        self._targets: ProductionTargets = targets
        self._orders: list[str] = orders
        self._stopped: bool = False
        self._results: list[ProductionPlanning] = []
        self._objectives: list[ObjectiveFunction] = []
        self._trace_results: bool = trace_results
        self._best_result: ProductionPlanning|None = None
        self._best_objective: float|None = None

    def update_solution(self, planning: ProductionPlanning, objective_value: ObjectiveFunction):
        self._objectives.append(objective_value)
        if self._trace_results:
            self._results.append(planning)
        if self._best_objective is None or objective_value.total_value < self._best_objective:
            self._best_objective = objective_value.total_value
            self._best_result = planning

    def update_iteration(self, iteration_cnt: int, lots_cnt: int, objective_value: ObjectiveFunction) -> bool:
        return not self._stopped

    def stop(self):
        self._stopped = True

    def is_done(self) -> bool:
        return super().is_done() or self._stopped

    def get_results(self) -> LotsOptimizationResults:
        results = self._results if self._trace_results else [self._best_result] if self._best_result is not None else []
        return LotsOptimizationResults(snapshot=self._snapshot, targets=self._targets, orders=self._orders,
                    results=results, objective_function=self._objectives, done=self._stopped or self.is_done())
