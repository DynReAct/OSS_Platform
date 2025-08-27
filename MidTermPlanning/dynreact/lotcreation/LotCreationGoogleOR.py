from ortools.constraint_solver import routing_enums_pb2
from ortools.constraint_solver import pywrapcp
import numpy as np


# M0 - Transition Matrix
# T0 - Initial order transition costs
def path_converingOR(M0, T0 = None):

    """Entry point of the program."""
    # Instantiate the data problem.

    if T0 is None: T0 = np.zeros(M0.shape[0])

    manager = pywrapcp.RoutingIndexManager(len(M0) + 1, 1 #num_vehicles
                                                  , 0 #depot
    )

    # Create Routing Model.
    routing = pywrapcp.RoutingModel(manager)


    def distance_callback(from_index, to_index):

        """Returns the distance between the two nodes."""
        # Convert from routing variable Index to distance matrix NodeIndex.
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)

        if to_node == 0: return 0
        if from_node == 0: return (T0[to_node - 1] * 1000).astype(int) # connecting order
        
        return (M0[from_node - 1][to_node - 1] * 1000).astype(int)


    transit_callback_index = routing.RegisterTransitCallback(distance_callback)

    # Define cost of each arc.
    routing.SetArcCostEvaluatorOfAllVehicles(transit_callback_index)

    # Setting first solution heuristic.
    search_parameters = pywrapcp.DefaultRoutingSearchParameters()
    search_parameters.first_solution_strategy = (routing_enums_pb2.FirstSolutionStrategy.CHRISTOFIDES)

    #search_parameters.local_search_metaheuristic = (
    #  routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH)
    #search_parameters.solution_limit = 1000 # .time_limit.seconds = 1
    #search_parameters.log_search = True

    # Solve the problem.
    solution = routing.SolveWithParameters(search_parameters)

    
    index = routing.Start(0)
    route = []
    while not routing.IsEnd(index):
      index = solution.Value(routing.NextVar(index))
      ni = manager.IndexToNode(index)
      if ni > 0: route.append(ni - 1)
    
    return route