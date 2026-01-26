from datetime import datetime
from typing import Sequence

from dynreact.base.model import PlannedWorkingShift, Site


class ShiftsProvider:
    """
    A service that provides access to planned working shifts
    """

    def __init__(self, url: str, site: Site):
        self._url = url
        self._site = site

    def id(self):
        return self._url

    def load_all(self, start: datetime, end: datetime|None=None, limit: int|None=100, equipments: Sequence[int]|None=None) -> dict[int, Sequence[PlannedWorkingShift]]:
        """
        Parameters:
            start:
            end:
            limit:
            equipments: equipment ids to be included

        Returns:
            A dictionary plant id -> shifts
        """
        raise Exception("not implemented")

    def load(self, equipment: int, start: datetime, end: datetime|None=None, limit: int|None=100) -> Sequence[PlannedWorkingShift]:
        return self.load_all(start, end=end, limit=limit, equipments=(equipment, )).get(equipment)
