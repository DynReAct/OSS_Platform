from datetime import datetime

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

    def store_ltp(self, solution_id: str, results: MidTermTargets, storage_levels: list[dict[str, StorageLevel]]|None=None) -> str:
        raise Exception("not implemented")

    def delete_ltp(self, start_time: datetime, solution_id: str) -> bool:
        raise Exception("not implemented")

    def load_ltp(self, start_time: datetime, solution_id: str) -> tuple[MidTermTargets, list[dict[str, StorageLevel]]|None]:
        raise Exception("not implemented")

    def solutions_ltp(self, start_time: datetime) -> list[str]:
        raise Exception("not implemented")

    def start_times_ltp(self, start: datetime, end: datetime) -> list[datetime]:
        raise Exception("not implemented")

    def has_solution_ltp(self, start_time: datetime, solution_id: str) -> bool:
        raise Exception("not implemented")
