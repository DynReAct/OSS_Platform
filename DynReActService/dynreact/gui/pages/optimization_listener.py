from dynreact.base.LotsOptimizer import OptimizationListener, LotsOptimizationState
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.model import ProductionPlanning, ObjectiveFunction


class FrontendOptimizationListener(OptimizationListener):

    def __init__(self, id: str, persistence: ResultsPersistence|None, store_results: bool,
                 initial_state: LotsOptimizationState|None = None, parameters: dict[str, any]|None = None):
        super().__init__()
        self._active: bool = True
        self._id: str = id
        self._persistence = persistence
        self._state: LotsOptimizationState|None = initial_state
        self._store_results: bool = store_results
        self._parameters = parameters

    def update_solution(self, planning: ProductionPlanning, objective_value: ObjectiveFunction):
        if self._state is None:
            self._state = LotsOptimizationState(planning, objective_value, planning, objective_value.total_value, history=[objective_value],
                                                parameters=self._parameters)
        else:
            self._state.current_solution = planning
            self._state.current_object_value = objective_value
            self._state.history.append(objective_value)
            if objective_value.total_value < self._state.best_objective_value:
                self._state.best_solution = planning
                self._state.best_objective_value = objective_value.total_value
        if self._store_results and self._persistence is not None:
            self._persistence.store(self._id, self._state)

    def update_iteration(self, iteration_cnt: int, lots_cnt: int, objective_value: ObjectiveFunction) -> bool:
        return self._active

    def stop(self):
        self._active = False

    def solution(self) -> tuple[ProductionPlanning, float]:
        if self._state is None:
            return None, None
        return self._state.current_solution, self._state.current_object_value.total_value

    def history(self) -> list[float]:
        return [h.total_value for h in self._state.history] if self._state is not None else []

    def parameters(self) -> dict[str, any]|None:
        return self._parameters if self._state is None else self._state.parameters
