from datetime import datetime
from typing import Iterator, Literal

from dynreact.base.model import EquipmentDowntime, Site


class DowntimeProvider:
    """
    @beta: currently not used
    """

    def __init__(self, uri: str, site: Site):
        self._site = site

    def downtimes(self, start: datetime, end: datetime, plant: int|list[int]|None=None, process: str|None=None,
                  order: Literal["asc", "desc"] = "asc") -> Iterator[EquipmentDowntime]:
        raise Exception("not implemented")
