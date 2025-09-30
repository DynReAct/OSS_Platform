from datetime import datetime, timedelta, date

from dynreact.base.model import Site, Model, AggregatedProduction, AggregatedStorageContent


class AggregationLevel(Model, frozen=True):

    id: str
    interval: timedelta
    """
    a representative interval, even though actual aggregation intervals may
    slightly differ from this one. For instance, this may return 30 days for a monthly
    aggregation, although the exact number of days per month may vary.
    """


default_aggregation_levels = [
    AggregationLevel(id="MONTHLY", interval=timedelta(days=30)),
    AggregationLevel(id="WEEKLY", interval=timedelta(days=7)),
    AggregationLevel(id="DAILY", interval=timedelta(days=1)),
]


class AggregationProvider:

    def __init__(self, site: Site):
        self._site = site

    """  # TODO required?
    def aggregations(self, level: AggregationLevel, start: datetime, end: datetime|None = None) -> list:
        return []  # TODO
    """

    def supported_aggregation_levels(self) -> list[AggregationLevel]:
        """
        :return: the aggregation levels supported by the provider
        """
        return list(default_aggregation_levels)

    def aggregated_production(self, t: datetime | date, level: AggregationLevel | timedelta) -> AggregatedProduction | None:
        raise Exception("not implemented")

    def aggregated_storage_content(self, snapshot: datetime) -> AggregatedStorageContent|None:
        raise Exception("not implemented")

