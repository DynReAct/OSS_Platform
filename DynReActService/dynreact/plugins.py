import importlib
import sys
import traceback
from typing import Any

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
from dynreact.base.impl.FileAvailabilityPersistence import FileAvailabilityPersistence
from dynreact.base.impl.FileConfigProvider import FileConfigProvider
from dynreact.base.impl.FileDowntimeProvider import FileDowntimeProvider
from dynreact.base.impl.FileLotSink import FileLotSink
from dynreact.base.impl.FileResultsPersistence import FileResultsPersistence
from dynreact.base.impl.FileSnapshotProvider import FileSnapshotProvider
from dynreact.base.impl.SimpleLongTermPlanning import SimpleLongTermPlanning
from dynreact.base.model import Site

from dynreact.app_config import DynReActSrvConfig
import inspect


class Plugins:

    def __init__(self, config: DynReActSrvConfig):
        self._config = config
        self._config_provider: ConfigurationProvider | None = None
        self._snapshot_provider: SnapshotProvider | None = None
        self._downtime_provider: DowntimeProvider | None = None
        self._cost_provider: CostProvider|None = None
        self._lots_optimizer: LotsOptimizationAlgo|None = None
        self._long_term_planning: LongTermPlanning|None = None
        self._short_term_planning: ShortTermPlanning| None = None
        self._results_persistence: ResultsPersistence|None = None
        self._availability_persistence: PlantAvailabilityPersistence|None = None
        self._plant_performance_models: list[PlantPerformanceModel]|None = None
        self._lot_sinks: dict[str, LotSink]|None = None

    def get_snapshot_provider(self) -> SnapshotProvider:
        if self._snapshot_provider is None:
            site = self.get_config_provider().site_config()
            if self._config.snapshot_provider.startswith("default+file:"):
                self._snapshot_provider = FileSnapshotProvider(self._config.snapshot_provider, site)
            else:
                self._snapshot_provider = Plugins._load_snapshot_provider(self._config.snapshot_provider, site)
                if self._snapshot_provider is None:
                    raise Exception("Snapshot provider not found " + self._config.snapshot_provider)
        return self._snapshot_provider

    def get_config_provider(self) -> ConfigurationProvider:
        if self._config_provider is None:
            if self._config.config_provider.startswith("default+file:"):
                self._config_provider = FileConfigProvider(self._config.config_provider)
            else:
                self._config_provider = Plugins._load_module("dynreact.config.ConfigurationProviderImpl", ConfigurationProvider, self._config.config_provider)
                if self._config_provider is None:
                    raise Exception("Config provider not found " + self._config.config_provider)
        return self._config_provider

    def get_downtime_provider(self) -> DowntimeProvider:
        if self._downtime_provider is None:
            site = self.get_config_provider().site_config()
            if self._config.downtime_provider.startswith("default+file:"):
                self._downtime_provider = FileDowntimeProvider(self._config.downtime_provider, site)
            else:
                self._downtime_provider = Plugins._load_module("dynreact.downtimes.DowntimeProviderImpl", DowntimeProvider, self._config.downtime_provider)
                if self._downtime_provider is None:
                    raise Exception("Downtime provider not found " + self._config.downtime_provider)
        return self._downtime_provider

    def get_cost_provider(self) -> CostProvider:
        if self._cost_provider is None:
            site = self.get_config_provider().site_config()
            self._cost_provider = Plugins._load_cost_provider(self._config.cost_provider, site)
            if self._cost_provider is None:
                raise Exception("Cost provider not found " + str(self._config.cost_provider))
        return self._cost_provider

    def get_lots_optimization(self) -> LotsOptimizationAlgo:
        if self._lots_optimizer is None:
            self._lots_optimizer = Plugins._load_module("dynreact.lotcreation.LotsOptimizerImpl", LotsOptimizationAlgo,
                                                        self.get_config_provider().site_config())
        return self._lots_optimizer

    def get_long_term_planning(self) -> LongTermPlanning:
        if self._long_term_planning is None:
            site = self.get_config_provider().site_config()
            if self._config.long_term_provider.startswith("default:"):
                self._long_term_planning = SimpleLongTermPlanning(self._config.long_term_provider, site)
            else:
                self._long_term_planning = Plugins._load_module("dynreact.longtermplanning.LongTermPlanningImpl", LongTermPlanning,
                                                        self._config.long_term_provider, site)
        return self._long_term_planning

    def get_stp_config_params(self) -> ShortTermPlanning:
        if self._short_term_planning is None:
            if self._config.short_term_planning.startswith("default+file:"):
                self._short_term_planning = ShortTermPlanning(self._config.short_term_planning)
            else:
                self._short_term_planning = Plugins._load_module("dynreact.shorttermplanning", ShortTermPlanning,
                                                                self._config.short_term_planning)
        return self._short_term_planning

    def get_results_persistence(self) -> ResultsPersistence:
        if self._results_persistence is None:
            site = self.get_config_provider().site_config()
            if self._config.results_persistence.startswith("default+file:"):
                self._results_persistence = FileResultsPersistence(self._config.results_persistence, site)
            else:
                self._results_persistence = Plugins._load_module("dynreact.results.ResultsPersistenceImpl",
                        ResultsPersistence, self._config.results_persistence, site)
                if self._results_persistence is None:
                    raise Exception("Results persistence not found " + self._config.results_persistence)
        return self._results_persistence

    def get_availability_persistence(self) -> PlantAvailabilityPersistence:
        if self._availability_persistence is None:
            site = self.get_config_provider().site_config()
            if self._config.availability_persistence.startswith("default+file:"):
                self._availability_persistence = FileAvailabilityPersistence(self._config.availability_persistence, site)
            else:
                self._availability_persistence = Plugins._load_module("dynreact.availability.AvailabilityPersistenceImpl",
                        PlantAvailabilityPersistence, self._config.availability_persistence, site)
                if self._availability_persistence is None:
                    raise Exception("Plant availability persistence not found " + self._config.availability_persistence)
        return self._availability_persistence

    def get_lot_sinks(self) -> dict[str, LotSink]:
        if self._lot_sinks is None:
            site = self.get_config_provider().site_config()
            sinks = {}
            for sink_config in self._config.lot_sinks:
                if sink_config.startswith("default+file:"):
                    sink = FileLotSink(sink_config, site)
                else:
                    sink = Plugins._load_module("dynreact.lots.LotSinkImpl", LotSink, sink_config, site)
                if sink is not None:
                    sinks[sink.id()] = sink
            self._lot_sinks = sinks
        return self._lot_sinks

    def get_plant_performance_models(self) -> list[PlantPerformanceModel]:
        if self._plant_performance_models is None:
            site = self.get_config_provider().site_config()
            self._plant_performance_models = [Plugins._load_plant_performance_model(config, site) for
                                config in self._config.plant_performance_models] if self._config.plant_performance_models is not None else []
        return self._plant_performance_models

    @staticmethod
    def _load_plant_performance_model(config: str, site: Site) -> PlantPerformanceModel|None:
        if ":" not in config:
            return None
        idx = config.index(":")
        class_name = config[0:idx]
        uri = config[idx+1:]
        return Plugins._load_module(class_name, PlantPerformanceModel, uri, site, do_raise=True)

    @staticmethod
    def _load_snapshot_provider(provider_url: str, site: Site) -> SnapshotProvider|None:
        return Plugins._load_module("dynreact.snapshot.SnapshotProviderImpl", SnapshotProvider, provider_url, site)

    @staticmethod
    def _load_cost_provider(cost_provider: str|None, site: Site) -> CostProvider|None:
        return Plugins._load_module("dynreact.cost.CostCalculatorImpl", CostProvider, cost_provider, site)

    @staticmethod
    def _load_module(module: str, clzz, *args, **kwargs) -> Any|None:   # returns an instance of the clzz, if found
        mod = sys.modules.get(module)
        do_raise = kwargs.pop("do_raise", False)
        errors = []
        if mod is None:
            spec_res = importlib.util.find_spec(module, package=None)
            # TODO what if multiple are found?
            mod = importlib.util.module_from_spec(spec_res)
            sys.modules[module] = mod
            spec_res.loader.exec_module(mod)
        for name, element in inspect.getmembers(mod):
            try:
                if inspect.isclass(element) and issubclass(element, clzz) and element != clzz:
                    return element(*args, **kwargs)
            except Exception as e:  # TODO remember errors in case none other is found?
                errors.append(e)
                if do_raise:
                    raise
        if len(errors) > 0:
            print(f"Failed to load module {module} of type {clzz}: {errors[-1]}")
            raise errors[0]  # FIXME
        return None


# for testing
if __name__ == "__main__":
    p = Plugins(DynReActSrvConfig())
    site = p.get_config_provider().site_config()
    print("Site", site)
    snapshot = p.get_snapshot_provider().load()
    print("Snapshot", snapshot.timestamp, "coils:", len(snapshot.material), ", orders:", len(snapshot.orders), ", lots:", len(snapshot.lots))
    status0 = p.get_cost_provider().status(snapshot, site.equipment[0].id)
    print("Status0", status0)

