from datetime import datetime
from typing import Literal, Iterator

from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.model import Site, Snapshot


class StaticSnapshotProvider(SnapshotProvider):

    def __init__(self, site: Site, snapshot: Snapshot):
        super().__init__("static", site)
        self._snapshot = snapshot
        self._timestamp = snapshot.timestamp
        if snapshot.timestamp.tzinfo is None:
            raise Exception("Timestamps are expected timezone-sensitive")

    def snapshots(self, start_time: datetime, end_time: datetime, order: Literal["asc", "desc"] = "asc") -> Iterator[datetime]:
        if start_time <= self._timestamp and end_time > self._timestamp:
            return iter([self._timestamp])
        return iter([])

    def load(self, *args, time: datetime|None=None, **kwargs) -> Snapshot|None:
        return self._snapshot
