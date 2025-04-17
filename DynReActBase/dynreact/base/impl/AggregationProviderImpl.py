import threading
import traceback
from datetime import datetime, date, timedelta, timezone

from dynreact.base.AggregationProvider import AggregationProvider, AggregationLevel, default_aggregation_levels
from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.impl.AggregationPersistence import AggregationPersistence
from dynreact.base.impl.MaterialAggregation import MaterialAggregation
from dynreact.base.model import AggregatedProduction, AggregatedStorageContent, Snapshot


class AggregationProviderImpl(AggregationProvider):

    def __init__(self, site,
                 snapshot_provider: SnapshotProvider,
                 persistence_provider: AggregationPersistence,
                 aggregation_levels: list[AggregationLevel] = default_aggregation_levels,
                 interval: timedelta = timedelta(minutes=5),
                 interval_start: timedelta = timedelta(minutes=1)):
        super().__init__(site)
        self._aggregation_levels = list(aggregation_levels)
        self._snapshot_provider = snapshot_provider
        self._persistence = persistence_provider
        self._interval = interval
        self._interval_start = interval_start
        self._aggregations: dict[str, list[AggregatedProduction]] = {}
        "Unfinished production aggregations. Keys: aggregation level ids"
        self._last_processed_snapshot_prod: datetime|None = None   # TODO init from persistence
        self._last_processed_snapshot_storage: datetime | None = None  # TODO init from persistence
        self._stopped: threading.Event = threading.Event()

    def start(self):
        """
        Must be called once to start the aggregation
        :return:
        """
        self._stopped.clear()
        threading.Thread(target=self._run).start()

    def stop(self):
        self._stopped.set()

    def _run(self):
        self._stopped.wait(self._interval_start.total_seconds())
        while not self._stopped.is_set():
            try:
                self._run_internal()
            except:
                print("AggregationProvider run failed:")
                traceback.print_exc()
            self._stopped.wait(self._interval.total_seconds())

    def _run_internal(self):
        has_none = self._last_processed_snapshot_storage is None or self._last_processed_snapshot_prod is None
        start_time: datetime = datetime.fromtimestamp(0, tz=timezone.utc) if has_none else min(self._last_processed_snapshot_prod, self._last_processed_snapshot_storage)
        for snap in self._snapshot_provider.snapshots(start_time, datetime.now(tz=timezone.utc)):
            update_prod: bool = self._last_processed_snapshot_prod is None or self._last_processed_snapshot_prod < snap
            update_stg: bool = self._last_processed_snapshot_storage is None or self._last_processed_snapshot_storage < snap
            if not update_prod and not update_stg:
                continue
            if self._stopped.is_set():
                return
            snapshot: Snapshot = self._snapshot_provider.load(time=snap)
            if update_prod:
                try:
                    self._update_prod_aggregations(snapshot)
                except:
                    print(f"Failed to update production aggregation for snapshot {snap}")
                    traceback.print_exc()
                finally:
                    self._last_processed_snapshot_prod = snap
            if self._stopped.is_set():
                return
            if update_stg:
                try:
                    self._update_storage_aggregations(snapshot)
                except:
                    print(f"Failed to update storage aggregation for snapshot {snap}")
                    traceback.print_exc()
                finally:
                    self._last_processed_snapshot_storage = snap
            if self._stopped.is_set():
                return

    def supported_aggregation_levels(self) -> list[AggregationLevel]:
        return list(self._aggregation_levels)

    def aggregated_production(self, t: datetime | date, level: AggregationLevel | timedelta) -> AggregatedProduction | None:
        raise Exception("not implemented")

    def aggregated_storage_content(self, snapshot: datetime) -> AggregatedStorageContent|None:
        return self._persistence.load_storage_aggregation(snapshot)

    def _update_prod_aggregations(self, snapshot: Snapshot):
        pass  # TODO

    # calculate aggregation and update persistence
    def _update_storage_aggregations(self, snapshot: Snapshot):
        agg = MaterialAggregation(self._site, self._snapshot_provider)
        agg_by_plants = agg.aggregate_categories_by_plant(snapshot)
        agg_by_storage = agg.aggregate_by_storage(agg_by_plants)
        agg_by_process = agg.aggregate_by_process(agg_by_plants)
        result = AggregatedStorageContent(content_by_storage=agg_by_storage, content_by_process=agg_by_process, content_by_equipment=agg_by_plants)
        self._persistence.store_storage(snapshot.timestamp, result)



