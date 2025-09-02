from typing import Sequence, Any

import numpy as np

from dynreact.lotcreation.globaltsp.GlobalTspSolver import GlobalCostsTspSolver, GlobalTspInput, TspResult, evaluate_route, Route


class CombinedSequentialSolver[T](GlobalCostsTspSolver[T]):
    """
    Takes the result of one solver and feeds it as the start configuration into the next solver.
    """

    def __init__(self, solvers: Sequence[GlobalCostsTspSolver[Any]], time_limits: Sequence[float|None]|None=None):
        self._solvers = solvers
        self._time_limits = time_limits if time_limits is not None else [None for s in solvers]

    def find_shortest_path_global(self, data: GlobalTspInput[T]) -> TspResult[T]:
        time_limits = [t for t in self._time_limits]   # copy
        if data.time_limit is not None:
            time_limits[-1] = data.time_limit
        num: int = data.local_transition_costs.shape[0]
        route = np.arange(num, dtype=np.int16)
        state = evaluate_route(route, data)
        costs = data.eval_costs(state)
        result = TspResult(route, state)
        all_results: list[TspResult[T]] = [result]   # initial config
        all_costs: list[float] = [costs]
        inverse_trafo: Route = route   # initially the identity transformation
        local_data = GlobalTspInput(local_transition_costs=data.local_transition_costs, transition_costs=data.transition_costs,
                                    local_start_costs=data.local_start_costs, eval_costs=data.eval_costs, empty_state=data.empty_state,
                                    time_limit=time_limits[0])
        # TODO test this in a simple setting...
        for idx, solver in enumerate(self._solvers):
            result = solver.find_shortest_path_global(local_data)
            route_in_original_coords = inverse_trafo[result.route]
            all_results.append(TspResult(route=route_in_original_coords, state=result.state, timeout_reached=result.timeout_reached))
            all_costs.append(data.eval_costs(result.state))
            # reshuffle route so we can use the output of solver 1 as input for solver 2 => configurable
            if True:
                # transformation from the new best route to the original coordinates
                inverse_trafo = route_in_original_coords
                local_data = permute(local_data, result.route, time_limit=time_limits[idx])
        return all_results[np.argmin(all_costs)]

def permute[T](data: GlobalTspInput[T], permutation: Route, time_limit: float | None=None) -> GlobalTspInput[T]:
    num: int = len(permutation)
    local_transition_costs = np.array([[data.local_transition_costs[permutation[i], permutation[j]] for j in range(num)] for i in range(num)], dtype=np.float32)
    local_start_costs = None
    if data.local_start_costs is not None:
        local_start_costs = data.local_start_costs[permutation]

    def transition_costs(route: Route, next_item: np.uint16, costs: float) -> float:
        return data.transition_costs(permutation[route], permutation[next_item], costs)

    return GlobalTspInput(local_transition_costs=local_transition_costs, local_start_costs=local_start_costs, transition_costs=transition_costs,
                          eval_costs=data.eval_costs, empty_state=data.empty_state, time_limit=time_limit if time_limit is not None else data.time_limit)

#def _invert_permutation(permutation: Route) -> Route:
#    num = len(permutation)
#    as_list = permutation.tolist()
#    return np.array([as_list.index(idx) for idx in range(num)], dtype=np.uint16)


class EnsembleSolver[T](GlobalCostsTspSolver[T]):
    """
    Compares the results from different solvers and selects the best; all solvers are fed the same start configuration,
    as opposed to CombinedSequentialSolver, where the result of solver i is fed as start config into solver i+1
    """

    def __init__(self, solvers: Sequence[GlobalCostsTspSolver[Any]], time_limits: Sequence[float|None]|None=None):
        self._solvers = solvers
        self._time_limits = time_limits

    def find_shortest_path_global(self, data: GlobalTspInput[T]) -> TspResult[T]:
        results: list[TspResult[T]] = self.find_shortest_paths_global(data)
        costs = [data.eval_costs(r.state) for r in results]
        return results[np.argmin(costs)]

    def find_shortest_paths_global(self, data: GlobalTspInput[T]) -> list[TspResult[T]]:
        dataset = [data for idx in range(len(self._solvers))]
        if self._time_limits is not None:
            dataset = [GlobalTspInput(local_transition_costs=data.local_transition_costs,
                                      local_start_costs=data.local_start_costs, transition_costs=data.transition_costs,
                                      eval_costs=data.eval_costs, empty_state=data.empty_state,
                                      time_limit=self._time_limits[idx]) for idx in range(len(self._solvers))]
        results: list[TspResult[T]] = [solver.find_shortest_path_global(dataset[idx]) for idx, solver in
                                       enumerate(self._solvers)]
        return results
