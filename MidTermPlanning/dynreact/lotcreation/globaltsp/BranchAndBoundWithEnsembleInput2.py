import time
from itertools import groupby
from typing import Callable, Any, Mapping, Sequence, Iterator, Generator

import numpy as np
import numpy.typing as npt

from dynreact.lotcreation.globaltsp.CombinedSolver import permute
from dynreact.lotcreation.globaltsp.GlobalTspSolver import Route, GlobalTspInput, GlobalCostsTspSolver, TspResult, PassThroughSolver
from dynreact.lotcreation.globaltsp.GoogleOrSolver import GoogleOrSolver
from dynreact.lotcreation.globaltsp.NNSolver import NearestNeighbourSolver

"""
The idea of this module is to initialize a branch and bound algorithm with multiple initial routes, which could be, for instance,
the results of other optimization algorithms, so that the likelihood will be high to have at least one good initial route
and hence to prune many bad ones quickly. 
"""


def _evaluate_route[T](route: Route, empty: T, costs:  Callable[[Route, np.uint16 | int, T], T]) -> T:
    state: T = empty
    for idx, item in enumerate(route):
        state = costs(route[:idx], item, state)
    return state


class _SubSolver2[T]:
    """
    A sub solver is associated with one specific start route. It operates in coordinates in which the start route is
    [0, 1, 2, 3, ...]
    """

    def __init__(self,
                 _id: str,
                 data: GlobalTspInput,
                 permutation: Route,  # transform route in this solver's coordinates to original coordinates
                 excluded_routes: Sequence[Route]|None,  # Either excluded_routes or included_route must be specified
                 included_route: Route|None,  # Either excluded_routes or included_route must be specified
                 use_bound_estimation: bool,
                 bound_factor_upcoming_costs: float,
                 lower_mean_transition: npt.NDArray[np.float32]):
        self._id = _id
        num = data.local_transition_costs.shape[0]
        self._num = num
        route_length = lambda r: len(r)
        # keys: route length
        self._excluded_routes: dict[int, list[Route]]|None = {k: v for k, v in groupby(sorted(excluded_routes, key=route_length), key=route_length)} if excluded_routes is not None else {}
        self._included_route: Route|None = included_route
        self._included_length: int|None = len(included_route) if included_route is not None else -1
        self._permutation = permutation
        self._best_state = None
        #self._best_costs = init_cost
        self._best_route = None
        self._best_costs = np.inf
        self._local_transition_costs = data.local_transition_costs
        self._local_start_costs = data.local_start_costs
        self._transition_costs = data.transition_costs
        self._eval_costs = data.eval_costs
        self._empty_state = data.empty_state
        self._use_bound_estimation = use_bound_estimation
        self._bound_factor_upcoming_costs = bound_factor_upcoming_costs
        self._lower_mean_transition = lower_mean_transition

        self._last_route: Route = np.array(range(num), dtype=np.uint16)
        self._last_idx = len(self._last_route) - 2
        self._contingent: int = 0
        self._done: int = 0
        self._exhausted: bool = False

    def done(self) -> bool:
        return self._exhausted

    def run(self, iterations: int, current_best_costs: float) -> Generator[tuple[Route|None, T|None], tuple[float, int], None]:
        """This is used in a sort of work-stealing manner by the orchestrator"""
        if self._exhausted:
            return
        self._best_costs = current_best_costs
        self._best_route = None
        self._best_state = None
        self._contingent = iterations
        self._done = 0
        last_route = self._last_route
        num = self._num
        last_idx = next((idx for idx in reversed(range(num-1)) if last_route[idx] < last_route[idx+1]), None)
        if last_idx is None:
            self._exhausted = True
            return
        sub_route = last_route[:last_idx+1]
        yield from self.find_best_subpath(sub_route)
        if self._best_state is not None:
            yield (self._permutation[self._best_route] if self._best_route is not None else None), self._best_state

    def find_best_subpath(self, start_route: Route):
        for route_length in reversed(range(len(start_route))):
            if route_length <= self._included_length:
                self._exhausted = True
                return
            current_value = start_route[route_length]
            new_start_route = start_route[:route_length]
            open_items = np.array([item for item in range(self._num) if item not in new_start_route], dtype=np.uint16)
            state = _evaluate_route(new_start_route, self._empty_state, self._transition_costs)
            for pos, idx2 in enumerate(open_items):
                if idx2 <= current_value:
                    continue
                next_route = np.append(new_start_route, idx2)
                if route_length in self._excluded_routes:
                    excluded: list[Route] = self._excluded_routes[route_length]
                    has_match: bool = any(ex for ex in excluded if all(item == next_route[idx] for idx, item in enumerate(ex)))
                    if has_match:
                        continue
                next_state = self._transition_costs(new_start_route, idx2, state)
                next_costs: float = self._eval_costs(next_state)
                if next_costs >= self._best_costs:
                    self._done += 1
                    continue
                new_open_items = np.delete(open_items, pos)
                if self._use_bound_estimation:
                    other_costs = np.sum(self._lower_mean_transition[open_items])
                    estimated_costs = next_costs + self._bound_factor_upcoming_costs * other_costs
                    if estimated_costs >= self._best_costs:
                        self._done += 1
                        continue
                yield from self._find_subpath(next_route, next_state, new_open_items)  #  ~= [i for i in open_items if i != idx2]
        self._exhausted = True

    def _find_subpath(self, route: Route, state: T, open_items: npt.NDArray[np.uint16]):
        open_slots = len(open_items)
        route_length = self._num - open_slots + 1  # applies to next_route below
        excluded: list[Route]|None = self._excluded_routes.get(route_length)
        for pos, item in enumerate(open_items):
            next_route = np.append(route, item)
            has_match: bool = excluded is not None and any(ex for ex in excluded if all(item == next_route[idx] for idx, item in enumerate(ex)))
            if has_match:
                continue
            next_state = self._transition_costs(route, item, state)
            next_costs = self._eval_costs(next_state)
            if open_slots == 1:
                self._done += 1    # we need to continue this final iteration, in any case
                self._last_route = next_route
                self._last_idx = route_length-1
            if next_costs >= self._best_costs:
                self._done += 1
                continue
            if open_slots == 1:
                self._best_costs = next_costs
                self._best_state = next_state
                self._best_route = next_route
            else:
                if self._use_bound_estimation:
                    other_costs = np.sum(self._lower_mean_transition[open_items])
                    estimated_costs = next_costs + self._bound_factor_upcoming_costs * other_costs
                    if estimated_costs >= self._best_costs:
                        self._done += 1
                        continue
                yield from self._find_subpath(next_route, next_state, np.delete(open_items, pos))  # [i for i in open_items if i != item])
        if open_slots == 1 and self._done >= self._contingent:
            passed = yield (self._permutation[self._best_route] if self._best_route is not None else None), self._best_state
            if passed is None:
                raise Exception(f"Exception in solver {self._id}, no value sent!")
            self._best_costs = passed[0]
            self._contingent = passed[1]
            self._done = 0
            self._best_state = None


