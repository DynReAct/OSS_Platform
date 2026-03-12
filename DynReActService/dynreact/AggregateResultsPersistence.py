from datetime import datetime
from typing import Literal, Sequence

from dynreact.base.LotsOptimizer import LotsOptimizationState
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.model import MidTermTargets, StorageLevel, Site


class AggregateResultsPersistence(ResultsPersistence):
    """
    Allows to read results from multiple persistence providers, but does not support writes
    """

    def __init__(self, site: Site, persistences: Sequence[ResultsPersistence]):
        super().__init__("aggregate", site)
        self._delegates = tuple(persistences)

    def load(self, snapshot_id: datetime, process: str, solution_id: str) -> LotsOptimizationState:
        for delegate in self._delegates:
            try:
                result = delegate.load(snapshot_id, process, solution_id)
                if result is not None:
                    return result
            except:
                pass
        return None

    def solutions(self, snapshot_id: datetime, process: str) -> list[str]:
        return [sol for delegate in self._delegates for sol in delegate.solutions(snapshot_id, process)]

    def load_ltp(self, start_time: datetime, solution_id: str) -> tuple[MidTermTargets, list[dict[str, StorageLevel]] | None]:
        for delegate in self._delegates:
            try:
                result = delegate.load_ltp(start_time, solution_id)
                if result is not None and result[0] is not None:
                    return result
            except:
                pass
        return None

    def solutions_ltp(self, start_time: datetime) -> list[str]:
        return [sol for delegate in self._delegates for sol in delegate.solutions_ltp(start_time)]

    def start_times_ltp(self, start: datetime | None = None, end: datetime | None = None, sort: Literal["asc", "desc"] = "asc", limit: int = 100) -> list[datetime]:
        start_times = [sol for delegate in self._delegates for sol in delegate.start_times_ltp(start, end, sort=sort, limit=limit)]
        start_times = [sol for idx, sol in enumerate(start_times) if start_times.index(sol) == idx]  # unique values
        start_times = sorted(start_times) if sort == "asc" else sorted(start_times, reverse=True)
        if limit is not None and len(start_times) > limit:
            start_times = start_times[:limit]
        return start_times

    def has_solution_ltp(self, start_time: datetime, solution_id: str) -> bool:
        return any(delegate.has_solution_ltp(start_time, solution_id) for delegate in self._delegates)
