import math

import numpy as np
import numpy.typing as npt
from ortools.constraint_solver import pywrapcp, routing_enums_pb2
from ortools.constraint_solver.routing_parameters_pb2 import RoutingSearchParameters

from dynreact.lotcreation.globaltsp.GlobalTspSolver import Route, TspSolver, TspInput, TspResult


class _GoogleOrInstance:

    def __init__(self,
                 local_transition_costs: npt.NDArray[np.float32],
                 time_limit: int|None = None,
                 local_start_costs: npt.NDArray[np.float32]|None = None,
                 parameters: RoutingSearchParameters | None = None,
                 scaling_factor: int = 100):
        self._local_transition_costs = local_transition_costs if isinstance(local_transition_costs, np.ndarray) \
            else np.array(local_transition_costs, dtype=np.float32)
        self._num = self._local_transition_costs.shape[0]
        self._local_start_costs = local_start_costs if local_start_costs is not None else np.zeros(self._num, dtype=np.float32)
        self._scaling_factor = scaling_factor
        self._best_path: Route | None = None
        self._best_costs: float = np.inf
        if time_limit is not None:
            time_limit = int(time_limit)
            if time_limit <= 0:
                time_limit = None
        self._time_limit: int|None = time_limit
        self._iteration_cnt: int = 0
        self._start_time = None
        if parameters is None:
            parameters: RoutingSearchParameters = pywrapcp.DefaultRoutingSearchParameters()
            # Setting first solution heuristic.
            parameters.first_solution_strategy = (routing_enums_pb2.FirstSolutionStrategy.CHRISTOFIDES)
            # https://developers.google.com/optimization/routing/routing_tasks#time_limits
            if self._time_limit is not None and self._time_limit > 0:
                parameters.time_limit.seconds = math.ceil(self._time_limit)
        self._search_parameters = parameters

    def find_shortest_path(self) -> TspResult[float]:
        manager = pywrapcp.RoutingIndexManager(self._num + 1, 1  # num_vehicles
                                               , 0  # depot
                                               )
        routing = pywrapcp.RoutingModel(manager)
        scaling_factor = self._scaling_factor
        start_costs = self._local_start_costs
        trans_costs = self._local_transition_costs

        def distance_callback(from_index: int, to_index: int) -> int:
            """Returns the distance between the two nodes."""
            # Convert from routing variable Index to distance matrix NodeIndex.
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            if to_node == 0:
                return 0
            if from_node == 0:
                return (start_costs[to_node - 1] * scaling_factor).astype(int)  # connecting order
            return (trans_costs[from_node - 1][to_node - 1] * scaling_factor).astype(int)

        transit_callback_index = routing.RegisterTransitCallback(distance_callback)
        # Define cost of each arc.
        routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)
        solution = routing.SolveWithParameters(self._search_parameters)

        index = routing.Start(0)
        route = []
        while not routing.IsEnd(index):
            index = solution.Value(routing.NextVar(index))
            ni = manager.IndexToNode(index)
            if ni > 0:
                route.append(ni - 1)
        costs: np.float32 = start_costs[route[0]] + sum(trans_costs[route[idx], route[idx+1]] for idx in range(self._num-1))
        return TspResult(route=np.array(route, dtype=np.uint16), state=costs)


class GoogleOrSolver(TspSolver):

    def __init__(self, scaling_factor: int=100, parameters: RoutingSearchParameters|None=None):
        self._scaling_factor: int = scaling_factor
        self._parameters = parameters

    def find_shortest_path(self, data: TspInput) -> TspResult[float]:
        return _GoogleOrInstance(data.local_transition_costs, time_limit=data.time_limit, local_start_costs=data.local_start_costs,
                                 scaling_factor=self._scaling_factor, parameters=self._parameters).find_shortest_path()
