import functools
from datetime import datetime
import glob
import os
from typing import Any, Literal

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

    @staticmethod
    def _to_path_component(val0: str):
        val = val0
        if ".." in val:
            raise Exception("Invalid path component " + val0)
        val = val.replace("//", "/")
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

    def _get_folder_longterm(self, start_time: datetime):
        millis = FileResultsPersistence._sanitize_datetime(start_time)
        folder = os.path.join(self._folder, "longterm", millis)
        return folder

    def _get_file_lotcreation(self, snapshot_id: datetime, process: str, solution_id: str):
        return os.path.join(self._get_folder_lotcreation(snapshot_id, process),
                            FileResultsPersistence._to_path_component(solution_id) + ".json")

    def _get_file_longterm(self, start_time: datetime, solution_id: str):
        return os.path.join(self._get_folder_longterm(start_time),
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
        start_time: datetime = results.period[0]
        if next(iter(results.production_sub_targets), None) is None or next(iter(results.sub_periods), None) is None:
            raise Exception("No shifts?")
        folder = self._get_folder_longterm(start_time)
        os.makedirs(folder, exist_ok=True)
        new_file = self._get_file_longterm(start_time, solution_id)
        json_str = results.model_dump_json(exclude_unset=True, exclude_none=True)
        json_full = "{\n    \"targets\": " + json_str
        if storage_levels:
            json_full += ",\n    \"storage_levels\": " + pydantic_core.to_json(storage_levels, exclude_none=True).decode("utf-8")
                        #json.dumps(pydantic_core.to_jsonable_python(storage_levels, exclude_none=True))
        json_full += "\n}"
        with open(new_file, "w") as file:
            file.write(json_full)
        self.load_ltp.cache_clear()
        return FileResultsPersistence._solution_id_for_file(new_file)

    def delete_ltp(self, start_time: datetime, solution_id: str) -> bool:
        file = self._get_file_longterm(start_time, solution_id)
        if not os.path.isfile(file):
            return False
        os.remove(file)
        self.load_ltp.cache_clear()
        return True

    @functools.lru_cache(maxsize=32)
    def load_ltp(self, start_time: datetime, solution_id: str) -> tuple[MidTermTargets, list[dict[str, StorageLevel]]|None]:
        file = self._get_file_longterm(start_time, solution_id)
        if not os.path.isfile(file):
            raise Exception(f"Solution {solution_id} does not exist for start time {start_time}, no such file: {file}")
        content = None
        with open(file, "r") as fl:
            content = fl.read()
        ta = TypeAdapter(dict[str, MidTermTargets|list[dict[str, StorageLevel]]])
        model = ta.validate_json(content)
        targets = model.get("targets")
        storage_levels = model.get("storage_levels", None)
        return targets, storage_levels

    def has_solution_ltp(self, start_time: datetime, solution_id: str) -> bool:
        file = self._get_file_longterm(start_time, solution_id)
        return os.path.isfile(file)

    def start_times_ltp(self, start: datetime|None=None, end: datetime|None=None, sort: Literal["asc", "desc"]="asc", limit: int=100) -> list[datetime]:
        # TODO cache folder names?
        folder = os.path.join(self._folder, "longterm")
        start_ms = DatetimeUtils.to_millis(start) if start is not None else None
        end_ms = DatetimeUtils.to_millis(end) if end is not None else None
        sub_folders = sorted(dir for dir in glob.glob(folder + "/*") if os.path.isdir(dir))
        sub_folders_as_millis = (FileResultsPersistence._folder_name_to_millis(FileResultsPersistence._solution_id_for_file(dir, strip_ending=False)) for dir in sub_folders)
        sub_folders_as_millis = [dir for dir in sub_folders_as_millis if dir is not None and (start_ms is None or dir >= start_ms) and (end_ms is None or dir < end_ms)]
        if sort == "desc":
            sub_folders_as_millis = list(reversed(sub_folders_as_millis))
        if limit is not None and len(sub_folders_as_millis) > limit:
            sub_folders_as_millis = sub_folders_as_millis[0:limit]
        return [DatetimeUtils.to_datetime(dir) for dir in sub_folders_as_millis]

    def solutions_ltp(self, start_time: datetime) -> list[str]:
        folder = self._get_folder_longterm(start_time)
        if not os.path.isdir(folder):
            return []
        return [FileResultsPersistence._solution_id_for_file(fl) for fl in glob.glob(folder + "/*.json")]


    @staticmethod
    def _folder_name_to_millis(folder: str) -> int | None:
        try:
            return int(folder)
        except ValueError:
            return None
