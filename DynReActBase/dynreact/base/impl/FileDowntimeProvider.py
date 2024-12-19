from datetime import datetime
from typing import Iterator, Literal

from pydantic import TypeAdapter

from dynreact.base.DowntimeProvider import DowntimeProvider
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.FileConfigProvider import FileConfigProvider

from dynreact.base.model import Site, EquipmentDowntime


class FileDowntimeProvider(DowntimeProvider):
    """
    @beta: currently not used
    Read configuration from json files
    """
    def __init__(self, uri: str, site: Site):
        super().__init__(uri, site)
        uri = uri.lower()
        if not uri.startswith("default+file:"):
            raise Exception("Unexpected URI for file config provider: " + str(uri))
        self._file = uri[len("default+file:"):]
        js = None
        with open(self._file, "r", encoding="utf-8") as file:
            js = file.read()
        adapter = TypeAdapter(list[EquipmentDowntime])
        downtimes: list[EquipmentDowntime] = adapter.validate_json(js)
        self._downtimes = downtimes

    def downtimes(self, start: datetime, end: datetime, plant: int|list[int]|None=None, process: str|None=None,
                  order: Literal["asc", "desc"] = "asc") -> Iterator[EquipmentDowntime]:
        downtimes = self._downtimes
        if plant is not None:
            if not isinstance(plant, list):
                plant = [plant]
            downtimes = [d for d in downtimes if d.equipment in plant]
        if process is not None:
            new_downtimes = []
            for d in downtimes:
                plant_id: int = d.equipment
                plant_obj = next((p for p in self._sites.equipment if p.id == plant_id), None)
                if plant_obj is not None and plant_obj.process == process:
                    new_downtimes.append(d)
            downtimes = new_downtimes
        downtimes = [d for d in downtimes if d.start < end and d.end >= start]
        downtimes = sorted(downtimes, key= lambda d: d.start, reverse=order == "desc")
        return iter(downtimes)


# for testing
if __name__ == "__main__":
    site = FileConfigProvider("default+file:./data/sample/site.json").site_config()
    provider = FileDowntimeProvider("default+file:./data/sample/downtimes.json", site)
    start = DatetimeUtils.parse_date("2023-04-25T06:00Z")
    end = DatetimeUtils.parse_date("2023-04-28T00:00Z")
    print("Downtimes", list(provider.downtimes(start, end, plant=[1, 13], order="desc")))
