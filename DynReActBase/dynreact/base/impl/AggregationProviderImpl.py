import threading
import traceback
from datetime import datetime, date, timedelta, timezone
from typing import Iterable

from dynreact.base.AggregationProvider import AggregationProvider, AggregationLevel, default_aggregation_levels
from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.impl.AggregationPersistence import AggregationPersistence, AggregationInternal
from dynreact.base.impl.MaterialAggregation import MaterialAggregation
from dynreact.base.model import AggregatedProduction, AggregatedStorageContent, Snapshot, AggregatedMaterial, Order


# TODO init prod data on start
# TODO timezone handling
# TODO tests
class AggregationProviderImpl(AggregationProvider):

    _ONE_MONTH: timedelta = timedelta(days=30)
    _ONE_WEEK: timedelta = timedelta(days=7)
    _ONE_DAY: timedelta = timedelta(days=1)

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
        self._last_processed_snapshot_prod: dict[str, datetime|None] = {level.id: None for level in aggregation_levels}   # will be initialized from persistence
        self._last_processed_snapshot_storage: datetime | None = None   # will be initialized from persistence
        self._stopped: threading.Event = threading.Event()
        self._stg_cache_lock = threading.Lock()
        self._stg_data_cache: dict[datetime, AggregatedStorageContent] = {}
        self._prod_cache_lock = threading.Lock()
        self._prod_data_cache: dict[str, dict[datetime, AggregationInternal]] = {level.id: {} for level in aggregation_levels}  # guarded by lock
        self._prod_snapshots_by_level: dict[str, Snapshot|None] = {level.id: None for level in aggregation_levels}

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
        try:
            if self._last_processed_snapshot_storage is None or None in self._last_processed_snapshot_prod.values():
                self._init_from_persistence()
        except:
            print("AggregationProvider initialization failed")
            traceback.print_exc()
        start_wait = self._interval_start.total_seconds()
        if start_wait > 0:
            self._stopped.wait(self._interval_start.total_seconds())
        while not self._stopped.is_set():
            try:
                self._run_internal()
            except:
                print("AggregationProvider run failed:")
                traceback.print_exc()
            self._stopped.wait(self._interval.total_seconds())

    def _init_from_persistence(self):
        start = datetime.fromtimestamp(0, tz=timezone.utc)
        now = datetime.now(tz=timezone.utc)
        try:
            last = next(self._persistence.storage_values(start, now, order="desc"))
            if self._last_processed_snapshot_storage is None or last > self._last_processed_snapshot_storage:
                self._last_processed_snapshot_storage = last
        except StopIteration:
            pass
        for level in self._aggregation_levels:
            try:
                last = next(self._persistence.production_values(level.id, start, now, order="desc"))
                agg = self._persistence.load_production_aggregation(level.id, last)
                if agg is not None:
                    last_snap = agg.last_snapshot
                    if self._last_processed_snapshot_prod[level.id] is None or last_snap > self._last_processed_snapshot_prod[level.id]:
                        self._last_processed_snapshot_prod[level.id] = last_snap
            except StopIteration:
                pass

    def _run_internal(self):
        has_none = self._last_processed_snapshot_storage is None or None in self._last_processed_snapshot_prod.values()
        start_time: datetime = datetime.fromtimestamp(0, tz=timezone.utc) if has_none else min(list(self._last_processed_snapshot_prod.values()) + [self._last_processed_snapshot_storage])
        for snap in self._snapshot_provider.snapshots(start_time, datetime.now(tz=timezone.utc)):
            update_prod: bool = None in self._last_processed_snapshot_prod.values() or any(last < snap for last in self._last_processed_snapshot_prod.values())
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
                    for level in self._aggregation_levels:
                        self._last_processed_snapshot_prod[level.id] = snap
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
        level = level if isinstance(level, timedelta) else level.interval
        agg_id = next((l.id for l in self._aggregation_levels if l.interval == level), None)
        if agg_id is None:
            raise Exception(f"Unsupported aggregation level {level}")
        start_time: datetime = AggregationProviderImpl._get_interval_start_end(t, level)[0]
        with self._prod_cache_lock:
            cached = self._prod_data_cache[agg_id].get(start_time)
        if cached is not None:
            return cached
        return self._persistence.load_production_aggregation(agg_id, start_time)  # TODO timestamp ok?

    def aggregated_storage_content(self, snapshot: datetime) -> AggregatedStorageContent|None:
        result = self._persistence.load_storage_aggregation(snapshot)
        if result is not None:
            return result
        # handle case that the calculation has not run yet
        snapshot_obj = self._snapshot_provider.load(time=snapshot)
        if snapshot_obj is None or abs(snapshot_obj.timestamp.timestamp() - snapshot.timestamp()) > 60:
            return None
        with self._stg_cache_lock:
            cached = self._stg_data_cache.get(snapshot_obj.timestamp)
            if cached is not None:
                return cached
            agg: AggregatedStorageContent = self._get_storage_aggregations_internal(snapshot_obj)
            self._stg_data_cache[snapshot_obj.timestamp] = agg
        return agg

    def _update_prod_aggregations(self, snapshot: Snapshot):
        for level in self._aggregation_levels:
            agg = self.aggregated_production(snapshot.timestamp, level)
            is_closing: bool = agg is None or agg.aggregation_interval[1] <= snapshot.timestamp
            if agg is not None and agg.aggregation_interval[0] <= snapshot.timestamp <= agg.aggregation_interval[1]:  # TODO tolerance for end of interval required!
                self._update_aggregation(agg, snapshot, level, is_closing)
            if is_closing:
                self._start_new_prod_aggregation(snapshot, level)
            self._last_processed_snapshot_prod[level.id] = snapshot.timestamp


    def _update_aggregation(self, agg: AggregationInternal, snapshot: Snapshot, level: AggregationLevel, is_closing: bool):
        current_snapshot = self._prod_snapshots_by_level.get(level.id)
        if current_snapshot is None or current_snapshot.timestamp < agg.aggregation_interval[0] or current_snapshot.timestamp > agg.aggregation_interval[1]:
            current_id = self._snapshot_provider.previous(snapshot.timestamp - timedelta(minutes=3))
            current_snapshot = self._snapshot_provider.load(current_id) if current_id is not None else None
            if current_snapshot is None:  # ?
                self._prod_snapshots_by_level[level.id] = snapshot
                return
        updated = self._update_aggregation_internal(agg, current_snapshot, snapshot, level, is_closing)
        self._prod_snapshots_by_level[level.id] = snapshot
        with self._prod_cache_lock:
            self._prod_data_cache[level.id][updated.aggregation_interval[0]] = updated
        try:
            self._persistence.store_production(level.id, updated)
        except:
            print(f"Failed to store production aggregation at level {level.id}")
            traceback.print_exc()

    def _update_aggregation_internal(self, agg: AggregationInternal, previous_snap: Snapshot, snapshot: Snapshot, level: AggregationLevel, is_closing: bool):
        prev_orders: dict[str, Order] = {o.id: o for o in previous_snap.orders}
        curr_orders: dict[str, Order] = {o.id: o for o in snapshot.orders}
        total_sum: float = agg.total_weight
        material_sums: dict[str, float] = dict(agg.material_weights) if agg.material_weights is not None else {}
        for oid, order in prev_orders.items():
            #if oid in curr_orders:  # TODO algo ok?
            #    continue
            new = curr_orders.get(oid)
            weight = order.actual_weight
            new_weight = new.actual_weight if new is not None else 0
            if new_weight >= weight:
                continue
            weight_diff = weight - new_weight
            total_sum += weight_diff
            for clzz in order.material_classes.values():
                if clzz not in material_sums:
                    material_sums[clzz] = 0
                material_sums[clzz] += weight_diff
        new_agg = AggregationInternal(total_weight=total_sum, material_weights=material_sums, last_snapshot=snapshot.timestamp,
                                      aggregation_interval=agg.aggregation_interval, closed=is_closing)
        return new_agg

    def _start_new_prod_aggregation(self, snapshot: Snapshot, level: AggregationLevel):
        start, end = AggregationProviderImpl._get_interval_start_end(snapshot.timestamp, level.interval)
        agg = AggregationInternal(aggregation_interval=(start, end), closed=False, last_snapshot=snapshot.timestamp, total_weight=0)
        self._persistence.store_production(level.id, agg)
        with self._prod_cache_lock:
            self._prod_data_cache[level.id][start] = agg
        self._prod_snapshots_by_level[level.id] = snapshot

    # calculate aggregation and update persistence
    def _update_storage_aggregations(self, snapshot: Snapshot):
        with self._stg_cache_lock:
            cached = self._stg_data_cache.pop(snapshot.timestamp, None)
        result = cached if cached is not None else self._get_storage_aggregations_internal(snapshot)
        self._persistence.store_storage(snapshot.timestamp, result)

    def _get_storage_aggregations_internal(self, snapshot: Snapshot) -> AggregatedStorageContent:
        t = snapshot.timestamp
        agg = MaterialAggregation(self._site, self._snapshot_provider)
        agg_by_plants0 = agg.aggregate_categories_by_plant(snapshot)
        total_weights_by_plants: dict[int, float] = AggregationProviderImpl._total_weight(agg_by_plants0)
        agg_by_storage0 = agg.aggregate_by_storage(agg_by_plants0)
        total_weights_by_storage = AggregationProviderImpl._total_weight(agg_by_storage0)
        agg_by_process0 = agg.aggregate_by_process(agg_by_plants0)
        total_weights_by_process = AggregationProviderImpl._total_weight(agg_by_process0)
        agg_by_plants = {p: AggregatedMaterial(material_weights=AggregationProviderImpl._merge_dicts(values.values()), total_weight=total_weights_by_plants.get(p, 0),
                                               aggregation_interval=(t, t)) for p, values in agg_by_plants0.items()}
        agg_by_storage = {p: AggregatedMaterial(material_weights=AggregationProviderImpl._merge_dicts(values.values()), total_weight=total_weights_by_storage.get(p, 0),
                                               aggregation_interval=(t, t)) for p, values in agg_by_storage0.items()}
        agg_by_process = {p: AggregatedMaterial(material_weights=AggregationProviderImpl._merge_dicts(values.values()), total_weight=total_weights_by_process.get(p, 0),
                                                aggregation_interval=(t, t)) for p, values in agg_by_process0.items()}
        return AggregatedStorageContent(content_by_storage=agg_by_storage, content_by_process=agg_by_process, content_by_equipment=agg_by_plants)

    @staticmethod
    def _total_weight[T: int|str](agg_by_unit: dict[T, dict[str, dict[str, float]]]) -> dict[T, float]:
        total_weights: dict[T, list[float]] = {p: [sum(values[cat].values()) for cat in values.keys()] for p, values in agg_by_unit.items()}
        return {t: max(values) if len(values) > 0 else 0 for t, values in total_weights.items()}

    @staticmethod
    def _merge_dicts(values: Iterable[dict[str, float]]) -> dict[str, float]:
        return {key: val for dct in values for key, val in dct.items()}

    @staticmethod
    def _get_interval_start_end(timestamp: datetime, level: timedelta) -> tuple[datetime, datetime]:  # TODO small tolerance for timestamps close to end of month?
        if level == AggregationProviderImpl._ONE_MONTH:
            start = timestamp.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            end = (start + timedelta(days=31)).replace(day=1)
            return start, end
        if level == AggregationProviderImpl._ONE_WEEK:
            start = (timestamp - timedelta(days=timestamp.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
            end   = start + AggregationProviderImpl._ONE_WEEK
            return start, end
        if level == AggregationProviderImpl._ONE_DAY:
            start = timestamp.replace(hour=0, minute=0, second=0, microsecond=0)
            end = start + AggregationProviderImpl._ONE_DAY
            return start, end
        raise Exception("Aggregation level " + str(level) + " not implemented")

