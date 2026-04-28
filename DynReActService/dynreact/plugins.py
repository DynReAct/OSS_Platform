import importlib
import importlib.util
import sys
import traceback
from typing import Any

from dash import html

from dynreact.auth.authentication import get_permission_manager
from dynreact.base.ConfigurationProvider import ConfigurationProvider
from dynreact.base.CostProvider import CostProvider
from dynreact.base.DowntimeProvider import DowntimeProvider
from dynreact.base.LongTermPlanning import LongTermPlanning
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.LotSink import LotSink
from dynreact.base.LotsOptimizer import LotsOptimizationAlgo
from dynreact.base.PermissionManager import PermissionManager
from dynreact.base.PlantAvailabilityPersistence import PlantAvailabilityPersistence
from dynreact.base.PlantPerformanceModel import PlantPerformanceModel
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.ShiftsProvider import ShiftsProvider
from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.impl.AggregationPersistence import AggregationPersistence
from dynreact.base.impl.DummyShiftsProvider import DummyShiftsProvider
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
from dynreact.module_loader import instantiate_first_matching, resolve_explicit_reference


class Plugins:

    def __init__(self, config: DynReActSrvConfig):
        self._config = config
        self._profile: str|None = config.profile
        self._config_provider: ConfigurationProvider | None = None
        self._snapshot_provider: SnapshotProvider | None = None
        self._downtime_provider: DowntimeProvider | None = None
        self._cost_provider: CostProvider|None = None
        self._lots_optimizer: LotsOptimizationAlgo|None = None
        self._long_term_planning: LongTermPlanning|None = None
        self._shifts_provider: ShiftsProvider|None = None
        self._results_persistence: ResultsPersistence|None = None
        self._availability_persistence: PlantAvailabilityPersistence|None = None
        self._plant_performance_models: list[PlantPerformanceModel]|None = None
        self._lot_sinks: dict[str, LotSink]|None = None
        self._aggregation_persistence: AggregationPersistence|None = None
        self._permissions: PermissionManager|None = None

    @staticmethod
    def _stp_error_page(stp: str, error: Exception|None = None):
        msg = f"Failed to load STP frontend '{stp}'."
        details = str(error) if error is not None else "Unknown error"
        return html.Div([
            html.H2("Short Term Planning Unavailable"),
            html.P(msg),
            html.Pre(details, style={"whiteSpace": "pre-wrap"}),
            html.P("Check that the frontend package is installed and that its Python dependencies are available."),
        ], style={"padding": "1.5rem"})

    def get_snapshot_provider(self) -> SnapshotProvider:
        if self._snapshot_provider is None:
            site = self.get_config_provider().site_config()
            # Direct instance (for testing)
            if isinstance(self._config.snapshot_provider, SnapshotProvider):
                self._snapshot_provider = self._config.snapshot_provider
            elif self._config.snapshot_provider.startswith("default+file:"):
                self._snapshot_provider = FileSnapshotProvider(self._config.snapshot_provider, site)
            else:
                self._snapshot_provider = Plugins._load_module("dynreact.snapshot", self._config.snapshot_provider, self._profile, SnapshotProvider, site, do_raise=True)
        return self._snapshot_provider

    def get_config_provider(self) -> ConfigurationProvider:
        if self._config_provider is None:
            # Direct instance (for testing)
            if isinstance(self._config.config_provider, ConfigurationProvider):
                self._config_provider = self._config.config_provider
            elif self._config.config_provider.startswith("default+file:"):
                self._config_provider = FileConfigProvider(self._config.config_provider)
            else:
                self._config_provider = Plugins._load_module("dynreact.config", self._config.config_provider, self._profile, ConfigurationProvider, do_raise=True)
        return self._config_provider

    def get_downtime_provider(self) -> DowntimeProvider:
        if self._downtime_provider is None:
            site = self.get_config_provider().site_config()
            if self._config.downtime_provider.startswith("default+file:"):
                self._downtime_provider = FileDowntimeProvider(self._config.downtime_provider, site)
            else:
                self._downtime_provider = Plugins._load_module("dynreact.downtimes", self._config.downtime_provider, self._profile, DowntimeProvider, site, do_raise=True)
        return self._downtime_provider

    def get_cost_provider(self) -> CostProvider:
        if self._cost_provider is None:
            if isinstance(self._config.cost_provider, CostProvider):
                self._cost_provider = self._config.cost_provider
            else:
                site = self.get_config_provider().site_config()
                self._cost_provider = Plugins._load_module("dynreact.cost", self._config.cost_provider, self._profile, CostProvider, site, do_raise=True)
        return self._cost_provider

    def get_lots_optimization(self) -> LotsOptimizationAlgo:
        if self._lots_optimizer is None:
            cfg = self._config.lot_creation
            if cfg == "default:tabu-search":
                cfg = f"class:dynreact.lotcreation.LotsOptimizerImpl,{cfg}"
            self._lots_optimizer = Plugins._load_module("dynreact.lotcreation", cfg, self._profile, LotsOptimizationAlgo,
                                                        self.get_config_provider().site_config(), do_raise=True)
        return self._lots_optimizer

    def get_long_term_planning(self) -> LongTermPlanning:
        if self._long_term_planning is None:
            site = self.get_config_provider().site_config()
            if self._config.long_term_provider.startswith("default:"):
                self._long_term_planning = SimpleLongTermPlanning(self._config.long_term_provider, site)
            else:
                self._long_term_planning = Plugins._load_module("dynreact.ltp",  self._config.long_term_provider, self._profile, LongTermPlanning, site, do_raise=True)
        return self._long_term_planning

    def get_results_persistence(self) -> ResultsPersistence:
        if self._results_persistence is None:
            if isinstance(self._config.results_persistence, ResultsPersistence):
                self._results_persistence = self._config.results_persistence
            else:
                site = self.get_config_provider().site_config()
                if self._config.results_persistence.startswith("default+file:"):
                    self._results_persistence = FileResultsPersistence(self._config.results_persistence, site)
                else:
                    self._results_persistence = Plugins._load_module("dynreact.results", self._config.results_persistence, self._profile, ResultsPersistence, site, do_raise=True)
        return self._results_persistence

    def get_availability_persistence(self) -> PlantAvailabilityPersistence:
        if self._availability_persistence is None:
            site = self.get_config_provider().site_config()
            if self._config.availability_persistence.startswith("default+file:"):
                self._availability_persistence = FileAvailabilityPersistence(self._config.availability_persistence, site)
            else:
                self._availability_persistence = Plugins._load_module("dynreact.availability", self._config.availability_persistence, self._profile,
                                                                      PlantAvailabilityPersistence, site, do_raise=True)
        return self._availability_persistence

    def get_aggregation_persistence(self) -> AggregationPersistence:
        if self._aggregation_persistence is None:
            #site = self.get_config_provider().site_config()
            if self._config.aggregation_persistence.startswith("default+file:"):
                self._aggregation_persistence = FileAggregationPersistence(self._config.aggregation_persistence)
            else:
                self._aggregation_persistence = Plugins._load_module("dynreact.aggregation", self._config.aggregation_persistence, self._profile,
                                                                 AggregationPersistence, self._config.aggregation_persistence, do_raise=True)
        return self._aggregation_persistence

    def get_lot_sinks(self, if_exists: bool=False) -> dict[str, LotSink]:
        if self._lot_sinks is None and not if_exists:
            site = self.get_config_provider().site_config()
            sinks = {}
            permissions = self.get_permission_manager()
            for sink_config in self._config.lot_sinks:
                if sink_config.startswith("default+file:"):
                    sink = FileLotSink(sink_config, site, permissions)
                else:
                    sink = Plugins._load_module("dynreact.lotsink", sink_config, self._profile, LotSink, site, permissions)
                if sink is not None:
                    sinks[sink.id()] = sink
            self._lot_sinks = sinks
        return dict(self._lot_sinks)

    def get_shifts_provider(self, if_exists: bool=False) -> ShiftsProvider:
        if self._shifts_provider is None and not if_exists:
            site = self.get_config_provider().site_config()
            if isinstance(self._config.shifts_provider, ShiftsProvider):
                self._shifts_provider = self._config.shifts_provider
            elif (self._config.shifts_provider and self._config.shifts_provider.startswith("dummy:")) or (not self._profile and not self._config.shifts_provider):
                self._shifts_provider = DummyShiftsProvider(self._config.shifts_provider, site)
            else:
                self._shifts_provider = Plugins._load_module("dynreact.shifts", self._config.shifts_provider, self._profile,
                                                             ShiftsProvider, site, do_raise=True)
        return self._shifts_provider

    def get_permission_manager(self) -> PermissionManager:
        if self._permissions is None:
            self._permissions = get_permission_manager(self._config)
        return self._permissions

    def get_plant_performance_models(self) -> list[PlantPerformanceModel]:
        if self._plant_performance_models is None:
            site = self.get_config_provider().site_config()
            self._plant_performance_models = [Plugins._load_plant_performance_model(config, site) for
                                config in self._config.plant_performance_models] if self._config.plant_performance_models is not None else []
        return self._plant_performance_models

    def load_short_term_planning(self):
        uri = self._config.short_term_planning
        profile = (self._config.profile or "").strip().lower()
        from dynreact.shortterm.ShortTermPlanning import ShortTermPlanning
        if uri.startswith("default+file:"):
            return ShortTermPlanning(uri)
        return Plugins._load_module("dynreact.shortterm", uri, profile if profile != "" else None, ShortTermPlanning, do_raise=True)

    def load_stp_page(self):
        stp = self._config.stp_frontend
        if not stp:
            return None
        if stp == "default":
            try:
                import dynreact.gui_stp.agentsPage
                return dynreact.gui_stp.agentsPage.layout
            except Exception as exc:
                print("Failed to load standard Agents page")
                traceback.print_exc()
                return Plugins._stp_error_page(stp, exc)
        try:
            modl = importlib.import_module(stp)
            layout = getattr(modl, "layout", None)
            if layout is not None:
                return layout
        except Exception as exc:
            print(f"An error occurred loading the STP frontend {stp}")
            traceback.print_exc()
            import_error = exc
        else:
            import_error = None

        importers = iter(sys.meta_path)
        for importer in importers:
            try:
                spec_res = importer.find_spec(stp, path=None)
                if spec_res is not None:
                    modl = importlib.util.module_from_spec(spec_res)
                    spec_res.loader.exec_module(modl)
                    layout = getattr(modl, "layout", None)
                    if layout is not None:
                        sys.modules[stp] = modl
                        return layout
            except Exception as exc:
                print(f"An error occurred loading the STP frontend {stp}")
                traceback.print_exc()
                import_error = exc
        return Plugins._stp_error_page(stp, import_error)

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
        return instantiate_first_matching(class_name, PlantPerformanceModel, config, do_raise=True)

    @staticmethod
    def _load_module(
            base_module: str,
            provider_url: str|None,
            profile: str|None,
            clzz,
            *args,
            **kwargs
        ) -> Any|None:   # returns an instance of the clzz, if found
        module: str|None = None
        explicit_class_name: str | None = None
        if provider_url is not None and provider_url.startswith("class:"):
            separator = provider_url.find(",")
            explicit_ref = provider_url[provider_url.index(":") + 1:] if separator < 0 else provider_url[provider_url.index(":") + 1:separator]
            module, explicit_class_name = resolve_explicit_reference(explicit_ref)
            provider_url = None if separator < 0 else provider_url[separator + 1:]
        elif profile is not None:
            module = f"{base_module}.{profile}"
        if module is None:
            raise Exception(f"Module not specified for {clzz}, provider url {provider_url}, profile: {profile}.")
        try:
            return instantiate_first_matching(
                module,
                clzz,
                provider_url,
                *args,
                explicit_class_name=explicit_class_name,
                ignored_exceptions=(NotApplicableException,),
                **kwargs,
            )
        except Exception as exc:
            print(f"Failed to load module {module} of type {clzz}: {exc}")
            raise


# for testing
if __name__ == "__main__":
    p = Plugins(DynReActSrvConfig())
    site = p.get_config_provider().site_config()
    print("Site", site)
    snapshot = p.get_snapshot_provider().load()
    print("Snapshot", snapshot.timestamp, "coils:", len(snapshot.material), ", orders:", len(snapshot.orders), ", lots:", len(snapshot.lots))
    status0 = p.get_cost_provider().status(snapshot, site.equipment[0].id)
    print("Status0", status0)
