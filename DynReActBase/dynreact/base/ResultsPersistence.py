from datetime import datetime, date
from typing import Literal, Sequence

from dynreact.base.LotsOptimizer import LotsOptimizationState
from dynreact.base.model import Site, MidTermTargets, StorageLevel


class ResultsPersistence:
    """
    A service to load and store mid-term planning and long-term planning optimization results
    """

    def __init__(self, url: str, site: Site):
        self._url = url
        self._site = site

    # ====================
    # Mid term planning
    # ====================

    def store(self, solution_id: str, solution: LotsOptimizationState) -> str:
        raise Exception("not implemented")

    def delete(self, snapshot_id: datetime, process: str, solution_id: str) -> bool:
        raise Exception("not implemented")

    def load(self, snapshot_id: datetime, process: str, solution_id: str) -> LotsOptimizationState:
        raise Exception("not implemented")

    def solutions(self, snapshot_id: datetime, process: str) -> list[str]:
        raise Exception("not implemented")

    # ====================
    # Long term planning
    # ====================

    def store_ltp(self, solution_id: str, results: MidTermTargets, storage_levels: Sequence[dict[str, StorageLevel]]|None=None) -> str:
        raise Exception("not implemented")

    def delete_ltp(self, start_time: datetime, solution_id: str) -> bool:
        raise Exception("not implemented")

    def load_ltp(self, start_time: datetime, solution_id: str) -> tuple[MidTermTargets, Sequence[dict[str, StorageLevel]]|None]:
        raise Exception("not implemented")

    def solutions_ltp(self, start_time: datetime) -> Sequence[str]:
        raise Exception("not implemented")

    def start_times_ltp(self, start: datetime|None=None, end: datetime|None=None, sort: Literal["asc", "desc"]="asc", limit: int=100) -> Sequence[datetime]:
        raise Exception("not implemented")

    def has_solution_ltp(self, start_time: datetime, solution_id: str) -> bool:
        raise Exception("not implemented")

    def start_months_ltp(self, start: date|None=None, end: date|None=None, sort: Literal["asc", "desc"]="asc", limit: int=100) -> Sequence[date]:
        start_dt = datetime(year=start.year, month=start.month, day=start.day).astimezone() if start is not None else None
        end_dt = datetime(year=end.year, month=end.month, day=end.day).astimezone() if end is not None else None
        results = self.start_times_ltp(start=start_dt, end=end_dt, sort=sort, limit=30*limit if limit is not None else None)
        months = []
        for result in results:
            month = result.date().replace(day=1)
            if month not in months:
                months.append(month)
        return months
