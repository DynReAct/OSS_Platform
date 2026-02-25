from datetime import datetime, timedelta, timezone, tzinfo
from threading import Lock
from typing import Any

from dynreact.SnapshotUpdate import SnapshotUpdate
from dynreact.base.AggregationProvider import AggregationProvider
from dynreact.base.ConfigurationProvider import ConfigurationProvider
from dynreact.base.CostProvider import CostProvider
from dynreact.base.DowntimeProvider import DowntimeProvider
from dynreact.base.LongTermPlanning import LongTermPlanning
from dynreact.base.LotSink import LotSink
from dynreact.base.LotsOptimizer import LotsOptimizationAlgo
from dynreact.base.PermissionManager import PermissionManager
from dynreact.base.PlantAvailabilityPersistence import PlantAvailabilityPersistence
from dynreact.base.PlantPerformanceModel import PlantPerformanceModel
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.ShiftsProvider import ShiftsProvider
from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.impl.AggregationPersistence import AggregationPersistence
from dynreact.base.impl.AggregationProviderImpl import AggregationProviderImpl
from dynreact.base.model import Snapshot, Site, ProductionPlanning, ProductionTargets, Material, Lot
from dynreact.lots_optimization import LotCreator

from dynreact.app_config import DynReActSrvConfig
from dynreact.plugins import Plugins