class _BBEnsembleScenario2[T]:

    def __init__(self,
                 data: GlobalTspInput,
                 init_routes: list[Route],
                 bound_factor_upcoming_costs: float | dict[int, float] = 0.25,
                 batch_size: int = 1000
                 ):
        if len(init_routes) == 0:
            raise Exception("No initial routes provided")
        duplicates: list[int] = []
        for idx in range(1, len(init_routes)):
            if any(np.array_equal(init_routes[idx], other, equal_nan=True) for other in init_routes[:idx]):
                duplicates.append(idx)
        for dup in reversed(duplicates):
            init_routes.pop(dup)
        init_states = [_evaluate_route(r, data.empty_state, data.transition_costs) for r in init_routes]
        init_costs = [data.eval_costs(state) for state in init_states]
        init_routes = [route for cost, route in sorted(zip(init_costs, init_routes), key=lambda pair: pair[0])]  # sort routes by costs
        init_states = [state for cost, state in sorted(zip(init_costs, init_states), key=lambda pair: pair[0])]
        init_costs = sorted(init_costs)

        self._local_transition_costs = data.local_transition_costs if isinstance(data.local_transition_costs, np.ndarray) \
            else np.array(data.local_transition_costs, dtype=np.float32)
        self._transition_costs = data.transition_costs
        self._eval_costs = data.eval_costs
        self._num = self._local_transition_costs.shape[0]
        num = self._num
        self._batch_size: int = batch_size
        if batch_size <= 0 or not np.isfinite(batch_size):
            raise ValueError(f"Invalid batch size {batch_size}")
        self._empty_state: T = data.empty_state
        self._init_routes: list[Route] = init_routes
        self._init_states: list[T] = init_states
        self._init_costs: list[float] = init_costs

        self._best_path: Route | None = init_routes[0]
        self._best_costs: float = init_costs[0]
        self._best_cost_obj: T | None = init_states[0]
        # self._init_nearest_neighbors = init_nearest_neighbours
        self._time_limit = data.time_limit
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
                    lower_idx = keys[idx - 1]
                    upper_idx = keys[idx]
                    if num < lower_idx:
                        bound_factor_upcoming_costs = 0
                        break
                    if num <= upper_idx:
                        v0 = bound_factor_upcoming_costs[idx - 1]
                        v1 = bound_factor_upcoming_costs[idx]
                        bound_factor_upcoming_costs = v0 + (num - lower_idx) / (upper_idx - lower_idx) * (v1 - v0)
                        break
                if isinstance(bound_factor_upcoming_costs, Mapping):
                    bound_factor_upcoming_costs = bound_factor_upcoming_costs[keys[l - 1]]
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
        sub_solvers: list[_SubSolver2] = []
        included_routes: dict[int, Route] = {}

        for idx, route in enumerate(self._init_routes):
            transformed_data = permute(data, route)
            common_routes: list[Route] = [route[:_BBEnsembleScenario2._overlap_count(route, other)] for other in self._init_routes[idx + 1:]]
            if idx == 0:
                excluded_routes = [np.append(common, np.uint16(self._init_routes[idx+1+idx2][len(common)])) for idx2, common in enumerate(common_routes)]
                for idx2 in range(len(excluded_routes)):
                    included_routes[idx+1+idx2] = excluded_routes[idx2]
                included_route = None
            else:
                included_route = included_routes[idx]
                excluded_routes = None
                for idx2, other in enumerate(common_routes):
                    if len(other) > len(included_route):
                        excluded_routes = excluded_routes if excluded_routes is not None else []
                        other_idx = idx + 1 + idx2
                        start_route = np.append(other, self._init_routes[other_idx][len(other)])
                        excluded_routes.append(start_route)
                        if len(start_route) > len(included_routes[other_idx]):
                            included_routes[other_idx] = start_route
            # transform those excluded_routes and included_route to new coordinates
            included_route = None if included_route is None else np.arange(len(included_route), dtype=np.uint16)
            rlist = route.tolist()
            excluded_routes = None if excluded_routes is None else [np.array([rlist.index(el) for el in e], dtype=np.uint16) for e in excluded_routes]
            sub_solvers.append(_SubSolver2("SubSolver[" + ",".join(f"{i}" for i in route) + "]", transformed_data, route, excluded_routes, included_route, self._use_bound_estimation,
                           self._bound_factor_upcoming_costs, self._lower_mean_transition[route]))
        self._sub_solvers = sub_solvers

    # must ensure that routes are not equal before calling this
    @staticmethod
    def _overlap_count(r1: Route, r2: Route) -> int:
        return next(idx for idx, el in enumerate(r1) if r2[idx] != el)

    def find_shortest_path(self) -> TspResult[T]:
        timeout: bool = False
        start_time = time.time()
        generators = [s.run(self._batch_size, self._best_costs) for s in self._sub_solvers]
        batch_sizes = [np.max([int((np.max([self._best_costs, 0.01])/c)**2 * self._batch_size), 10]) for c in self._init_costs]  # TODO or update in each iteration based on last costs for the generator?
        start = True
        while len(generators) > 0:
            for_removal = []
            for idx, g in enumerate(generators):
                try:
                    if not start:
                        route, state = g.send((self._best_costs, batch_sizes[idx]))
                    else:
                        route, state = next(g)
                    if state is not None:
                        costs = self._eval_costs(state)
                        if costs < self._best_costs:
                            self._best_costs = costs
                            self._best_cost_obj = state
                            self._best_path = route
                except StopIteration:
                    for_removal.append(idx)
            if self._time_limit is not None and time.time() - start_time > self._time_limit:
                timeout = True
                break
            for idx in reversed(for_removal):
                generators.pop(idx)
                batch_sizes.pop(idx)
            start = False
        return TspResult(self._best_path, self._best_cost_obj, timeout_reached=timeout)

