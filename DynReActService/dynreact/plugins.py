import importlib
import sys, os
import traceback
from typing import Any  # , Iterator   Updated by JOM 20250521
import pkgutil
from collections.abc import Iterator as ABCIterator  # For type hinting, if needed elsewhere

from dynreact.base.ConfigurationProvider import ConfigurationProvider
from dynreact.base.CostProvider import CostProvider
from dynreact.base.DowntimeProvider import DowntimeProvider
from dynreact.base.LongTermPlanning import LongTermPlanning
from dynreact.base.NotApplicableException import NotApplicableException
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
        self._cost_provider: CostProvider | None = None
        self._lots_optimizer: LotsOptimizationAlgo | None = None
        self._long_term_planning: LongTermPlanning | None = None
        self._short_term_planning: ShortTermPlanning | None = None
        self._results_persistence: ResultsPersistence | None = None
        self._availability_persistence: PlantAvailabilityPersistence | None = None
        self._plant_performance_models: list[PlantPerformanceModel] | None = None
        self._lot_sinks: dict[str, LotSink] | None = None

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
                self._config_provider = Plugins._load_module("dynreact.config.ConfigurationProviderImpl",
                                                             ConfigurationProvider, self._config.config_provider)
                if self._config_provider is None:
                    raise Exception("Config provider not found " + self._config.config_provider)
        return self._config_provider

    def get_downtime_provider(self) -> DowntimeProvider:
        if self._downtime_provider is None:
            site = self.get_config_provider().site_config()
            if self._config.downtime_provider.startswith("default+file:"):
                self._downtime_provider = FileDowntimeProvider(self._config.downtime_provider, site)
            else:
                self._downtime_provider = Plugins._load_module("dynreact.downtimes.DowntimeProviderImpl",
                                                               DowntimeProvider, self._config.downtime_provider)
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
                self._long_term_planning = Plugins._load_module("dynreact.longtermplanning.LongTermPlanningImpl",
                                                                LongTermPlanning,
                                                                self._config.long_term_provider, site)
            if self._long_term_planning is None:
                raise Exception("Long term planning not found: " + str(self._config.long_term_provider))
        return self._long_term_planning

    def get_stp_config_params(self) -> ShortTermPlanning:
        if self._short_term_planning is None:
            if self._config.short_term_planning.startswith("default+file:"):
                self._short_term_planning = ShortTermPlanning(self._config.short_term_planning)
            else:
                self._short_term_planning = Plugins._load_module("dynreact.shortterm", ShortTermPlanning,
                                                                 self._config.short_term_planning)
        return self._short_term_planning

    def get_results_persistence(self) -> ResultsPersistence:
        if self._results_persistence is None:
            site = self.get_config_provider().site_config()
            if self._config.results_persistence.startswith("default+file:"):
                self._results_persistence = FileResultsPersistence(self._config.results_persistence, site)
            else:
                self._results_persistence = Plugins._load_module("dynreact.results.ResultsPersistenceImpl",
                                                                 ResultsPersistence, self._config.results_persistence,
                                                                 site)
                if self._results_persistence is None:
                    raise Exception("Results persistence not found " + self._config.results_persistence)
        return self._results_persistence

    def get_availability_persistence(self) -> PlantAvailabilityPersistence:
        if self._availability_persistence is None:
            site = self.get_config_provider().site_config()
            if self._config.availability_persistence.startswith("default+file:"):
                self._availability_persistence = FileAvailabilityPersistence(self._config.availability_persistence,
                                                                             site)
            else:
                self._availability_persistence = Plugins._load_module(
                    "dynreact.availability.AvailabilityPersistenceImpl",
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
                                              config in
                                              self._config.plant_performance_models] if self._config.plant_performance_models is not None else []
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
        # Updated by JOM 20250521
        # importers = iter(sys.meta_path)
        importers = iter(sys.path)
        for importer in importers:
            try:
                # Updated by JOM 20250518
                # spec_res = importer.find_spec(stp, path=None)
                spec_res = importlib.util.find_spec(stp)
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
    def _load_plant_performance_model(config: str, site: Site) -> PlantPerformanceModel | None:
        if "::" not in config:
            return None
        idx = config.index("::")
        class_name = config[0:idx]
        last_idx = config.rindex("::")
        has_token = last_idx > idx
        uri = config[idx + 2:] if not has_token else config[idx + 2:last_idx]
        token = config[last_idx + 2:] if has_token else None
        config = PerformanceModelClientConfig(address=uri, token=token)
        return Plugins._load_module(class_name, PlantPerformanceModel, config, do_raise=True)

    @staticmethod
    def _load_snapshot_provider(provider_url: str, site: Site) -> SnapshotProvider | None:
        return Plugins._load_module("dynreact.snapshot.SnapshotProviderImpl", SnapshotProvider, provider_url, site)

    @staticmethod
    def _load_cost_provider(cost_provider: str | None, site: Site) -> CostProvider | None:
        return Plugins._load_module("dynreact.cost.CostCalculatorImpl", CostProvider, cost_provider, site)

    @staticmethod
    def _load_module(module_spec_arg: str, clzz: type, *args_to_pass: Any, **kwargs_to_pass: Any) -> Any | None:
        """
        Loads a module and returns an instance of the first class found
        that is a subclass of 'clzz'.

        This method robustly handles namespace packages by manually discovering all
        contributing paths and searching within each.

        Args:
            module_spec_arg: The fully qualified name of the module (e.g., "dynreact.shortterm")
                             or "class:<module.path.ClassName>,<uri>" syntax.
            clzz: The base class type to search for.
            *args_to_pass: Positional arguments for the class constructor.
                           If "class:" syntax is used, URI is prepended.
            **kwargs_to_pass: Keyword arguments for the class constructor.
                              "do_raise" (bool, default False) controls exception raising.

        Returns:
            An instance of the found class, or None.
        """
        module_name_to_load: str = module_spec_arg
        final_constructor_args: tuple = args_to_pass
        final_constructor_kwargs: dict = dict(kwargs_to_pass)  # Mutable copy

        if isinstance(module_spec_arg, str) and module_spec_arg.startswith("class:"):
            spec_uri_content = module_spec_arg[len("class:"):]
            parts = spec_uri_content.split(',', 1)
            module_name_to_load = parts[0].strip()
            uri_arg = parts[1].strip() if len(parts) > 1 else ""
            final_constructor_args = (uri_arg,) + args_to_pass

        do_raise: bool = final_constructor_kwargs.pop("do_raise", False)
        errors: list[Exception] = []

        # --- Path Discovery for Namespace Packages ---
        explicit_search_paths = []
        module_name_parts = module_name_to_load.split('.')

        for path_entry in sys.path:
            potential_module_dir = os.path.join(path_entry, *module_name_parts)
            if os.path.isdir(potential_module_dir):
                # This directory matches the structure (e.g., .../dynreact/shortterm)
                # For pkgutil-style or PEP 420 namespaces, this directory contributes.
                normalized_path = os.path.normpath(potential_module_dir)
                if normalized_path not in explicit_search_paths:
                    explicit_search_paths.append(normalized_path)

        # Fallback: if manual scan is empty, try importing and using its __path__
        # This is a fallback because the user reported this __path__ might be incomplete.
        if not explicit_search_paths:
            try:
                imported_module_for_path = importlib.import_module(module_name_to_load)
                if hasattr(imported_module_for_path, '__path__'):
                    for p_item in imported_module_for_path.__path__:
                        norm_p_item = os.path.normpath(p_item)
                        if norm_p_item not in explicit_search_paths:
                            explicit_search_paths.append(norm_p_item)
            except ImportError:
                pass  # Error will be handled below if list remains empty

        if not explicit_search_paths and not imported_module_for_path:
            errors.append(ImportError(f"Could not discover any filesystem paths for module {module_name_to_load}."))
            if do_raise:
                raise ModuleNotFoundError(
                    f"Module {module_name_to_load} paths not found. Searched sys.path. Errors: {errors}")
            return None

        # --- Module Scanning ---
        # modules_to_scan_objects will hold actual loaded module objects
        modules_to_scan_objects = []
        # processed_module_names tracks full module names to avoid redundant processing
        processed_module_names = set()

        # 1. Attempt to import the main namespace package itself.
        # This allows scanning for classes defined directly in any of its __init__.py files.
        try:
            # This import should ideally create a module object with a complete __path__
            # due to the pkgutil.extend_path in your __init__.py files.
            main_namespace_module = importlib.import_module(module_name_to_load)
            if main_namespace_module not in modules_to_scan_objects:
                modules_to_scan_objects.append(main_namespace_module)
            processed_module_names.add(main_namespace_module.__name__)
        except ImportError as e_ns_import:
            errors.append(e_ns_import)
            # Continue, as submodules might still be discoverable via path walking if main import fails for some reason

        # 2. Walk through each discovered path that contributes to the namespace.
        # explicit_search_paths contains directories like ".../projectA/dynreact/shortterm", ".../projectB/dynreact/shortterm"
        for ns_path_item in explicit_search_paths:
            # ns_path_item is a directory, e.g., "/opt/.../OSS_Platform/ShortTermPlanning/dynreact/shortterm"
            # We want to find modules *within* this directory, such as "ras_short_term_planning_impl.py".
            # The prefix ensures their names are like "dynreact.shortterm.ras_short_term_planning_impl".
            for _, submodule_name_full, _ in pkgutil.walk_packages(
                    path=[ns_path_item],  # Search this specific directory portion of the namespace
                    prefix=module_name_to_load + '.',  # e.g., "dynreact.shortterm."
                    onerror=lambda name_err: errors.append(
                        ImportError(f"Error during walk_packages on {ns_path_item} for {name_err}"))):

                if submodule_name_full in processed_module_names:
                    continue
                try:
                    submodule = importlib.import_module(submodule_name_full)
                    if submodule not in modules_to_scan_objects:  # Check by object identity
                        modules_to_scan_objects.append(submodule)
                    processed_module_names.add(submodule_name_full)
                except ImportError as e_sub:
                    errors.append(ImportError(
                        f"Could not import submodule {submodule_name_full} from path {ns_path_item}: {e_sub}"))
                    if do_raise: raise
                except Exception as e_gen_sub:  # Catch other potential errors during import
                    errors.append(e_gen_sub)
                    if do_raise: raise

        # Deduplicate module objects if any identical ones were added (e.g., main_namespace_module and a walked version)
        final_modules_to_inspect = []
        seen_module_ids = set()
        for m_obj in modules_to_scan_objects:
            if id(m_obj) not in seen_module_ids:
                final_modules_to_inspect.append(m_obj)
                seen_module_ids.add(id(m_obj))

        if not final_modules_to_inspect:
            errors.append(ImportError(
                f"No modules found to inspect for {module_name_to_load} across discovered paths: {explicit_search_paths}"))
            if do_raise:
                # If initial errors exist, raise the first one, otherwise a generic not found.
                if errors: raise errors[0]
                raise ModuleNotFoundError(f"No inspectable modules found for {module_name_to_load}")
            return None

        # 3. Inspect members of all collected modules
        for module_to_inspect in final_modules_to_inspect:
            for member_name, member_obj in inspect.getmembers(module_to_inspect):
                if inspect.isclass(member_obj) and issubclass(member_obj, clzz) and member_obj is not clzz:
                    # Ensure class is from the module being inspected or the target namespace
                    if member_obj.__module__ == module_to_inspect.__name__ or \
                            member_obj.__module__.startswith(module_name_to_load):  # Covers submodules too
                        try:
                            instance = member_obj(*final_constructor_args, **final_constructor_kwargs)
                            return instance
                        # If using NotApplicableException, uncomment its specific except block here
                        # except NotApplicableException:
                        #     if do_raise: raise
                        except Exception as e_inst:
                            errors.append(e_inst)
                            if do_raise: raise

        if do_raise:
            if errors: raise errors[0]
            raise ModuleNotFoundError(
                f"Class extending {clzz.__name__} not found in {module_name_to_load} or its submodules after scanning {len(final_modules_to_inspect)} modules.")

        return None

    # @staticmethod
    # def _load_module(module: str, clzz, *args, **kwargs) -> Any|None:   # returns an instance of the clzz, if found
    #     # if *args starts with class: replace module by that arg
    #     if len(args) > 0 and isinstance(args[0], str) and args[0].startswith("class:"):
    #         first = args[0]
    #         module = first[first.index(":")+1:first.index(",")]
    #         first = first[first.index(",")+1:]
    #         args = tuple(a if idx > 0 else first for idx, a in enumerate(args))
    #     mod0 = sys.modules.get(module)
    #     do_raise = kwargs.pop("do_raise", False)
    #     errors = []
    #     mod_set: bool = mod0 is not None
    #     mod_iterator: Iterator = iter([mod0]) if mod_set else _ModIterator(module)
    #     for mod in mod_iterator:
    #         for name, element in inspect.getmembers(mod):
    #             try:
    #                 if inspect.isclass(element) and issubclass(element, clzz) and element != clzz:
    #                     result = element(*args, **kwargs)
    #                     if not mod_set:
    #                         sys.modules[module] = mod
    #                     return result
    #             except Exception as e:
    #                 if not isinstance(e, NotApplicableException):
    #                     errors.append(e)
    #                     if do_raise:
    #                         raise
    #     if len(errors) > 0:
    #         print(f"Failed to load module {module} of type {clzz}: {errors[0]}")
    #         raise errors[0]
    #     if do_raise:
    #         raise Exception(f"Module {module} not found")
    #     return None


