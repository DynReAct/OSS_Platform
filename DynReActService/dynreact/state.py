from datetime import datetime, timedelta

from dynreact.base.ConfigurationProvider import ConfigurationProvider
from dynreact.base.CostProvider import CostProvider
from dynreact.base.DowntimeProvider import DowntimeProvider
from dynreact.base.LongTermPlanning import LongTermPlanning
from dynreact.base.ShortTermPlanning import ShortTermPlanning
from dynreact.base.LotSink import LotSink
from dynreact.base.LotsOptimizer import LotsOptimizationAlgo
from dynreact.base.PlantAvailabilityPersistence import PlantAvailabilityPersistence
from dynreact.base.PlantPerformanceModel import PlantPerformanceModel
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.model import Snapshot, Site, ProductionPlanning, ProductionTargets, Material

from dynreact.app_config import DynReActSrvConfig
from dynreact.plugins import Plugins
from dynreact.auction import auction


class DynReActSrvState:

    def __init__(self, config: DynReActSrvConfig, plugins: Plugins):
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
#
# Added by JOM 20241005
#
        self._auction_obj : auction.Auction | None = None
        self._stp: ShortTermPlanning | None = None
#
#
        self._max_snapshot_caches: int = config.max_snapshot_caches
        self._max_snapshot_solutions_cache: int = config.max_snapshot_solutions_caches
        self._snapshots_cache: dict[datetime, Snapshot] = {}
        # snapshot, process, planning, targets
        self._snapshot_solutions_cache:  list[tuple[datetime, str, ProductionPlanning, ProductionTargets]] = []
        self._duedates_solutions_cache: list[tuple[datetime, str, ProductionPlanning, ProductionTargets]] = []
        self._coils_by_orders_cache: dict[datetime, dict[str, list[Material]]] = {}

    def get_snapshot_provider(self) -> SnapshotProvider:
        if self._snapshot_provider is None:
            self._snapshot_provider = self._plugins.get_snapshot_provider()
        return self._snapshot_provider

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

    def get_stp_context_params(self):
        if self._stp is None:
            self._stp = self._plugins.get_stp_config_params()
        return (self._stp._stpConfigParams.IP,self._stp._stpConfigParams.TOPIC_GEN,
                self._stp._stpConfigParams.VB)
    
    def get_stp_context_timing(self):
        if self._stp is None:
            self._stp = self._plugins.get_stp_config_params()
        return (self._stp._stpConfigParams.TimeDelays.AW,self._stp._stpConfigParams.TimeDelays.BW,
                self._stp._stpConfigParams.TimeDelays.CW,self._stp._stpConfigParams.TimeDelays.EW,
                self._stp._stpConfigParams.TimeDelays.SMALL_WAIT)

    
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
        if time in self._snapshots_cache:
            return self._snapshots_cache[time]
        snapshot = self.get_snapshot_provider().load(time=time)
        if snapshot is None:
            if time is not None and recurse:
                for time0 in self.get_snapshot_provider().snapshots(time - timedelta(minutes=5), time + timedelta(minutes=5)):
                    return self.get_snapshot(time=time0, recurse=False)
            return snapshot
        new_time = snapshot.timestamp
        if new_time not in self._snapshots_cache or time not in self._snapshots_cache:
            while len(self._snapshots_cache) >= self._max_snapshot_caches:
                first_ts = sorted(list(self._snapshots_cache.keys()))[0]
                self._snapshots_cache.pop(first_ts)
            self._snapshots_cache[new_time] = snapshot
            if time != new_time:
                self._snapshots_cache[time] = snapshot
        return snapshot

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

    def get_plant_performance_models(self) -> list[PlantPerformanceModel]:
        return self._plugins.get_plant_performance_models()

    def get_lot_sinks(self) -> dict[str, LotSink]:
        return self._plugins.get_lot_sinks()
#
# Added by JOM 20241005
#
    def get_auction_obj(self):
        if self._auction_obj is not None:
            return(self._auction_obj)
        return None

    def set_auction_obj(self, auction) -> None:
        if self._auction_obj is None:
            self._auction_obj = auction
