import time
from typing import Callable, Mapping

import numpy as np
import numpy.typing as npt

from dynreact.lotcreation.globaltsp.GlobalTspSolver import Route, GlobalTspInput, GlobalCostsTspSolver, TspResult


class _GlobalSearchBBScenario[T]:

    def __init__(self,
                 local_transition_costs: npt.NDArray[np.float32],
                 transition_costs: Callable[[Route, np.uint16 | int, T], T],
                 eval_costs: Callable[[T], float],
                 empty_state: T,
                 time_limit: float|None = None,
                 local_start_costs: npt.NDArray[np.float32]|None = None,
                 bound_factor_upcoming_costs: float|dict[int, float] = 0,
                 ):
        self._local_transition_costs = local_transition_costs if isinstance(local_transition_costs, np.ndarray) \
            else np.array(local_transition_costs, dtype=np.float32)
        self._transition_costs = transition_costs
        self._eval_costs = eval_costs
        self._num = self._local_transition_costs.shape[0]
        num = self._num
        self._empty_state: T = empty_state
        self._best_path: Route | None = None
        self._best_costs: float = np.inf
        self._best_cost_obj: T | None = None
        # self._init_nearest_neighbors = init_nearest_neighbours
        self._time_limit = time_limit
        self._iteration_cnt: int = 0
        self._start_time = None
        self._timeout_reached: bool = False
        self._lower_mean_transition = np.zeros(num, dtype=np.float32)
        if num > 2 and isinstance(bound_factor_upcoming_costs, Mapping):
            l: int = len(bound_factor_upcoming_costs)
            if l == 0:
                bound_factor_upcoming_costs = 0
            elif l == 1:
                bound_factor_upcoming_costs = next(iter(bound_factor_upcoming_costs.values()))
            else:
                keys: list[int] = list(bound_factor_upcoming_costs.keys())
                for idx in range(1, l):
                    lower_idx = keys[idx-1]
                    upper_idx = keys[idx]
                    if num < lower_idx:
                        bound_factor_upcoming_costs = 0
                        break
                    if num <= upper_idx:
                        v0 = bound_factor_upcoming_costs[idx-1]
                        v1 = bound_factor_upcoming_costs[idx]
                        bound_factor_upcoming_costs = v0 + (num - lower_idx)/(upper_idx-lower_idx) * (v1 - v0)
                        break
                if isinstance(bound_factor_upcoming_costs, Mapping):
                    bound_factor_upcoming_costs = bound_factor_upcoming_costs[keys[l-1]]
        self._bound_factor_upcoming_costs = bound_factor_upcoming_costs
        self._use_bound_estimation: bool = bound_factor_upcoming_costs > 0 and num > 2
        if self._use_bound_estimation:
            half = int(np.round(num / 2))
            for i in range(num):
                tc = self._local_transition_costs[[idx for idx in range(num) if idx != i], i]
                med = np.median(tc)
                sorted_tcs = np.sort([c for c in tc if c <= med])
                sorted_tcs = sorted_tcs[:half]
                mn = np.mean(sorted_tcs)
                self._lower_mean_transition[i] = mn

    def find_shortest_path(self) -> TspResult[T]:
        """
        Returns: the path plus global costs
        """
        num = self._num
        if num == 0:
            return TspResult(route=np.array([], dtype=np.uint16), state=self._empty_state)
        if num == 1:
            route: Route = np.array([0], dtype=np.uint16)
            return TspResult(route=route, state=self._transition_costs(np.array([], dtype=np.uint16), 0, self._empty_state))
        self._start_time = time.time()
        for idx in range(num):
            cost_obj: T = self._transition_costs(np.array([], dtype=np.uint16), idx, self._empty_state)
            costs: float = self._eval_costs(cost_obj)
            start_route = np.array([idx], dtype=np.uint16)
            if costs >= self._best_costs:
                continue
            if self._use_bound_estimation:
                other_costs = sum(self._lower_mean_transition[j] for j in range(num) if j != idx)
                estimated_costs = costs + self._bound_factor_upcoming_costs * other_costs
                if estimated_costs >= self._best_costs:
                    continue
            self.find_shortest_subpath(start_route, cost_obj)
        return TspResult(route=self._best_path, state=self._best_cost_obj, timeout_reached=self._timeout_reached)

    def find_shortest_subpath(self, start_route: Route, cost_obj: T):
        open_positions: list[np.uint16] = [idx for idx in (np.uint16(idx) for idx in range(self._num)) if idx not in start_route]
        open_slots: int = self._num - len(start_route)
        if self._time_limit is not None:
            if self._timeout_reached:
                return
            timeout = open_slots == 1 and time.time() - self._start_time > self._time_limit
            if timeout:
                self._timeout_reached = True
            # not returning immediately ensures that at least one solution will be found, since we are at the final level already
        for idx in open_positions:
            new_cost_obj = self._transition_costs(start_route, idx, cost_obj)
            new_costs: float = self._eval_costs(new_cost_obj)
            self._iteration_cnt += 1
            if new_costs >= self._best_costs:
                continue
            new_route = np.append(start_route, idx)
            if open_slots == 1:  # we already know costs are lower than the current best costs
                self._best_costs = new_costs
                self._best_cost_obj = new_cost_obj
                self._best_path = new_route
            else:
                if self._timeout_reached:
                    return
                if self._use_bound_estimation:
                    other_costs = np.sum(self._lower_mean_transition[open_positions])
                    estimated_costs = new_costs + self._bound_factor_upcoming_costs * other_costs
                    if estimated_costs >= self._best_costs:
                        continue
                self.find_shortest_subpath(new_route, new_cost_obj)


class GlobalSearchBB[T](GlobalCostsTspSolver[T]):
    """
    A branch and bound algorithm, which iterates through all permutations, but with the option to
        - set a time limit
        - short-circuit on routes whose anticipated costs are too high; this is configured via the parameter
              bound_factor_upcoming_costs; a value 0 disables this behaviour, whereas value 1 somewhat aggressively short-circuits routes.
    The algorithms iterates the permutations in a depth-first way, and in order to allow for efficient short-circuiting
    of expensive routes it is important to start with a good configuration. A different algorithm might be used for this purpose, e.g., one
    that only evaluates local costs.
    """

    def __init__(self, bound_factor_upcoming_costs: float|dict[int, float] = 0.25):
        """
        Parameters:
            bound_factor_upcoming_costs: This factor is used to anticipate a lower bound for the costs of a route after
                    the initial selection of some nodes. Common values are between 0 and 1, but larger values are allowed, as well.
                If this is a dictionary then keys must be sorted in an ascending way; keys are number of nodes. Example:
                    { 5: 0.25, 25: 1} means that below 5 nodes the bound factor will be set to 0, for 5 nodes it will be set to 0.25,
                     and above and starting with 25 nodes the factor will be 1. Between 5 and 25 nodes it will be linearly interpolated.
        """
        self._bound_factor_upcoming_costs: float|dict[int, float] = bound_factor_upcoming_costs

    def find_shortest_path_global(self, data: GlobalTspInput) -> TspResult[T]:
        return _GlobalSearchBBScenario(data.local_transition_costs, data.transition_costs, data.eval_costs, data.empty_state,
                                       time_limit=data.time_limit, local_start_costs=data.local_start_costs,
                                       bound_factor_upcoming_costs=self._bound_factor_upcoming_costs).find_shortest_path()
