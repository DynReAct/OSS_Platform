import glob
import os
from datetime import datetime, timezone
from typing import Literal, Iterator

from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.impl.AggregationPersistence import AggregationPersistence, AggregationInternal
from dynreact.base.model import AggregatedStorageContent


class FileAggregationPersistence(AggregationPersistence):

    def __init__(self, uri: str):
        super().__init__(uri)
        uri_lower = uri.lower()
        if not uri_lower.startswith("default+file:"):
            raise NotApplicableException("Unexpected URI for file results persistence: " + str(uri))
        folder = uri[len("default+file:"):]
        self._folder = folder
        self._stg_folder = os.path.join(folder, "stg").replace("\\", "/")
        self._prod_folder = os.path.join(folder, "prod").replace("\\", "/")
        os.makedirs(self._stg_folder, exist_ok=True)
        os.makedirs(self._prod_folder, exist_ok=True)
        self._stg_files: dict[str, datetime]|None = None  # keys: file names
        self._prod_files: dict[str, dict[str, datetime]] = {} # outer keys: level, inner keys: file names

    def store_production(self, level: str, value: AggregationInternal):
        level = level.upper()
        folder = os.path.join(self._prod_folder, level)
        os.makedirs(folder, exist_ok=True)
        start: datetime = value.aggregation_interval[0]
        start_id = FileAggregationPersistence._datetime_to_id(start)
        fl = os.path.join(folder, str(start_id) + ".json")
        content = value.model_dump_json(exclude_none=True, exclude_unset=True)
        with open(fl, "w", encoding="utf-8") as file:
            file.write(content)
        if level in self._prod_files:
            t: datetime = FileAggregationPersistence._id_for_file(fl)
            times: list[datetime] = list(self._prod_files[level].values())
            if len(times) == 0 or t >= times[-1]:
                self._prod_files[level][fl] = t
            else:
                self._prod_files.pop(level)

    def store_storage(self, snapshot: datetime, value: AggregatedStorageContent):
        snap_id = FileAggregationPersistence._datetime_to_id(snapshot)
        fl = os.path.join(self._stg_folder, snap_id + ".json")
        content = value.model_dump_json(exclude_none=True, exclude_unset=True)
        with open(fl, "w", encoding="utf-8") as file:
            file.write(content)
        if self._stg_files is not None:
            t: datetime = FileAggregationPersistence._id_for_file(fl)
            times: list[datetime] = list(self._stg_files.values())
            if len(times) == 0 or t >= times[-1]:
                self._stg_files[fl] = t
            else:
                self._stg_files = None  # clear, since we inserted a new file in between existing ones

    def production_values(self, level: str, start: datetime, end: datetime, order: Literal["asc", "desc"]="asc") -> Iterator[datetime]:
        all_files: dict[str, datetime]|None = self._prod_files.get(level)
        if all_files is None:
            level = level.upper()
            folder = os.path.join(self._prod_folder, level)
            if not os.path.isdir(folder):
                return iter([])
            files = sorted(glob.glob(folder + "/*.json"))
            all_files: dict[str, datetime] = {f: dt for f, dt in ((f, FileAggregationPersistence._id_for_file(f)) for f in files) if dt is not None}
            self._prod_files[level] = all_files
        applicable_files = {f: dt for f, dt in all_files.items() if start <= dt < end}
        if order == "desc":
            applicable_files = {key: applicable_files[key] for key in reversed(applicable_files)}
        return iter(applicable_files.values())

    def storage_values(self, start: datetime, end: datetime, order: Literal["asc", "desc"]="asc") -> Iterator[datetime]:
        all_files = self._stg_files
        if all_files is None:
            files = sorted(glob.glob(self._stg_folder + "/*.json"))
            all_files: dict[str, datetime] = {f: dt for f, dt in ((f, FileAggregationPersistence._id_for_file(f)) for f in files) if dt is not None}
            self._stg_files = all_files
        applicable_files = {f: dt for f, dt in all_files.items() if start <= dt < end}
        if order == "desc":
            applicable_files = {key: applicable_files[key] for key in reversed(applicable_files)}
        return iter(applicable_files.values())

    def load_production_aggregation(self, level: str, time: datetime) -> AggregationInternal|None:
        start_id = FileAggregationPersistence._datetime_to_id(time)
        fl = os.path.join(self._stg_folder, level.upper(), str(start_id) + ".json")
        if not os.path.isfile(fl):
            return None
        with open(fl, "r", encoding="utf-8") as file:
            content = file.read()
        result = AggregationInternal.model_validate_json(content)
        return result

    def load_storage_aggregation(self, snapshot: datetime) -> AggregatedStorageContent|None:
        snap_id = FileAggregationPersistence._datetime_to_id(snapshot)
        fl = os.path.join(self._stg_folder, snap_id + ".json")
        if not os.path.isfile(fl):
            return None
        with open(fl, "r", encoding="utf-8") as file:
            content = file.read()
        result = AggregatedStorageContent.model_validate_json(content)
        return result

    @staticmethod
    def _datetime_to_id(dt: datetime) -> str:
        return str(int(round(dt.replace(second=0, microsecond=0).timestamp())))

    @staticmethod
    def _id_for_file(fl: str) -> datetime|None:
        file = fl.replace("\\", "/")
        if "/" in file:
            file = file[file.rindex("/") + 1:]
        if "." not in file:
            return None
        file = file[:file.rindex(".")]
        try:
            return datetime.fromtimestamp(int(file), tz=timezone.utc)
        except ValueError:
            return None

