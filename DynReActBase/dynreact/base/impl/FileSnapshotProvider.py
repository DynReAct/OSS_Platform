import os.path
import pickle
from datetime import datetime, timezone
import glob
from pathlib import Path
from typing import Literal, Iterator

import pandas as pd

from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Snapshot, Site, Equipment, Process, Material, Order, Lot


class FileSnapshotProvider(SnapshotProvider):
    """
    Can read snapshot from json or pickle files and also store in those file types
    """

    _FILE_TYPES = ["csv", "json", "pickle"]
    _DATETIME_FORMAT = "%Y-%m-%dT%H_%M"

    def __init__(self, uri: str, site: Site,
                 file_type: Literal["csv", "json", "pickle"] = "csv"):  # TODO how to pass parameters?
        super().__init__(uri, site)
        uri = uri.lower()
        if not uri.startswith("default+file:"):
            raise NotApplicableException("Unexpected URI for file snapshot provider: " + str(uri))
        self._folder = uri[len("default+file:"):]
        self._file_type: Literal["csv", "json", "pickle"] = file_type
        Path(self._folder).mkdir(parents=True, exist_ok=True)
        self._snapshot_ids: dict[str, datetime] = {}
        self._snapshots: dict[datetime, Snapshot] = {}

    @staticmethod
    def _extract_timestamp(fl: str) -> datetime | None:
        last_sep = fl.rindex("/")
        file0 = (fl if last_sep < 0 else fl[last_sep + 1:]).lower()
        dot = file0.rindex(".")
        if dot < 0 or not file0.startswith("snapshot_"):
            return None
        file0 = file0[len("snapshot_"):dot]
        try:
            return datetime.strptime(file0, FileSnapshotProvider._DATETIME_FORMAT).astimezone(tz=timezone.utc)
        except (ValueError, TypeError):
            return None

    def snapshots(self, start_time: datetime, end_time: datetime, order: Literal["asc", "desc"] = "asc") -> Iterator[
        datetime]:
        if len(self._snapshot_ids) > 0:
            return iter(self._snapshot_ids.values())
        matches = [f for f in (f.replace("\\", "/") for f in  sorted(glob.glob(os.path.join(self._folder, "*.[json,pickle]*"), recursive=False),
                                      reverse=order == "desc")) if "snapshot" in f and ("/" not in f or f.rindex("/") < f.rindex("snapshot"))]
        num_matches: int = len(matches)
        if num_matches == 1:
            ts: datetime | None = FileSnapshotProvider._extract_timestamp(matches[0])
            if ts is None:
                ts = DatetimeUtils.now().replace(second=0, microsecond=0)
            self._snapshot_ids[matches[0]] = ts
        else:
            for file in matches:
                ts: datetime | None = FileSnapshotProvider._extract_timestamp(file)
                if ts is None:
                    continue
                self._snapshot_ids[file] = ts
        return iter(self._snapshot_ids.values())

    def load(self, *args, time: datetime | None = None, **kwargs) -> Snapshot | None:
        timestamp = self.previous(time=time) if time is not None else self.previous()
        if timestamp is None:
            return None
        if len(self._snapshots) > 0:
            for ts, snap in self._snapshots.items():
                if timestamp == ts:
                    return snap
        for file, ts in self._snapshot_ids.items():
            if timestamp == ts:
                snap = self._read_file(file, timestamp, *args, **kwargs)
                if snap is not None:
                    self._snapshots[ts] = snap
                    return snap
        return None

    def _read_file(self, fl: str, timestamp: datetime, *args, **kwargs) -> Snapshot | None:
        if fl.lower().endswith("csv") or ("content_type" in kwargs and kwargs["content_type"] == "text/csv"):
            return self._read_csv(fl, timestamp)
        if "content_type" not in kwargs and fl.endswith(".pickle"):
            kwargs["content_type"] = "application/python-pickle"  # not a standard type, but everything ending in "pickle" is recognized by the pydantic module
        snapshot = Snapshot.parse_file(fl, *args, **kwargs)
        return snapshot

    def _read_csv(self, file: str, timestamp: datetime) -> Snapshot:
        frame: pd.DataFrame = pd.read_csv(file, sep=";", dtype={"id": str, "order": str,
                                                "process": "Int64", "order_position": "Int64"})
        col_names = frame.columns
        material_cols: dict[str, int] = {c[len("material_"):]: idx for idx, c in enumerate(col_names) \
                                         if c.startswith("material_")}
        plants: dict[str, Equipment] = {p.name_short: p for p in self._site.equipment}
        processes: list[Process] = self._site.processes
        coils: list[Material] = []
        orders: dict[str, Order] = {}
        lots: dict[int, list[Lot]] = {}
        # inline_coils: dict[int, list[InlineCoil]] = {}
        categories = self._site.material_categories

        for row in frame.itertuples(index=False):
            if isinstance(row.plant,float):
                plant_name = None
            else:
                plant_name: str = row.plant if len(row.plant) > 0 else None
            plant: int | None = None
            if plant_name in plants:  # e.g. if the production stage is not considered
                plant = plants[plant_name].id
            process_id = int(row.process)
            process = next((p for p in processes if process_id in p.process_ids), None)
            if process is None:
                raise Exception(f"Process not found for coil {row.id}, process id {process_id}")
            order = row.order
            weight = float(row.weight)
            c = Material(id=row.id, order=order, current_equipment=plant, current_equipment_name=plant_name,
                         current_process=process_id, current_process_name=process.name_short,
                         weight=weight, order_position=int(row.order_position), current_storage=row.storage)
            coils.append(c)
            o = orders.get(order)
            # TODO lots, inline coils, etc
            if o is None:
                allowed_plants = [int(p) for p in row.allowed_plants.split(",")]
                o = Order(id=order, current_processes=[process_id], allowed_equipment=allowed_plants,
                          active_processes={process_id: "PENDING"}, actual_weight=weight,
                          target_weight=float(row.order_weight), material_classes={},
                          material_properties={col: row[idx] for col, idx in material_cols.items()})
                for cat in categories:
                    clzz = self.material_class_for_order(o, cat)
                    if clzz is not None:
                        o.material_classes[cat.id] = clzz.id
                orders[order] = o
                if plant is not None:
                    o.current_equipment = [plant]
            else:
                o.actual_weight += weight
                if process not in o.current_processes:
                    o.current_processes.append(process_id)
                    o.current_processes = sorted(o.current_processes)
                    o.active_processes[process_id] = "PENDING"
                if plant is not None:
                    if o.current_equipment is None:
                        o.current_equipment = []
                    if plant not in o.current_equipment:
                        o.current_equipment.append(plant)
        # TODO lots, inline_coils?
        snapshot = Snapshot(timestamp=timestamp, orders=list(orders.values()), material=coils, lots={}, inline_material={})
        return snapshot

    def store(self, snapshot: Snapshot, *args, **kwargs):  # TODO json
        formatted = snapshot.timestamp.strftime(FileSnapshotProvider._DATETIME_FORMAT)
        file_type = self._file_type
        fl = os.path.join(self._folder, "snapshot_" + formatted + "." + self._file_type)
        lower = fl.lower()
        if file_type is None:
            if lower.endswith(".json"):
                file_type = "json"
            elif lower.endswith(".pkle"):
                file_type = "pickle"
        if file_type is None:
            raise Exception("Unknown file type " + str(fl))
        if file_type == "json":
            json_string: str = snapshot.json(exclude_none=True)
            with open(fl, "w") as writer:
                writer.write(json_string)
        elif file_type == "pickle":
            with open(fl, "wb") as writer:
                pickle.dump(snapshot, writer, pickle.HIGHEST_PROTOCOL)  # highest protocol reasonable?
        else:
            raise Exception("Unknown file type " + str(fl))


if __name__ == "__main__":
    provider = FileSnapshotProvider("default+file:./data/sample", None)
    print(list(provider.snapshots(datetime.fromtimestamp(0, tz=timezone.utc), datetime.fromtimestamp(999_999_999, tz=timezone.utc))))

