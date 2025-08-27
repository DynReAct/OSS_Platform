import time
from typing import Callable, Sequence

import numpy as np


class _GlobalCostsTspSolver:
    """
    Note: this algorithm is most effective if a good starting position is provided
    """

    def __init__(self, transition_costs: np.ndarray, global_costs: Callable[[tuple[int, ...], float], float], start_costs: np.ndarray|None=None,
                 initial_paths: tuple[tuple[int, ...], ...] | None = None, init_nearest_neighbours: bool = True,
                 time_limit: float|None = None
                 ):
        self._transition_costs = transition_costs if isinstance(transition_costs, np.ndarray) else np.array(transition_costs)
        self._global_costs = global_costs
        self._num = transition_costs.shape[0] if isinstance(transition_costs, np.ndarray) else len(transition_costs)
        self._best_path: tuple[int, ...]|None = None
        self._best_costs: float = np.inf
        self._start_costs = start_costs if start_costs is not None else np.zeros(self._num)
        self._initial_paths = initial_paths
        self._init_nearest_neighbors = init_nearest_neighbours
        self._time_limit = time_limit
        self._iteration_cnt: int = 0
        self._start_time = None

    def find_shortest_path(self) -> tuple[tuple[int, ...], float]:
        """
        Returns: the path plus global costs
        """
        if self._num == 0:
            return tuple(), 0
        if self._num == 1:
            return (0, ), self._global_costs((0, ), self._start_costs[0])
        self._start_time = time.time()
        if self._initial_paths is not None:
            for path in self._initial_paths:
                costs = self._evaluate_path(path)
                if costs < self._best_costs:
                    self._best_costs = costs
                    self._best_path = path
        if self._init_nearest_neighbors:  #  a heuristic initialization aimed at eliminating a lot of worse paths quickly
            self._evaluate_nearest_neighbor_route()
        for idx in range(self._num):
            transition_costs: float = self._start_costs[idx]
            start_route = (idx, )
            if transition_costs >= self._best_costs:
                continue
            self.find_shortest_subpath(start_route, transition_costs)
        return self._best_path, self._best_costs

    def find_shortest_subpath(self, start_route: tuple[int, ...], cumulative_transition_costs: float):
        if self._time_limit is not None and self._iteration_cnt % 100 == 0 and time.time() - self._start_time > self._time_limit:
            # abort
            return
        self._iteration_cnt += 1
        open_positions: list[int] = [idx for idx in range(self._num) if idx not in start_route]
        open_slots: int = len(open_positions)
        for idx in open_positions:
            delta_trans: float = self._transition_costs[start_route[-1], idx]
            trans_costs: float = cumulative_transition_costs + delta_trans
            if trans_costs >= self._best_costs:
                continue
            new_route = start_route + (idx, )
            if open_slots == 1:
                global_costs = self._global_costs(new_route, trans_costs)
                if global_costs < self._best_costs:
                    self._best_costs = global_costs
                    self._best_path = new_route
            else:
                self.find_shortest_subpath(new_route, trans_costs)

    def _evaluate_path(self, route: tuple[int, ...]) -> float:
        tc = self._start_costs[route[0]]
        last = route[0]
        for idx in route[1:]:
            tc += self._transition_costs[last, idx]
        return self._global_costs(route, tc)

    def _evaluate_nearest_neighbor_route(self):
        route, costs = self._construct_nearest_neighbor_solution()
        full_costs = self._global_costs(route, costs)
        if full_costs < self._best_costs:
            self._best_path = route
            self._best_costs = full_costs

    def _construct_nearest_neighbor_solution(self, start_idx: int|None = None) -> tuple[tuple[int, ...], float]:
        num = self._num
        if start_idx is None:
            start_idx = 0
            min_start_costs = min(self._start_costs)
            start_candidates = [idx for idx in range(num) if self._start_costs[idx] == min_start_costs]
            if len(start_candidates) == 1:
                start_idx = start_candidates[0]
            elif len(start_candidates) > 1:
                min_transition_costs_to: list[float] = [min(self._transition_costs[j, i] for j in range(num) if j != i) for i in start_candidates]
                most_expensive_trans_to = np.argmax(min_transition_costs_to)
                start_idx = int(most_expensive_trans_to)
        trans_costs: float = self._start_costs[start_idx]
        route = [start_idx]
        open_items = list(range(num))
        open_items.remove(start_idx)
        for idx in range(1, num):
            # find the best next match
            all_trans_costs: list[float] = self._transition_costs[start_idx, open_items]  # [self._transition_costs[start_idx, item] for item in open_items]
            open_idx = np.argmin(all_trans_costs)
            trans_costs += all_trans_costs[open_idx]
            next_item = open_items.pop(open_idx)
            route.append(next_item)
            start_idx = next_item
        return tuple(route), trans_costs


def solve(transition_costs: np.ndarray|Sequence[Sequence[float]],
          global_costs: Callable[[tuple[int, ...], float], float],
          start_costs: np.ndarray|Sequence[float]|None=None,
          initial_paths: tuple[tuple[int, ...], ...]|None=None,
          init_nearest_neighbours: bool=False,
          time_limit: float | None = None) -> tuple[tuple[int, ...], float]:
    """
    Parameters:
        transition_costs: a 2D matrix of transition costs
        global_costs: a function of the path and the cumulative transition costs for the path; it is expected that the
            global_costs returned are always higher than the cumulative transition costs, otherwise the algorithm
            may lead to suboptimal results
        start_costs: a 1D vector
        initial_paths: a set of known good approximations
        init_nearest_neighbours: use a heuristic initialization?
        time_limit: set a time limit (in s). If set, the optimal solution is not guaranteed to be found.
    """
    return _GlobalCostsTspSolver(transition_costs, global_costs, start_costs=start_costs,
                                 initial_paths=initial_paths, init_nearest_neighbours=init_nearest_neighbours,
                                 time_limit=time_limit).find_shortest_path()


