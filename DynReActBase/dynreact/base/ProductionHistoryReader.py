import datetime
from typing import Sequence

from dynreact.base.model import Site, ProductionTargets


class ProductionHistoryReader:
    """
    A service that provides information about historical production values.
    """

    def __init__(self, uri: str, site: Site):
        self._site = site
        self._uri = uri

    def production_aggregate(self,
                             process: str,
                             start: datetime, end: datetime,
                             equipment: Sequence[int]|None=None,
                             material_filter: Sequence[str]|None=None) -> ProductionTargets:
        """
        Read production aggregates for a specific time interval.

        Parameters:
            process: process id
            start: start time
            end: end time
            equipment: optional equipment filter
            material_filter: optional material type filter; sequence of material class ids

        Returns:
            aggregated production values
        """
        raise Exception("not implemented")

