from datetime import datetime
from typing import Literal

from dynreact.base.LotsOptimizer import LotsOptimizationState
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Site, Process, MidTermTargets, StorageLevel


class MemoryResultsPersistence(ResultsPersistence):
    """For tests"""

    def __init__(self, uri: str, site: Site):
        super().__init__(uri, site)
        uri_lower = uri.lower()
        if not uri_lower.startswith("memory:"):
            raise NotApplicableException(f"Unexpected URI for memory results persistence: {uri}")
        # key from outer to inner: snapshot id, process, solution id
        self._mtp_results: dict[datetime, dict[str, dict[str, LotsOptimizationState]]] = {}
        # outer key: planning period start time, inner key: solution id
        self._ltp_results: dict[datetime, dict[str, tuple[MidTermTargets, list[dict[str, StorageLevel]]|None]]] = {}

    def _sanitize_process(self, process: str) -> str:
        proc: Process | None = self._site.get_process(process)
        if proc is None:
            raise Exception("Process not found " + str(process))
        return proc.name_short

    @staticmethod
    def _sanitize_datetime(snapshot_id: datetime) -> str:
        millis = DatetimeUtils.to_millis(snapshot_id.replace(second=0, microsecond=0))
        if millis is None:
            raise Exception(f"Invalid snapshot id {snapshot_id}")
        return str(millis)

    def store(self, solution_id: str, solution: LotsOptimizationState) -> str:
        if solution.current_solution is None or solution.best_solution is None:
            raise Exception("Solution is None")
        process: str = self._sanitize_process(solution.best_solution.process)
        snap: datetime = next(iter(solution.best_solution.equipment_status.values())).snapshot_id
        if snap not in self._mtp_results:
            self._mtp_results[snap] = {}
        dct = self._mtp_results[snap]
        if process not in dct:
            dct[process] = {}
        dct = dct[process]
        dct[solution_id] = solution
        return solution_id

    def delete(self, snapshot_id: datetime, process: str, solution_id: str) -> bool:
        process = self._sanitize_process(process)
        dct_0 = self._mtp_results
        if snapshot_id not in dct_0:
            return False
        dct_1 = dct_0[snapshot_id]
        if process not in dct_1:
            return False
        dct_2 = dct_1[process]
        if solution_id not in dct_2:
            return False
        dct_2.pop(solution_id)
        if len(dct_2) == 0:
            dct_1.pop(process)
        if len(dct_1) == 0:
            dct_0.pop(snapshot_id)
        return True

    def load(self, snapshot_id: datetime, process: str, solution_id: str) -> LotsOptimizationState:
        process = self._sanitize_process(process)
        dct = self._mtp_results
        if snapshot_id not in dct:
            return None
        dct = dct[snapshot_id]
        if process not in dct:
            return None
        dct = dct[process]
        return dct.get(solution_id)

    def solutions(self, snapshot_id: datetime, process: str) -> list[str]:
        process = self._sanitize_process(process)
        dct = self._mtp_results
        if snapshot_id not in dct:
            return []
        dct = dct[snapshot_id]
        if process not in dct:
            return []
        dct = dct[process]
        return list(dct.keys())

    def store_ltp(self, solution_id: str, results: MidTermTargets,
                  storage_levels: list[dict[str, StorageLevel]] | None = None) -> str:
        start_time = results.period[0]
        if start_time not in self._ltp_results:
            self._ltp_results[start_time] = {}
        self._ltp_results[start_time][solution_id] = (results, storage_levels)
        return solution_id

    def delete_ltp(self, start_time: datetime, solution_id: str) -> bool:
        if start_time not in self._ltp_results:
            return False
        dct = self._ltp_results[start_time]
        if solution_id not in dct:
            return False
        dct.pop(solution_id)
        if len(dct) == 0:
            self._ltp_results.pop(start_time)
        return True

    def load_ltp(self, start_time: datetime, solution_id: str) -> tuple[MidTermTargets, list[dict[str, StorageLevel]]|None]:
        if start_time not in self._ltp_results:
            return None
        return self._ltp_results[start_time].get(solution_id)

    def has_solution_ltp(self, start_time: datetime, solution_id: str) -> bool:
        if start_time not in self._ltp_results:
            return False
        return solution_id in self._ltp_results[start_time]

    def start_times_ltp(self, start: datetime | None = None, end: datetime | None = None,
                        sort: Literal["asc", "desc"] = "asc", limit: int = 100) -> list[datetime]:
        start_times = sorted(list(self._ltp_results.keys()))
        if start or end:
            start_times = [s for s in start_times if (start is None or s >= start) and (end is None or s < end)]
        if sort == "desc":
            start_times = reversed(start_times)
        if limit < len(start_times):
            start_times = start_times[:limit]
        return start_times

    def solutions_ltp(self, start_time: datetime) -> list[str]:
        if start_time not in self._ltp_results:
            return []
        return list(self._ltp_results[start_time].keys())
