"""Dash user interface helpers and callbacks for OSS_Platform/ShortTermPlanning/dynreact/gui_stp/agents_state.

The module is documented in English to make the short-term planning
workflow easier to maintain across OSS and RAS-specific integrations.
"""

import importlib.abc
import importlib.util
import inspect
import os
import sys
from typing import Any, Iterator, cast

from dynreact.auction.auction import Auction
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.shortterm.common import KeySearch
from dynreact.shortterm.ShortTermPlanning import ShortTermPlanning


class AgentsConfig:
    """Configuration holder for the STP UI runtime.

    Attributes:
        short_term_planning: URI pointing to the STP configuration source.
    """
    short_term_planning: str = "default+file:./data/stp_context.json"

    def __init__(self, short_term_planning: str|None = None) -> None:
        if short_term_planning is None:
            short_term_planning = os.getenv("SHORT_TERM_PLANNING_PARAMS", AgentsConfig.short_term_planning)
        self.short_term_planning = short_term_planning


class AgentsState:
    """Mutable UI state shared by the STP pages and callbacks."""
    def __init__(self, config: AgentsConfig|None = None) -> None:
        self._auction_obj: Auction | None = None
        self._stp: ShortTermPlanning | None = None
        self._config = config if config is not None else AgentsConfig()

    def get_auction_obj(self) -> Any:
        """Get auction obj.
        
        This function is part of the short-term planning workflow and keeps
        the existing runtime behavior while documenting the public contract.
        
        Returns:
            The value produced by the underlying planning, UI, or test helper logic.
        """
        if self._auction_obj is not None:
            return(self._auction_obj)
        return None

    def set_auction_obj(self, auction: Any) -> None:
        """Set auction obj.
        
        This function is part of the short-term planning workflow and keeps
        the existing runtime behavior while documenting the public contract.
        
        Args:
            auction: Input value for the `auction` parameter.
        
        Returns:
            The value produced by the underlying planning, UI, or test helper logic.
        """
        if self._auction_obj is None:
            self._auction_obj = auction

    def set_stp_config(self) -> None:
        """Set stp config.
        
        This function is part of the short-term planning workflow and keeps
        the existing runtime behavior while documenting the public contract.
        
        Returns:
            The value produced by the underlying planning, UI, or test helper logic.
        """
        if self._stp is None:
            self.get_stp_config_params()

    #def get_stp_context_params(self):
    #    self.set_stp_config()
    #    return (self._stp._stpConfigParams.KAFKA_IP, self._stp._stpConfigParams.TOPIC_GEN,
    #            self._stp._stpConfigParams.VB)

    def get_stp_context_params(self) -> Any:
        """Get stp context params.
        
        This function is part of the short-term planning workflow and keeps
        the existing runtime behavior while documenting the public contract.
        
        Returns:
            The value produced by the underlying planning, UI, or test helper logic.
        """
        self.set_stp_config()
        return (KeySearch.search_for_value("KAFKA_IP"), KeySearch.search_for_value("TOPIC_GEN"),
                KeySearch.search_for_value("TOPIC_CALLBACK"), KeySearch.search_for_value("VB"))

    def get_stp_context_timing(self) -> Any:
        """Get stp context timing.
        
        This function is part of the short-term planning workflow and keeps
        the existing runtime behavior while documenting the public contract.
        
        Returns:
            The value produced by the underlying planning, UI, or test helper logic.
        """
        self.set_stp_config()
        stp = self.get_stp_config_params()
        return (
            stp._stpConfigParams.TimeDelays.AUCTION_WAIT,
            stp._stpConfigParams.TimeDelays.COUNTERBID_WAIT,
            stp._stpConfigParams.TimeDelays.CLONING_WAIT,
            stp._stpConfigParams.TimeDelays.EXIT_WAIT,
            stp._stpConfigParams.TimeDelays.SMALL_WAIT,
        )

    def get_stp_config_params(self) -> ShortTermPlanning:
        """Get stp config params.
        
        This function is part of the short-term planning workflow and keeps
        the existing runtime behavior while documenting the public contract.
        
        Returns:
            The value produced by the underlying planning, UI, or test helper logic.
        """
        if self._stp is None:
            if self._config.short_term_planning.startswith("default+file:"):
                self._stp = ShortTermPlanning(self._config.short_term_planning)
            else:
                loaded = AgentsState._load_module("dynreact.shorttermplanning", ShortTermPlanning, self._config.short_term_planning)
                if loaded is None:
                    raise RuntimeError(f"Unable to load STP module from {self._config.short_term_planning}.")
                self._stp = cast(ShortTermPlanning, loaded)
        return self._stp

    # copied from DynReActService/dynreact/plugins.py
    @staticmethod
    def _load_module(module: str, clzz: Any, *args: Any, **kwargs: Any) -> Any | None:  # returns an instance of the clzz, if found
        # if *args starts with class: replace module by that arg
        if len(args) > 0 and isinstance(args[0], str) and args[0].startswith("class:"):
            first = args[0]
            module = first[first.index(":") + 1:first.index(",")]
            first = first[first.index(",") + 1:]
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


class _ModIterator(Iterator):  # returns loaded modules
    """Iterator over importers able to provide a module specification."""
    def __init__(self, module: str) -> None:
        # Note: this works if there are duplicates in editable installations,
        # but not if there are duplicate modules in separate wheels
        self._importers = iter(sys.meta_path + [importlib.util])
        # self._importers = iter([importlib.util]) # TODO maybe we do not need this sys.meta_path voodoo at all?
        self._module = module

    def __next__(self) -> Any:
        while True:
            importer = next(self._importers)
            try:
                if importer is importlib.util:
                    spec_res = importlib.util.find_spec(self._module)
                elif isinstance(importer, importlib.abc.MetaPathFinder):
                    spec_res = importer.find_spec(self._module, None)
                else:
                    continue
                if spec_res is not None:
                    mod = importlib.util.module_from_spec(spec_res)
                    # sys.modules[module] = mod  # we'll check first if this is the correct module
                    if spec_res.loader is None:
                        continue
                    spec_res.loader.exec_module(mod)
                    return mod
            except Exception:
                pass
