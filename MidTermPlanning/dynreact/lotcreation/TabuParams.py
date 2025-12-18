import multiprocessing as mp
import os
from typing import Literal

import dotenv


class TabuParams:
    """
    Parameters for the mid-term planning algorithm.
    """

    ntotal: int = 1000
    "Number of TabuSearch Iterations, if not explicitly specified via the run(max_iterations=...) parameter."
    Expiration: int = 10
    "Tabu List expiration"
    ExpirationAfterShuffle: int = 4
    "Tabu List expiration after reshuffle"
    NMinUntilShuffle: int = 5
    "number of local minima to be reached until shuffeling"
    NParallel: int = min(mp.cpu_count(), 8)
    "parallel processing -> Set to 1 for debugging"
    TAllowed: float = 4
    "Maximum transition cost within lot; cf. new lot costs in cost provider (default: 3, for SimpleCostProvider)"
    CostNaN: float = 50.0
    "default if cost can not be calculated"
    tsp_solver_global_costs: Literal["ortools", "globalbb", "default"] = "default"
    """
    The algorithm to be used for sorting of orders assigned to one equipment. This is a traveling salesman problem,
    but with path-dependent costs. The options are
        - ortools: simply ignores global costs for scheduling and considers only local transition costs. Classical TSP solver.
        - global_bb: sort of brute force solver with some basic short-circuiting for expensive paths 
            (short-circuiting only evaluates local costs, less suitable for situations with high global/path-dependent cost contributions)
        - default: a combination that first finds a good local solution and then employs the global solver from this starting point 
    """
    tsp_solver_global_bound_factor: float|None = None
    """
    For the global tsp solver this factor determines the early stopping behaviour. If it is zero, no early stopping happens and the
    solver is guaranteed to find the optimum solution (unless the timeout parameter is set, which it is by default), if it is one a 
    somewhat aggressive early stopping strategy is used, which might lead to good solutions being missed, but should improve performance.
    By default, the factor is selected chosen on the number of orders assigned to the equipment, the more orders, the higher the factor. 
    """
    tsp_solver_global_timeout: float = 1
    """
    Timeout in seconds for the global tsp solver. Default: 1s. Set to zero or a negative value to disable the timeout, 
    which may lead to excessive optimization durations.
    """
    tsp_solver_final_tsp: bool = True
    """
    If enabled (by default it is), the tsp solver will be run once again at the end of each iteration, if either  
    the tsp solver timed out for the best solution, or was not run at all for the best solution.
    """
    tsp_solver_final_timeout: float = 4
    """
    Timeout in seconds for a final tsp optimization in each iteration of the optimization.
    Typically, this timeout should be set to a higher value than tsp_sovler_global_timeout, since this optimization
    will not run so often.
    """
    tsp_solver_ortools_timeout: int = 1
    """
    Timeout for the ortools solver in seconds. Default: 1s. Only integer values supported
    """
    max_tsps_per_worker: int = 3
    """
    Maximum number of traveling salesman problems to be solved per worker process in each optimization step.
    Set to a negative number for unlimited tsps (may impact performance, but sensible for tests which require a deterministic behaviour), 
    or to zero to completely disable the traveling salesman solver 
    (in this case a simplistic heuristic will be used instead, not recommended).  
    """
    rand_seed: int|None = None
    """
    Pseudo-random seed for tests.  
    """

    def __init__(self,
                 ntotal: int|None = None,
                 Expiration: int|None = None,
                 ExpirationAfterShuffle: int|None = None,
                 NMinUntilShuffle: int|None = None,
                 NParallel: int|None = None,
                 TAllowed: float|None = None,
                 CostNaN: float|None = None,
                 tsp_solver_global_costs: Literal["ortools", "globalbb", "default"]|None = None,
                 tsp_solver_global_bound_factor: float | None = None,
                 tsp_solver_global_timeout: float|None = None,
                 tsp_solver_final_tsp: bool|None = None,
                 tsp_solver_final_timeout: float|None = None,
                 tsp_solver_ortools_timeout: int|None = None,
                 max_tsps_per_worker: int|None = None,
                 rand_seed: int|None = None
    ):
        dotenv.load_dotenv()
        if ntotal is None:
            ntotal = int(os.getenv("TABU_ITERATIONS", TabuParams.ntotal))
        self.ntotal = ntotal
        "Number of TabuSearch Iterations"
        if Expiration is None:
            Expiration = int(os.getenv("TABU_LIST_EXPIRATION", TabuParams.Expiration))
        self.Expiration = Expiration
        "Tabu List expiration"
        if ExpirationAfterShuffle is None:
            ExpirationAfterShuffle = int(os.getenv("TABU_LIST_EXPIRATION_AFTER_SHUFFLE", TabuParams.ExpirationAfterShuffle))
        self.ExpirationAfterShuffle = ExpirationAfterShuffle
        if NMinUntilShuffle is None:
            NMinUntilShuffle = int(os.getenv("TABU_LOCAL_MIN_UNTIL_SHUFFEL") or os.getenv("TABU_LOCAL_MIN_UNTIL_SHUFFLE") or TabuParams.NMinUntilShuffle)
        self.NMinUntilShuffle = NMinUntilShuffle
        "number of local minima to be reached until shuffeling"
        if NParallel is None:
            NParallel = int(os.getenv("TABU_NUM_CORES", TabuParams.NParallel))
        self.NParallel = NParallel
        "parallel processing -> Set to 1 for debugging"
        if TAllowed is None:
            TAllowed = float(os.getenv("TABU_MAX_TRANSITION_COST", TabuParams.TAllowed))
        self.TAllowed = TAllowed
        "Maximum transition cost within lot"
        if CostNaN is None:
            CostNaN = float(os.getenv("TABU_COST_NAN", TabuParams.CostNaN))
        self.CostNaN = CostNaN
        "default if cost cannot be calculated"
        if tsp_solver_global_costs is None:
            tsp_solver_global_costs = os.getenv("TABU_GLOBAL_COSTS_SOLVER", TabuParams.tsp_solver_global_costs).lower().strip()
            if tsp_solver_global_costs not in ("ortools", "globalbb", "default"):
                raise ValueError("Invalid tsp solver", tsp_solver_global_costs)
        self.tsp_solver_global_costs = tsp_solver_global_costs
        if tsp_solver_global_bound_factor is None:
            tsp_solver_global_bound_factor0 = os.getenv("TABU_GLOBAL_COSTS_BOUND_FACTOR")
            if tsp_solver_global_bound_factor0 is not None:
                tsp_solver_global_bound_factor = float(tsp_solver_global_bound_factor0)
        self.tsp_solver_global_bound_factor = tsp_solver_global_bound_factor
        if tsp_solver_global_timeout is None:
            tsp_solver_global_timeout = float(os.getenv("TABU_GLOBAL_COSTS_TIMEOUT", TabuParams.tsp_solver_global_timeout))
        self.tsp_solver_global_timeout = tsp_solver_global_timeout
        if tsp_solver_final_tsp is None:
            tsp_solver_final_tsp0 = os.getenv("TABU_FINAL_TSP")
            if tsp_solver_final_tsp0 is not None:
                tsp_solver_final_tsp = tsp_solver_final_tsp0.lower() == "true" or tsp_solver_final_tsp0 == "1"
            else:
                tsp_solver_final_tsp = TabuParams.tsp_solver_final_tsp
        self.tsp_solver_final_tsp = tsp_solver_final_tsp
        if tsp_solver_final_timeout is None:
            tsp_solver_final_timeout = float(os.getenv("TABU_FINAL_COSTS_TIMEOUT", TabuParams.tsp_solver_final_timeout))
        self.tsp_solver_final_timeout = tsp_solver_final_timeout
        if tsp_solver_ortools_timeout is None:
            tsp_solver_ortools_timeout = float(os.getenv("TABU_ORTOOLS_TIMEOUT", TabuParams.tsp_solver_ortools_timeout))
        self.tsp_solver_ortools_timeout = tsp_solver_ortools_timeout
        if max_tsps_per_worker is None:
            max_tsps_per_worker = int(os.getenv("TABU_MAX_TSPS", TabuParams.max_tsps_per_worker))
        self.max_tsps_per_worker = max_tsps_per_worker
        if rand_seed is None:
            rand_seed0 = os.getenv("TABU_RAND_SEED")
            if rand_seed0 is not None and rand_seed0 != "":
                rand_seed = int(rand_seed0)
        self.rand_seed = rand_seed
