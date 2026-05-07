import functools
from datetime import datetime, date, timezone, timedelta
import glob
import os
from typing import Any, Literal, Sequence

import pydantic_core
from pydantic import BaseModel, TypeAdapter

from dynreact.base.LotsOptimizer import LotsOptimizationState
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import EquipmentStatus, Site, Process, ProductionPlanning, MidTermTargets, StorageLevel, \
    ObjectiveFunction


class LotsOptimizationStateModel(BaseModel):

    current_solution: ProductionPlanning
    current_object_value: ObjectiveFunction
    best_solution: ProductionPlanning
    best_objective_value: ObjectiveFunction
    #num_iterations: int
    history: list[ObjectiveFunction]
    parameters: dict[str, Any] | None = None


class FileResultsPersistence(ResultsPersistence):

    def __init__(self, uri: str, site: Site):
        super().__init__(uri, site)
        uri_lower = uri.lower()
        if not uri_lower.startswith("default+file:"):
            raise NotApplicableException("Unexpected URI for file results persistence: " + str(uri))
        folder = uri[len("default+file:"):]
        self._folder = folder
        os.makedirs(folder, exist_ok=True)
        # outer keys: months, inner keys: ltp start times, values: solution ids
        self._ltp_ids_cache: dict[date, dict[datetime, list[str]]] = {}
        self._ltp_months_cache: list[date]|None = None

    @staticmethod
    def _to_path_component(val0: str):
        val = val0
        if ".." in val:
            raise Exception("Invalid path component " + val0)
        val = val.replace("\\", "/")
        while val.startswith("/") or val.startswith(" ") or val.startswith("."):
            val = val[1:]
        if len(val) == 0:
            raise Exception("Invalid path component: " + val0)
        return val.replace(" ", "_").replace("/", "_").replace("-", "_").replace(".", "_")\
            .replace(":", "_").replace("<", "_").replace(">", "_")

    def _sanitize_process(self, process: str) -> str:
        proc: Process | None = self._site.get_process(process)
        if proc is None:
            raise Exception("Process not found " + str(process))
        return proc.name_short

    @staticmethod
    def _sanitize_datetime(snapshot_id: datetime) -> str:
        millis = DatetimeUtils.to_millis(snapshot_id.replace(second=0, microsecond=0))
        if millis is None:
            raise Exception("Invalid snapshot id " + str(snapshot_id))
        return str(millis)

    def _get_folder_lotcreation(self, snapshot_id: datetime, process: str):
        process = self._sanitize_process(process)
        millis = FileResultsPersistence._sanitize_datetime(snapshot_id)
        folder = os.path.join(self._folder, "lotcreation", millis, process)
        return folder

    def _get_file_lotcreation(self, snapshot_id: datetime, process: str, solution_id: str):
        return os.path.join(self._get_folder_lotcreation(snapshot_id, process),
                            FileResultsPersistence._to_path_component(solution_id) + ".json")

    def store(self, solution_id: str, solution: LotsOptimizationState) -> str:
        if solution.current_solution is None or solution.best_solution is None:
            raise Exception("Solution is None")
        process: str = self._sanitize_process(solution.best_solution.process)
        first_status: EquipmentStatus = next(iter(solution.best_solution.equipment_status.values()), None)
        if first_status is None:
            raise Exception("No plant status?")
        snapshot_id: datetime = first_status.snapshot_id
        folder = self._get_folder_lotcreation(snapshot_id, process)
        os.makedirs(folder, exist_ok=True)
        new_file = self._get_file_lotcreation(snapshot_id, process, solution_id)
        model = LotsOptimizationStateModel(current_solution=solution.current_solution, best_solution=solution.best_solution,
                                current_object_value=solution.current_object_value, best_objective_value=solution.best_objective_value,
                                #num_iterations=solution.num_iterations
                                history=solution.history, parameters=solution.parameters
                                )
        json_str = model.model_dump_json(exclude_unset=True, exclude_none=True)
        with open(new_file, "w") as file:
            file.write(json_str)
        self.load.cache_clear()
        return FileResultsPersistence._solution_id_for_file(new_file)

    def delete(self, snapshot_id: datetime, process: str, solution_id: str) -> bool:
        file = self._get_file_lotcreation(snapshot_id, process, solution_id)
        if not os.path.isfile(file):
            return False
        os.remove(file)
        self.load.cache_clear()
        return True

    @functools.lru_cache(maxsize=32)
    def load(self, snapshot_id: datetime, process: str, solution_id: str) -> LotsOptimizationState:
        file = self._get_file_lotcreation(snapshot_id, process, solution_id)
        if not os.path.isfile(file):
            raise Exception("Solution " + str(solution_id) + " does not exist for process " + str(process)
                            + " and snapshot " + str(snapshot_id))
        content = None
        with open(file, "r") as fl:
            content = fl.read()
        model = LotsOptimizationStateModel.model_validate_json(content)
        return LotsOptimizationState(model.current_solution, model.current_object_value, model.best_solution,
                                     model.best_objective_value, history=model.history, parameters=model.parameters)

    def solutions(self, snapshot_id: datetime, process: str) -> list[str]:
        folder = self._get_folder_lotcreation(snapshot_id, process)
        if not os.path.isdir(folder):
            return []
        return [FileResultsPersistence._solution_id_for_file(fl) for fl in glob.glob(folder + "/*.json")]

    @staticmethod
    def _solution_id_for_file(file: str, strip_ending: bool=True) -> str:
        file = file.replace("\\", "/")
        if "/" in file:
            file = file[file.rindex("/")+1:]
        if strip_ending and "." in file:
            file = file[:file.rindex(".")]
        return file

    def store_ltp(self, solution_id: str, results: MidTermTargets, storage_levels: list[dict[str, StorageLevel]]|None=None) -> str:
        start_time: datetime = results.period[0].astimezone()  # ensure local timezone
        if next(iter(results.production_sub_targets), None) is None or next(iter(results.sub_periods), None) is None:
            raise Exception("No shifts?")
        month: date = FileResultsPersistence._get_ltp_month(start_time)
        folder = self._get_ltp_folder(month)
        os.makedirs(folder, exist_ok=True)
        filename = self._get_ltp_file(start_time, solution_id)
        new_file = os.path.join(folder, filename)
        if os.path.isfile(new_file):
            raise Exception(f"Solution {solution_id} for start time {start_time} already exists")
        json_str = results.model_dump_json(exclude_unset=True, exclude_none=True)
        json_full = "{\n    \"targets\": " + json_str
        if storage_levels:
            json_full += ",\n    \"storage_levels\": " + pydantic_core.to_json(storage_levels, exclude_none=True).decode("utf-8")
                        #json.dumps(pydantic_core.to_jsonable_python(storage_levels, exclude_none=True))
        json_full += "\n}"
        with open(new_file, "w") as file:
            file.write(json_full)
        self.load_ltp.cache_clear()  # XXX or rather add the new guy to the cache?
        if self._ltp_ids_cache is not None:
            if month not in self._ltp_ids_cache:
                self._ltp_ids_cache[month] = {}
            if start_time not in self._ltp_ids_cache[month]:
                self._ltp_ids_cache[month][start_time] = []
            self._ltp_ids_cache[month][start_time].append(solution_id)
        if self._ltp_months_cache is not None and month not in self._ltp_months_cache:
            next_higher_idx = next((idx for idx, m in enumerate(self._ltp_months_cache) if m > month), len(self._ltp_months_cache))
            self._ltp_months_cache.insert(next_higher_idx, month)
        return FileResultsPersistence._solution_id_for_file(new_file)

    def start_times_ltp(self, start: datetime|None=None, end: datetime|None=None, sort: Literal["asc", "desc"]="asc", limit: int=100) -> Sequence[datetime]:
        if self._ltp_months_cache is None:    # TODO or last update to old?
            self._reload_ltp_months_cache()
        months = self._ltp_months_cache
        if start or end:
            start = start if start is None else start.astimezone()
            end = end if end is None else end.astimezone()
            months = [m for m in months if (start is None or start.date() <= m) and (end is None or end.date() >= m)]
        if len(months) == 0:
            return tuple()
        start_times = []
        if sort == "desc":
            months = reversed(months)
        for month in months:
            if month not in self._ltp_ids_cache:
                self._load_ltp_month_ids(month)
            month_results = self._ltp_ids_cache[month].keys()
            if start or end:
                month_results = [t for t in month_results if (start is None or start <= t) and (end is None or end > t)]
            start_times.extend(sorted(month_results, reverse=sort == "desc"))
        if limit is not None and len(start_times) > limit:
            start_times = start_times[:limit]
        return start_times

    def solutions_ltp(self, start_time: datetime) -> Sequence[str]:
        start_time = start_time.astimezone()
        month = FileResultsPersistence._get_ltp_month(start_time)
        if self._ltp_months_cache is None:
            self._reload_ltp_months_cache()
        if month not in self._ltp_months_cache:
            return tuple()
        if month not in self._ltp_ids_cache:
            self._load_ltp_month_ids(month)
        results: dict[datetime, list[str]] = self._ltp_ids_cache[month]
        return tuple(results[start_time]) if start_time in results else tuple()

    def has_solution_ltp(self, start_time: datetime, solution_id: str) -> bool:
        start_time = start_time.astimezone()
        month = FileResultsPersistence._get_ltp_month(start_time)
        if self._ltp_months_cache is None:
            self._reload_ltp_months_cache()
        if month not in self._ltp_months_cache:
            return False
        if month not in self._ltp_ids_cache:
            self._load_ltp_month_ids(month)
        results: dict[datetime, list[str]] = self._ltp_ids_cache[month]
        return start_time in results and solution_id is results[start_time]

    @functools.lru_cache(maxsize=16)
    def load_ltp(self, start_time: datetime, solution_id: str) -> tuple[MidTermTargets, list[dict[str, StorageLevel]] | None]:
        start_time = start_time.astimezone()
        month = FileResultsPersistence._get_ltp_month(start_time)
        folder = self._get_ltp_folder(month)
        filename = self._get_ltp_file(start_time, solution_id)
        file = os.path.join(folder, filename)
        if not os.path.isfile(file):
            raise Exception(f"Solution {solution_id} does not exist for start time {start_time}, no such file: {file}")
        content = None
        with open(file, "r") as fl:
            content = fl.read()
        ta = TypeAdapter(dict[str, MidTermTargets | Sequence[dict[str, StorageLevel]]])
        model = ta.validate_json(content)
        targets = model.get("targets")
        storage_levels = model.get("storage_levels", None)
        return targets, storage_levels

    def delete_ltp(self, start_time: datetime, solution_id: str) -> bool:
        start_time = start_time.astimezone()
        month = FileResultsPersistence._get_ltp_month(start_time)
        folder = self._get_ltp_folder(month)
        filename = self._get_ltp_file(start_time, solution_id)
        file = os.path.join(folder, filename)
        if not os.path.isfile(file):
            return False
        os.remove(file)
        # cache cleanup
        self.load_ltp.cache_clear()
        if month in self._ltp_ids_cache:
            solutions = self._ltp_ids_cache[month]
            if start_time in solutions and solution_id in solutions[start_time]:
                solutions[start_time].remove(solution_id)
                if len(solutions[start_time]) == 0:
                    solutions.pop(start_time)
                    if len(solutions) == 0:
                        self._ltp_ids_cache.pop(month)
                        try:
                            os.rmdir(self._get_ltp_folder(month))
                        except:
                            pass
                        if self._ltp_months_cache is not None and month in self._ltp_months_cache:
                            self._ltp_months_cache.remove(month)
        return True

    def start_months_ltp(self, start: date | None = None, end: date | None = None, sort: Literal["asc", "desc"] = "asc", limit: int = 100) -> Sequence[date]:
        if self._ltp_months_cache is None:
            self._reload_ltp_months_cache()
        months = self._ltp_months_cache
        if start or end:
            months = [m for m in months if (start is None or m >= start) and (end is None or m < end)]
        if sort == "desc":
            months = list(reversed(months))
        if limit is not None and len(months) > limit:
            months = months[:limit]
        return tuple(months)

    def _reload_ltp_months_cache(self):
        folder = os.path.join(self._folder, "longterm")
        sub_folders = sorted(dir for dir in glob.glob(folder + "/*") if os.path.isdir(dir))
        months = [m for m in (FileResultsPersistence._parse_ltp_month(f) for f in sub_folders) if m is not None]
        self._ltp_months_cache = months

    def _load_ltp_month_ids(self, month: date):
        folder = self._get_ltp_folder(month)
        if not os.path.isdir(folder):
            self._ltp_ids_cache[month] = {}
            return
        files = sorted(file for file in glob.glob(folder + "/*.json") if os.path.isfile(file))
        solutions = {}
        for file in files:
            tm_id = FileResultsPersistence._start_time_and_id_for_file(month, file)
            if tm_id is not None:
                time, id = tm_id
                if time not in solutions:
                    solutions[time] = []
                solutions[time].append(id)
        self._ltp_ids_cache[month] = solutions

    @staticmethod
    def _start_time_and_id_for_file(month: date, filename: str) -> tuple[datetime, str]|None:
        filename = filename.replace("\\", "/")
        if "/" in filename:
            filename = filename[filename.rindex("/")+1:]
        if "_" not in filename or not filename.lower().endswith(".json"):
            return None
        sep = filename.index("_")
        try:
            tm = datetime.strptime(filename[:sep], "%d%H%M")
            tm = tm.replace(year=month.year, month=month.month).astimezone()
        except:
            return None
        return tm, filename[sep+1:-5]

    @staticmethod
    def _get_ltp_month(start_time: datetime) -> date:
        # before calling this ensure start_time is in local timezone
        return start_time.date().replace(day=1)

    @staticmethod
    def _parse_ltp_month(month_str: str) -> date|None:
        month_str = month_str.replace("\\", "/")
        if "/" in month_str:
            last_sep = month_str.rindex("/")
            month_str = month_str[last_sep+1:]
        try:
            return datetime.strptime(month_str, "%Y-%m").date()
        except:
            return None

    def _get_ltp_folder(self, month: date) -> str:
        # before calling this ensure start_time is in local timezone
        return os.path.join(self._folder, "longterm", month.strftime("%Y-%m"))

    def _get_ltp_file(self, start_time: datetime, solution_id: str) -> str:
        start_time_id = start_time.strftime("%d%H%M")
        return start_time_id + "_" + FileResultsPersistence._to_path_component(solution_id) + ".json"