class DynReActSrvState:

    def __init__(self, config: DynReActSrvConfig, plugins: Plugins):
        if config.time_zone:
            from zoneinfo import ZoneInfo
            self._time_zone = ZoneInfo(config.time_zone)
        else:
            self._time_zone = datetime.now(timezone.utc).astimezone().tzinfo
        self._config = config
        self._plugins = plugins
        self._config_provider: ConfigurationProvider|None = None
        self._site: Site|None = None
        self._snapshot_provider: SnapshotProvider | None = None
        self._downtime_provider: DowntimeProvider | None = None
        self._cost_provider: CostProvider | None = None
        self._lots_optimizer: LotsOptimizationAlgo | None = None
        self._ltp: LongTermPlanning | None = None
        self._results_persistence: ResultsPersistence | None = None
        self._availability_persistence: PlantAvailabilityPersistence|None = None
        self._shifts_provider: ShiftsProvider|None = None
        self._max_snapshot_caches: int = config.max_snapshot_caches
        self._max_snapshot_solutions_cache: int = config.max_snapshot_solutions_caches
        self._snapshots_cache: dict[datetime, Snapshot] = {}
        self._snapshot_updates: SnapshotUpdate|None = None
        # snapshot, process, planning, targets
        self._snapshot_solutions_cache:  list[tuple[datetime, str, ProductionPlanning, ProductionTargets]] = []
        self._duedates_solutions_cache: list[tuple[datetime, str, ProductionPlanning, ProductionTargets]] = []
        self._coils_by_orders_cache: dict[datetime, dict[str, list[Material]]] = {}
        self._stp_page = None
        self._aggregation: AggregationProvider|None = None
        self._aggregation_persistence: AggregationPersistence|None = None
        self._optimization_state = LotCreator()
        self._lots_batch_job = None
        self._snapshot_locks: dict[datetime, Lock] = {}

    def start(self):
        if self._config.lots_batch_config:
            from dynreact.batch import LotsBatchOptimizationJob
            self._lots_batch_job = LotsBatchOptimizationJob(self._config, self)

    def get_time_zone(self) -> tzinfo:
        return self._time_zone

    def get_lot_creator(self) -> LotCreator:
        return self._optimization_state

    def get_snapshot_provider(self) -> SnapshotProvider:
        if self._snapshot_provider is None:
            self._snapshot_provider = self._plugins.get_snapshot_provider()
            sinks = self.get_lot_sinks()
            if len(sinks) > 0:
                self._snapshot_updates = SnapshotUpdate(self.get_site())
        return self._snapshot_provider

    def get_aggregation_provider(self) -> AggregationProvider|None:
        itv = self._config.aggregation_exec_interval_minutes
        start_offset = self._config.aggregation_exec_offset_minutes
        if itv <= 0:
            return None
        if self._aggregation is None:
            self._aggregation = AggregationProviderImpl(self.get_site(), self.get_snapshot_provider(), self._plugins.get_aggregation_persistence(),
                                                interval=timedelta(minutes=itv), interval_start=timedelta(minutes=start_offset))
        return self._aggregation

    def get_config_provider(self) -> ConfigurationProvider:
        if self._config_provider is None:
            self._config_provider = self._plugins.get_config_provider()
        return self._config_provider

    def get_downtime_provider(self) -> DowntimeProvider:
        if self._downtime_provider is None:
            self._downtime_provider = self._plugins.get_downtime_provider()
        return self._downtime_provider

    def get_cost_provider(self) -> CostProvider:
        if self._cost_provider is None:
            self._cost_provider = self._plugins.get_cost_provider()
        return self._cost_provider

    def get_lots_optimization(self) -> LotsOptimizationAlgo:
        if self._lots_optimizer is None:
            self._lots_optimizer = self._plugins.get_lots_optimization()
        return self._lots_optimizer

    def get_long_term_planning(self) -> LongTermPlanning:
        if self._ltp is None:
            self._ltp = self._plugins.get_long_term_planning()
        return self._ltp

    def get_shifts_provider(self) -> ShiftsProvider:
        if self._shifts_provider is None:
            self._shifts_provider = self._plugins.get_shifts_provider()
        return self._shifts_provider

    def get_results_persistence(self) -> ResultsPersistence:
        if self._results_persistence is None:
            self._results_persistence = self._plugins.get_results_persistence()
        return self._results_persistence

    def get_availability_persistence(self) -> PlantAvailabilityPersistence:
        if self._availability_persistence is None:
            self._availability_persistence = self._plugins.get_availability_persistence()
        return self._availability_persistence

    def get_site(self) -> Site:
        if self._site is None:
            self._site = self.get_config_provider().site_config()
        return self._site

    def get_snapshot(self, time: datetime|None = None, recurse: bool = True) -> Snapshot|None:
        if time is None:
            time = self.get_snapshot_provider().current_snapshot_id()
        updates = self._snapshot_updates
        if updates is not None and time in updates:
            return updates[time]
        if time in self._snapshots_cache:
            return self._snapshots_cache[time]
        if time is not None and recurse:
            matches = list(self.get_snapshot_provider().snapshots(time - timedelta(minutes=10), time + timedelta(minutes=10)))
            matches_sorted = sorted(matches, key=lambda m: abs((m-time).total_seconds()))
            if len(matches_sorted) > 0:
                return self.get_snapshot(time=matches_sorted[0], recurse=False)
        lock = self._get_snapshot_lock(time)
        # this locking method does not entirely rule out that the same snapshot be loaded multiple times, but makes it improbable
        with lock:
            if time in self._snapshots_cache:
                return self._snapshots_cache[time]
            snapshot = self.get_snapshot_provider().load(time=time)
            if snapshot is None:
                return snapshot
            new_time = snapshot.timestamp
            if new_time not in self._snapshots_cache:  # or time not in self._snapshots_cache:
                while len(self._snapshots_cache) >= self._max_snapshot_caches:
                    first_ts = sorted(list(self._snapshots_cache.keys()))[0]
                    self._snapshots_cache.pop(first_ts)
                self._snapshots_cache[new_time] = snapshot
        if updates is not None and new_time in updates:
            return updates[new_time]
        return snapshot

    def _get_snapshot_lock(self, time: datetime):
        if time not in self._snapshot_locks:
            if len(self._snapshot_locks) > 10:
                keys_to_remove = list(self._snapshot_locks.keys())[0:4]
                for key in keys_to_remove:
                    self._snapshot_locks.pop(key)
            self._snapshot_locks[time] = Lock()
        return self._snapshot_locks.get(time)

    def transfer_lot(self, snapshot: Snapshot, sink: LotSink, lot: Lot, name: str, user: str|None, update_snapshot: bool=True) -> str:
        new_lot_id = sink.transfer_new(lot, snapshot, external_id=name, user=user)
        updates = self._snapshot_updates
        if updates is not None and update_snapshot:
            lot = lot.copy(update={"id": new_lot_id})
            new_snap = updates.update_snapshot(snapshot, lot)
        return new_lot_id

    def get_snapshot_solution(self, process: str, snapshot: datetime|None=None,
                              horizon:  timedelta|None=None) -> tuple[ProductionPlanning, ProductionTargets]|None:
        snapshot_obj = self.get_snapshot(snapshot)
        snapshot = snapshot_obj.timestamp
        cached = next((r for r in self._snapshot_solutions_cache if r[0] == snapshot and r[1] == process), None)
        if cached is not None:
            return cached[2], cached[3]
        if horizon is None:
            horizon = timedelta(days=1)
        result: tuple[ProductionPlanning, ProductionTargets] = self.get_lots_optimization().snapshot_solution(process, snapshot_obj, horizon, self.get_cost_provider())
        if result is not None:
            if len(self._snapshot_solutions_cache) >= self._max_snapshot_solutions_cache:
                self._snapshot_solutions_cache.pop(0)
            self._snapshot_solutions_cache.append((snapshot, process, result[0], result[1]))
        return result

    def get_due_date_solution(self, process: str, snapshot: datetime|None=None,
                              horizon: timedelta|None=None) -> tuple[ProductionPlanning, ProductionTargets]|None:
        snapshot_obj = self.get_snapshot(snapshot)
        snapshot = snapshot_obj.timestamp
        cached = next((r for r in self._duedates_solutions_cache if r[0] == snapshot and r[1] == process), None)
        if cached is not None:
            return  cached[2], cached[3]
        if horizon is None:
            horizon = timedelta(days=1)
        result: tuple[ProductionPlanning, ProductionTargets] = self.get_lots_optimization().due_dates_solution(process, snapshot_obj, horizon, self.get_cost_provider())
        if result is not None:
            if len(self._duedates_solutions_cache) >= self._max_snapshot_solutions_cache:
                self._duedates_solutions_cache.pop(0)
            self._duedates_solutions_cache.append((snapshot, process, result[0], result[1]))
        return result

    def get_coils_by_order(self, snapshot: datetime|None) -> dict[str, list[Material]]:
        snapshot_obj = self.get_snapshot(snapshot)
        snapshot = snapshot_obj.timestamp
        if snapshot in self._coils_by_orders_cache:
            return dict(self._coils_by_orders_cache[snapshot])
        coils_by_order: dict[str, list[Material]] = {}
        for coil in snapshot_obj.material:
            order: str = coil.order
            if order not in coils_by_order:
                coils_by_order[order] = []
            coils_by_order[order].append(coil)
        for arr in coils_by_order.values():
            arr.sort(key=lambda coil: (coil.current_process if coil.current_process is not None else 10_000, coil.order_position if coil.order_position is not None else 10_000))
        if len(self._coils_by_orders_cache) > self._max_snapshot_caches:
            first_ts = sorted(list(self._coils_by_orders_cache()))[0]
            self._coils_by_orders_cache.pop(first_ts)
        self._coils_by_orders_cache[snapshot] = coils_by_order
        return dict(coils_by_order)

    def get_permission_manager(self) -> PermissionManager:
        return self._plugins.get_permission_manager()

    def get_plant_performance_models(self) -> list[PlantPerformanceModel]:
        return self._plugins.get_plant_performance_models()

    def get_lot_sinks(self, if_exists: bool=False) -> dict[str, LotSink]:
        return self._plugins.get_lot_sinks()

    def get_stp_page(self):
        if self._stp_page is None:
            self._stp_page = self._plugins.load_stp_page()
        return self._stp_page