# class _ModIterator(Iterator):   # returns loaded modules

#     def __init__(self, module: str):
#         # Note: this works if there are duplicates in editable installations,
#         # but not if there are duplicate modules in separate wheels
#         self._importers = iter(sys.meta_path)
#         self._module = module

#     def __next__(self):
#         while True:
#             importer = next(self._importers)
#             try:
#                 # Updated by JOM 20250515
#                 # spec_res = importer.find_spec(self._module, path=None)
#                 spec_res = importlib.util.find_spec(self._module)
#                 if spec_res is not None:
#                     mod = importlib.util.module_from_spec(spec_res)
#                     # sys.modules[module] = mod  # we'll check first if this is the correct module
#                     spec_res.loader.exec_module(mod)
#                     return mod
#             except:
#                 pass
#
# Updated by JOM 20250519

# ModIterator not needed anymore, as we use importlib and pkgutil
# class _ModIterator(Iterator):
#     def __init__(self, module_name: str):
#         self._module_name = module_name
#         self._sub_modules = []
#         self._visited_modules = set()
#         try:
#             # Base module import first
#             module = importlib.import_module(module_name)
#             self._sub_modules.append(module)
#             self._visited_modules.add(module_name)

#             # If it is a package, iterating over its submodules
#             if hasattr(module, '__path__'):
#                 # (pkgutil.walk
#                 for sub_module_info in pkgutil.walk_packages(module.__path__, module_name + '.'):
#                     if sub_module_info.name not in self._visited_modules:
#                         try:
#                             # Importing found modules
#                             sub_module = importlib.import_module(sub_module_info.name)
#                             self._sub_modules.append(sub_module)
#                             self._visited_modules.add(sub_module_info.name)
#                         except ImportError:
#                             print(f"WARNING _ModIterator: Can't import the submodule {sub_module_info.name}")
#                             pass
#         except ImportError:
#             print(f"WARNING _ModIterator: Can't import the main module {module_name}")
#             pass
#         self._iter = iter(self._sub_modules)

#     def __next__(self):
#         return next(self._iter)

#     def __iter__(self):
#         return self

# for testing
if __name__ == "__main__":
    p = Plugins(DynReActSrvConfig())
    site = p.get_config_provider().site_config()
    print("Site", site)
    snapshot = p.get_snapshot_provider().load()
    print("Snapshot", snapshot.timestamp, "coils:", len(snapshot.material), ", orders:", len(snapshot.orders),
          ", lots:", len(snapshot.lots))
    status0 = p.get_cost_provider().status(snapshot, site.equipment[0].id)
    print("Status0", status0)
