from typing import Callable, Generator, Any

import numpy as np
import numpy.typing as npt

from dynreact.lotcreation.globaltsp.GlobalTspSolver import Route, GlobalTspInput, GlobalCostsTspSolver, TspResult


class _NearestNeighbourScenario[T]:

    def __init__(self,
                 local_transition_costs: npt.NDArray[np.float32],
                 transition_costs: Callable[[Route, np.uint16 | int, T], T],
                 eval_costs: Callable[[T], float],
                 empty_route: T,
                 time_limit: float|None = None,
                 local_start_costs: npt.NDArray[np.float32]|None = None):
        self._local_transition_costs = local_transition_costs if isinstance(local_transition_costs, np.ndarray) \
            else np.array(local_transition_costs, dtype=np.float32)
        self._transition_costs = transition_costs
        self._eval_costs = eval_costs
        self._num = self._local_transition_costs.shape[0]
        self._empty_route: T = empty_route
        self._best_path: Route | None = None
        self._best_costs: float = np.inf
        self._best_cost_obj: T | None = None
        self._time_limit = time_limit
        self._iteration_cnt: int = 0
        self._start_time = None

    def find_shortest_path(self) -> TspResult[T]:
        route, state = self._nearest_neighbour_solution(np.array([], dtype=np.uint16), self._empty_route)
        return TspResult(route=route, state=state)

    def _nearest_neighbour_solution(self, start_route: Route, cost_obj: T) -> tuple[Route, T]:
        open_positions: Generator[np.uint16, Any, None] = (idx for idx in (np.uint16(idx) for idx in range(self._num)) if idx not in start_route)
        open_slots: int = self._num - len(start_route)
        best_idx = -1
        best_costs = np.inf
        best_cost_obj: T | None = None
        for idx in open_positions:
            new_cost_obj = self._transition_costs(start_route, idx, cost_obj)
            new_costs: float = self._eval_costs(new_cost_obj)
            if new_costs < best_costs:
                best_idx = idx
                best_costs = new_costs
                best_cost_obj = new_cost_obj
        new_route = np.append(start_route, best_idx)
        if open_slots == 1:
            return new_route, best_cost_obj
        return self._nearest_neighbour_solution(new_route, best_cost_obj)


class NearestNeighbourSolver[T](GlobalCostsTspSolver[T]):

    def find_shortest_path_global(self, data: GlobalTspInput[T]) -> TspResult[T]:
        return _NearestNeighbourScenario(data.local_transition_costs, data.transition_costs, data.eval_costs, data.empty_state, data.time_limit, data.local_start_costs).find_shortest_path()
