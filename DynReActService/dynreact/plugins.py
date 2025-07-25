import importlib
import sys
import traceback
from typing import Any, Iterator

from dynreact.base.ConfigurationProvider import ConfigurationProvider
from dynreact.base.CostProvider import CostProvider
from dynreact.base.DowntimeProvider import DowntimeProvider
from dynreact.base.LongTermPlanning import LongTermPlanning
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.LotSink import LotSink
from dynreact.base.LotsOptimizer import LotsOptimizationAlgo
from dynreact.base.PlantAvailabilityPersistence import PlantAvailabilityPersistence
from dynreact.base.PlantPerformanceModel import PlantPerformanceModel
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.impl.AggregationPersistence import AggregationPersistence
from dynreact.base.impl.FileAggregationPersistence import FileAggregationPersistence
from dynreact.base.impl.FileAvailabilityPersistence import FileAvailabilityPersistence
from dynreact.base.impl.FileConfigProvider import FileConfigProvider
from dynreact.base.impl.FileDowntimeProvider import FileDowntimeProvider
from dynreact.base.impl.FileLotSink import FileLotSink
from dynreact.base.impl.FileResultsPersistence import FileResultsPersistence
from dynreact.base.impl.FileSnapshotProvider import FileSnapshotProvider
from dynreact.base.impl.PerformanceModelClient import PerformanceModelClientConfig
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
        self._short_term_planning: Any| None = None
        self._results_persistence: ResultsPersistence|None = None
        self._availability_persistence: PlantAvailabilityPersistence|None = None
        self._plant_performance_models: list[PlantPerformanceModel]|None = None
        self._lot_sinks: dict[str, LotSink]|None = None
        self._aggregation_persistence: AggregationPersistence|None = None

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
            if self._long_term_planning is None:
                raise Exception("Long term planning not found: " + str(self._config.long_term_provider))
        return self._long_term_planning

    def get_stp_config_params(self): # -> ShortTermPlanning:
        if self._short_term_planning is None:
            from dynreact.base.ShortTermPlanning import ShortTermPlanning
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

    def get_aggregation_persistence(self) -> AggregationPersistence:
        if self._aggregation_persistence is None:
            #site = self.get_config_provider().site_config()
            if self._config.aggregation_persistence.startswith("default+file:"):
                self._aggregation_persistence = FileAggregationPersistence(self._config.aggregation_persistence)
            else:
                self._aggregation_persistence = Plugins._load_module("dynreact.aggregation.AggregationPersistenceImpl",
                                                                 AggregationPersistence, self._config.aggregation_persistence)
                if self._aggregation_persistence is None:
                    raise Exception("Aggregation persistence not found " + self._config.aggregation_persistence)
        return self._aggregation_persistence

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

    def load_stp_page(self):
        stp = self._config.stp_frontend
        if not stp:
            return None
        if stp == "default":
            try:
                import dynreact.gui.plugins.agentsPage
                return dynreact.gui.plugins.agentsPage.layout
            except:
                print("Failed to load standard Agents page")
                traceback.print_exc()
                return None
        importers = iter(sys.meta_path)
        for importer in importers:
            try:
                spec_res = importer.find_spec(stp, path=None)
                if spec_res is not None:
                    modl = importlib.util.module_from_spec(spec_res)
                    spec_res.loader.exec_module(modl)
                    for name, element in inspect.getmembers(modl):
                        if name == "layout":
                            sys.modules[stp] = modl
                            return element  # return the layout function
            except:
                print(f"An error occurred loading the STP frontend {stp}")
                traceback.print_exc()
        return None

    @staticmethod
    def _load_plant_performance_model(config: str, site: Site) -> PlantPerformanceModel|None:
        if "::" not in config:
            return None
        idx = config.index("::")
        class_name = config[0:idx]
        last_idx = config.rindex("::")
        has_token = last_idx > idx
        uri = config[idx+2:] if not has_token else config[idx+2:last_idx]
        token = config[last_idx+2:] if has_token else None
        config = PerformanceModelClientConfig(address=uri, token=token)
        return Plugins._load_module(class_name, PlantPerformanceModel, config, do_raise=True)

    @staticmethod
    def _load_snapshot_provider(provider_url: str, site: Site) -> SnapshotProvider|None:
        return Plugins._load_module("dynreact.snapshot.SnapshotProviderImpl", SnapshotProvider, provider_url, site)

    @staticmethod
    def _load_cost_provider(cost_provider: str|None, site: Site) -> CostProvider|None:
        return Plugins._load_module("dynreact.cost.CostCalculatorImpl", CostProvider, cost_provider, site)

    @staticmethod
    def _load_module(module: str, clzz, *args, **kwargs) -> Any|None:   # returns an instance of the clzz, if found
        # if *args starts with class: replace module by that arg
        if len(args) > 0 and isinstance(args[0], str) and args[0].startswith("class:"):
            first = args[0]
            module = first[first.index(":")+1:first.index(",")]
            first = first[first.index(",")+1:]
            args = tuple(a if idx > 0 else first for idx, a in enumerate(args))
        mod0 = sys.modules.get(module)
        do_raise = kwargs.pop("do_raise", False)
        errors = []
        mod_set: bool = mod0 is not None
        mod_iterator: Iterator = iter([mod0]) if mod_set else _ModIterator(module)
        for mod in mod_iterator:
            for name, element in inspect.getmembers(mod):
                try:
                    if inspect.isclass(element) and issubclass(element, clzz) and element != clzz:
                        result = element(*args, **kwargs)
                        if not mod_set:
                            sys.modules[module] = mod
                        return result
                except Exception as e:
                    if not isinstance(e, NotApplicableException):
                        errors.append(e)
                        if do_raise:
                            raise
        if len(errors) > 0:
            print(f"Failed to load module {module} of type {clzz}: {errors[0]}")
            raise errors[0]
        if do_raise:
            raise Exception(f"Module {module} not found")
        return None


class _ModIterator(Iterator):   # returns loaded modules

    def __init__(self, module: str):
        # Note: this works if there are duplicates in editable installations,
        # but not if there are duplicate modules in separate wheels
        self._importers = iter(sys.meta_path + [importlib.util])
        # self._importers = iter([importlib.util]) # TODO maybe we do not need this sys.meta_path voodoo at all?
        self._module = module

    def __next__(self):
        while True:
            importer = next(self._importers)
            try:
                spec_res = importer.find_spec(self._module)
                if spec_res is not None:
                    mod = importlib.util.module_from_spec(spec_res)
                    # sys.modules[module] = mod  # we'll check first if this is the correct module
                    spec_res.loader.exec_module(mod)
                    return mod
            except:
                pass


# for testing
if __name__ == "__main__":
    p = Plugins(DynReActSrvConfig())
    site = p.get_config_provider().site_config()
    print("Site", site)
    snapshot = p.get_snapshot_provider().load()
    print("Snapshot", snapshot.timestamp, "coils:", len(snapshot.material), ", orders:", len(snapshot.orders), ", lots:", len(snapshot.lots))
    status0 = p.get_cost_provider().status(snapshot, site.equipment[0].id)
    print("Status0", status0)

