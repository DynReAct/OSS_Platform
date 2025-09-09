from enum import StrEnum
from typing import Sequence, TypeVar

from dynreact.lotcreation.globaltsp.GlobalTspSolver import Route, GlobalTspInput, TspInput, TspResult, GlobalCostsTspSolver, TspSolver


class SolverId(StrEnum):

    BranchBound = "branch_bound"
    NearestNeighbour = "nearest_neighbour"
    OrTools = "ortools"
    BranchBoundEnsemble = "bb_ensemble"


T = TypeVar("T")

# def solve[T] -> PYthon 3.12 syntax
def solve(data: GlobalTspInput[T],
             solver_id: SolverId|Sequence[SolverId]|GlobalCostsTspSolver[T] = SolverId.BranchBoundEnsemble) -> TspResult[T]:
    """
    Parameters:
        data: the problem formulation
        solver_id: optional solver id or solver
    Returns:
        the best solution found
    """

    return solver(solver_id).find_shortest_path_global(data)


def solver(solver_id: SolverId|Sequence[SolverId]|GlobalCostsTspSolver[T] = SolverId.BranchBoundEnsemble) -> GlobalCostsTspSolver[T]:
    if solver_id == SolverId.BranchBoundEnsemble:
        from globaltsp.BranchAndBoundWithEnsembleInput2 import GlobalSearchDefault
        solver_id = GlobalSearchDefault()
    elif solver_id == SolverId.BranchBound:
        from globaltsp.GlobalSearchBranchBound import GlobalSearchBB
        solver_id = GlobalSearchBB()
    elif solver_id == SolverId.OrTools:
        from globaltsp.GoogleOrSolver import GoogleOrSolver
        solver_id = GoogleOrSolver()
    elif solver_id == SolverId.NearestNeighbour:
        from globaltsp.NNSolver import NearestNeighbourSolver
        solver_id = NearestNeighbourSolver()
    elif isinstance(solver_id, Sequence) and not isinstance(solver_id, str):
        from globaltsp.CombinedSolver import CombinedSequentialSolver
        solver_id = CombinedSequentialSolver([solver(sid) for sid in solver_id])
    elif not isinstance(solver_id, GlobalCostsTspSolver):
        raise ValueError(f"Unsupported solver {solver_id}")
    return solver_id

