from datetime import datetime
from typing import Literal, Iterator

from dynreact.base.model import AggregatedProduction, AggregatedStorageContent


class AggregationInternal(AggregatedProduction):

    last_snapshot: datetime
    "Stores information about the last processed snapshot, thus enabling the aggregation provider to continue processing incomplete aggregations"


class AggregationPersistence:

    def store_production(self, level: str, value: AggregationInternal):
        raise Exception("not implemented")

    def store_storage(self, snapshot: datetime, value: AggregatedStorageContent):
        raise Exception("not implemented")

    def production_values(self, level: str, start: datetime, end: datetime, order: Literal["asc", "desc"]="asc") -> Iterator[datetime]:
        raise Exception("not implemented")

    def storage_values(self, start: datetime, end: datetime, order: Literal["asc", "desc"]="asc") -> Iterator[datetime]:
        raise Exception("not implemented")

    def load_production_aggregation(self, level: str, time: datetime) -> AggregationInternal|None:
        raise Exception("not implemented")

    def load_storage_aggregation(self, snapshot: datetime) -> AggregatedStorageContent|None:
        raise Exception("not implemented")
