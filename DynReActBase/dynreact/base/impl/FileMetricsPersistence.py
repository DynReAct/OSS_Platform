import json
import shutil
from datetime import datetime
import os.path
from glob import glob
from pathlib import Path
from typing import Any, Mapping

from pydantic import TypeAdapter, ConfigDict

from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.monitoring import MetricsPersistence, ServiceMetrics, ServiceHealth, Metric, PrimitiveMetric


class FileMetricsPersistence(MetricsPersistence):
    """
    Does not keep track of timestamps, simply overwrites old files, unless the app is restarted
    """

    _dt_format = "%Y-%m-%dT%H_%M"

    def __init__(self, url: str):
        super().__init__(url)
        if not url.startswith("file+json:"):
            raise NotApplicableException
        folder = url[len("file+json:"):]
        if len(folder) == 0:
            raise ValueError(f"Empty directory: {folder}")
        if not os.path.exists(folder):
            Path(folder).mkdir(parents=True, exist_ok=True)
        elif not os.path.isdir(folder):
            raise ValueError(f"Not a directory: {folder}")
        # use a new file for every system restart
        self._folder = folder
        file = os.path.join(folder, datetime.now().astimezone().strftime(FileMetricsPersistence._dt_format) + ".json")
        file_bak = file + ".bak"
        self._file = file
        self._file_bak = file_bak

    def store(self, metrics: Mapping[str, ServiceMetrics], health: Mapping[str, ServiceHealth], timestamp: datetime|None=None):
        metrics_dict = {key: FileMetricsPersistence._serialize(metric) for key, metric in metrics.items()}
        health_dict = TypeAdapter(Mapping[str, ServiceHealth], config=ConfigDict(extra="allow")).dump_python(health, mode="json", round_trip=True)
        timestamp = (timestamp or datetime.now()).astimezone()
        result = {
            "__timestamp__": timestamp.strftime(FileMetricsPersistence._dt_format),
            "metrics": metrics_dict,
            "health": health_dict
        }
        with open(self._file_bak, mode="w") as fl:
            json.dump(result, fl)
        shutil.copy2(self._file_bak, self._file)

    @staticmethod
    def _serialize(metrics: ServiceMetrics) -> dict[str, Any]:
        return {
            "service_id": metrics.service_id,
            "metrics": [metric.model_dump(exclude_none=True) for metric in metrics.metrics]
        }

    def load(self, timestamp: datetime|None=None) -> tuple[dict[str, ServiceMetrics], dict[str, ServiceHealth]]:
        glob_pattern = os.path.join(self._folder, f"*.json")
        glob_matches = [f.replace("\\", "/") for f in sorted(glob(glob_pattern, recursive=False), reverse=True)]
        if timestamp:
            timestamp = timestamp.astimezone()  # ensure timezone is set
        last = None
        for match in glob_matches:
            _id = match[match.rindex("/")+1:] if "/" in match else match
            _id = _id[:-5]
            try:
                t = datetime.strptime(_id, FileMetricsPersistence._dt_format).astimezone()
            except:
                continue
            if last is not None and (timestamp is None or t < timestamp):
                break
            last = match
        if last is None:
            return {}, {}
        with open(last, "r") as fl:
            as_dict: dict[str, Any] = json.load(fl)
        return TypeAdapter(dict[str, ServiceMetrics]).validate_python(as_dict["metrics"]),  TypeAdapter(dict[str, ServiceHealth]).validate_python(as_dict["health"])

