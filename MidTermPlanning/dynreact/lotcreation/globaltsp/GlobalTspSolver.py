import dataclasses
from typing import Callable, TypeVar, Generic

import numpy as np
import numpy.typing as npt

# TODO this is Python 12 syntax, need to support Python 11, as well
Route = npt.NDArray[np.uint16]   # 1D array
"""
A route between points [0, 1, 2, ... ], represented as a 1D array of the form [3, 0, 2, ...].
"""

T = TypeVar("T")


@dataclasses.dataclass(frozen=True)
class TspInput:
    local_transition_costs: npt.NDArray[np.float32]
    "2D Matrix of transition costs between items"
    local_start_costs: npt.NDArray[np.float32] | None
    "Optional start costs for items, a 1D vector."
    time_limit: float | None
    "An optional time limit for the optimization"


@dataclasses.dataclass(frozen=True)
class GlobalTspInput(TspInput, Generic[T]):
    transition_costs: Callable[[Route, np.uint16 | int, T], T]
    """
    Transition costs are a function of the route taken so far, the next item to visit, and the accumulated costs so far.
    Since it is often required to keep track of additional state information than just the accumulated costs, a 
    generic parameter T is used, instead of just the costs.
    It is assumed that the transition costs are always greater or equal to the corresponding local transition costs,
    otherwise the algorithms may lead to suboptimal results. 
    """
    eval_costs: Callable[[T], float]
    """
    Extract total costs from the state object T.
    """
    empty_state: T
    """
    Initial state for an empty route.
    """


@dataclasses.dataclass(frozen=True)
class TspResult(Generic[T]):
    """
    The best route determined by a TSP solver, along with its costs/state value.
    """

    route: Route
    state: T
    "For local solvers this is the cost"
    timeout_reached: bool|None = None


class GlobalCostsTspSolver(Generic[T]):
    """
    A traveling salesman solver that can potentially consider global costs.
    """

    def find_shortest_path_global(self, data: GlobalTspInput[T]) -> TspResult[T]:
        raise Exception("not implemented")


class TspSolver(GlobalCostsTspSolver[float]):
    """
    A classical traveling salesman solver that only evaluates local transition costs.
    It can also solve the global (path-dependent) problem by ignoring global cost components.
    """

    def find_shortest_path(self, data: TspInput) -> TspResult[float]:
        raise Exception("not implemented")

    def find_shortest_path_global(self, data: GlobalTspInput[float]) -> TspResult[float]:
        return self.find_shortest_path(data)


def local_problem_as_global(data: TspInput) -> GlobalTspInput[float]:
    """
    A global solver can also solve a purely local problem, using this conversion function.
    :param data:
    :return:
    """
    def global_costs(route: Route, next_item: np.uint16, cumulated_costs: float) -> float:
        if len(route) == 0:
            return cumulated_costs + (data.local_start_costs[next_item] if data.local_start_costs is not None else 0.)
        return cumulated_costs + data.local_transition_costs[route[-1], next_item]
    return GlobalTspInput(local_transition_costs=data.local_transition_costs, local_start_costs=data.local_start_costs, time_limit=data.time_limit,
                          transition_costs=global_costs, eval_costs=lambda c: c, empty_state=0.)


def evaluate_route(route: Route, data: GlobalTspInput[T]) -> T:
    """Use the iterative cost function to determine global costs/state of a route"""
    state: T = data.empty_state
    for idx, item in enumerate(route):
        state = data.transition_costs(route[:idx], item, state)
    return state


class PassThroughSolver(GlobalCostsTspSolver[T]):

    def find_shortest_path_global(self, data: GlobalTspInput[T]) -> TspResult[T]:
        route = np.arange(data.local_transition_costs.shape[0], dtype=np.uint16)
        state = evaluate_route(route, data)
        return TspResult(route=route, state=state)