class GlobalSearchBBEnsemble2[T](GlobalCostsTspSolver[T]):
    """
    A branch and bound algorithm, which iterates through all permutations, but with the option to
        - set a time limit
        - short-circuit on routes whose anticipated costs are too high; this is configured via the parameter
              bound_factor_upcoming_costs; a value 0 disables this behaviour, whereas value 1 somewhat aggressively short-circuits routes.
        - initialize different routes
    The algorithms iterates the permutations in a depth-first way, and in order to allow for efficient short-circuiting
    of expensive routes it is important to start with a good configuration. A different algorithm might be used for this purpose, e.g., one
    that only evaluates local costs.
    """

    def __init__(self, init_routes: list[Route], bound_factor_upcoming_costs: float|dict[int, float] = 0.25, batch_size: int=1_000):
        """
        Parameters:
            bound_factor_upcoming_costs: This factor is used to anticipate a lower bound for the costs of a route after
                    the initial selection of some nodes. Common values are between 0 and 1, but larger values are allowed, as well.
                If this is a dictionary then keys must be sorted in an ascending way; keys are number of nodes. Example:
                    { 5: 0.25, 25: 1} means that below 5 nodes the bound factor will be set to 0, for 5 nodes it will be set to 0.25,
                     and above and starting with 25 nodes the factor will be 1. Between 5 and 25 nodes it will be linearly interpolated.
        """
        self._bound_factor_upcoming_costs: float|dict[int, float] = bound_factor_upcoming_costs
        self._batch_size: int = batch_size
        self._init_routes = init_routes

    def find_shortest_path_global(self, data: GlobalTspInput) -> TspResult[T]:
        return _BBEnsembleScenario2(data, self._init_routes, bound_factor_upcoming_costs=self._bound_factor_upcoming_costs, batch_size=self._batch_size).find_shortest_path()


class GlobalSearchDefault[T](GlobalCostsTspSolver[T]):

    def __init__(self, bound_factor_upcoming_costs: float|dict[int, float] = 0.25, batch_size: int=1000, timeout_pre_solvers: float|None=1.):
        """

        """
        self._pre_solvers = [PassThroughSolver(), GoogleOrSolver(), NearestNeighbourSolver()]
        self._bound_factor_upcoming_costs: float|dict[int, float] = bound_factor_upcoming_costs
        self._batch_size: int = batch_size
        self._timeout_pre_solvers = timeout_pre_solvers

    def find_shortest_path_global(self, data: GlobalTspInput) -> TspResult[T]:
        data2 = GlobalTspInput(local_transition_costs=data.local_transition_costs, local_start_costs=data.local_start_costs,
                               transition_costs=data.transition_costs, eval_costs=data.eval_costs, empty_state=data.empty_state,
                               time_limit=self._timeout_pre_solvers)
        init_routes = [s.find_shortest_path_global(data2).route for s in self._pre_solvers]
        return GlobalSearchBBEnsemble2(init_routes=init_routes, bound_factor_upcoming_costs=self._bound_factor_upcoming_costs,
                                batch_size=self._batch_size, ).find_shortest_path_global(data)

