import dataclasses
from datetime import datetime, timedelta

import requests

from dynreact.base.PlantPerformanceModel import PlantPerformanceModel, PerformanceEstimation, PlantPerformanceInput, \
    PerformanceModelMetadata, PlantPerformanceResults, PlantPerformanceResultsFailed, PlantPerformanceResultsSuccess
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Site, Order, Material, ServiceHealth


@dataclasses.dataclass
class PerformanceModelClientConfig:

    address: str
    token: str|None=None


# TODO some results caching?
class PerformanceModelClient(PlantPerformanceModel):

    def __init__(self, config: PerformanceModelClientConfig):
        self._config = config
        self._address = PerformanceModelClient._validate_path(self._config.address)
        self._token = config.token
        self._meta: PerformanceModelMetadata|None = None
        self._status_update_interval: timedelta = timedelta(minutes=2)
        self._last_status_update: datetime|None = None
        self._last_status: int = -1

    def _get_meta(self) -> PerformanceModelMetadata:
        if self._meta is None:
            result = requests.get(self._address + "model",
                                  headers=PerformanceModelClient._attach_token({"Accept": "application/json"}, self._token))
            result.raise_for_status()
            json = result.json()
            self._meta = PerformanceModelMetadata.model_validate(json)
        return self._meta

    def id(self) -> str:
        return self._get_meta().id

    def label(self, lang: str="en") -> str:
        return self._get_meta().label

    def description(self, lang: str="en") -> str|None:
        return self._get_meta().description

    def status(self) -> int:
        now = DatetimeUtils.now()
        if self._last_status_update is None or now - self._last_status_update > self._status_update_interval:
            try:
                result = requests.get(self._address + "health",
                                      headers=PerformanceModelClient._attach_token({"Accept": "application/json"}, self._token))
                if not result.ok:
                    self._last_status = result.status_code
                else:
                    health = ServiceHealth.model_validate(result.json())
                    self._last_status = health.status
            except:
                self._last_status = 1
            self._last_status_update = now
        return self._last_status

    def applicable_processes_and_plants(self) -> tuple[list[str]|None, list[int]|None]:
        meta = self._get_meta()
        return list(meta.processes) if meta.processes is not None else None, list(meta.equipment) if meta.equipment is not None else None

    def bulk_performance(self, plant: int, orders: list[Order]) -> PlantPerformanceResults:
        data = PlantPerformanceInput(equipment=plant, orders=orders)
        try:
            response = requests.post(self._address + "performance",
                                   data=data.model_dump_json(exclude_none=True, exclude_unset=True),
                                   headers=PerformanceModelClient._attach_token({"Content-Type": "application/json", "Accept": "application/json"}, self._token)
                                   )
            if not response.ok:
                return PlantPerformanceResultsFailed(status=response.status_code, message=response.reason)
            result = PlantPerformanceResultsSuccess.model_validate(response.json())
            return result
        except:
            return PlantPerformanceResultsFailed(status=1, message="Service not available")

    @staticmethod
    def _validate_path(pth: str) -> str:
        if len(pth) > 0 and not pth.endswith("/"):
            pth = pth + "/"
        return pth

    @staticmethod
    def _attach_token(headers: dict[str, any], token: str|None) -> dict[str, any]:
        if token:
            headers["X-Token"] = token
        return headers

