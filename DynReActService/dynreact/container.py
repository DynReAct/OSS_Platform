"""
Dependency Injection Container for DynReAct
Manages plugin loading based on profile (oss, ras, etc.)
"""
import importlib
import sys
from typing import Any, Optional, Type
from pathlib import Path

from dynreact.app_config import DynReActSrvConfig
from dynreact.base.model import Site


class Container:
    """
    DI Container that loads components dynamically based on profile.
    Supports multiple implementations of the same interface based on profile.
    """
    
    def __init__(self, config: DynReActSrvConfig):
        self.config = config
        self.profile = getattr(config, 'profile', 'oss').lower()
        self._cache = {}
    
    def get_snapshot_provider(self, site: Site):
        """Get SnapshotProvider implementation for current profile"""
        if 'snapshot_provider' not in self._cache:
            module = self._load_profile_module('snapshot')
            # Try to instantiate using the provider_url
            self._cache['snapshot_provider'] = self._create_provider(
                module, self.config.snapshot_provider, site
            )
        return self._cache['snapshot_provider']
    
    def get_config_provider(self):
        """Get ConfigurationProvider implementation for current profile"""
        if 'config_provider' not in self._cache:
            module = self._load_profile_module('config')
            self._cache['config_provider'] = self._create_provider(
                module, self.config.config_provider
            )
        return self._cache['config_provider']
    
    def get_downtime_provider(self, site: Site):
        """Get DowntimeProvider implementation for current profile"""
        if 'downtime_provider' not in self._cache:
            module = self._load_profile_module('downtime')
            self._cache['downtime_provider'] = self._create_provider(
                module, self.config.downtime_provider, site
            )
        return self._cache['downtime_provider']
    
    def get_cost_provider(self, site: Site):
        """Get CostProvider implementation for current profile"""
        if 'cost_provider' not in self._cache:
            if self.config.cost_provider:
                module = self._load_profile_module('cost')
                self._cache['cost_provider'] = self._create_provider(
                    module, self.config.cost_provider, site
                )
        return self._cache.get('cost_provider')
    
    def get_performance_models(self, site: Site):
        """Get PlantPerformanceModel implementations for current profile"""
        if 'performance_models' not in self._cache:
            if self.config.plant_performance_models:
                module = self._load_profile_module('performance')
                models = []
                for model_config in self.config.plant_performance_models:
                    model = self._create_provider(module, model_config, site)
                    if model:
                        models.append(model)
                self._cache['performance_models'] = models
            else:
                self._cache['performance_models'] = []
        return self._cache['performance_models']
    
    def get_energy_kpi_provider(self, site: Site):
        """Get energy KPI provider implementation for current profile"""
        if 'energy_kpi' not in self._cache:
            try:
                module = self._load_profile_module('energy_kpi')
                self._cache['energy_kpi'] = self._create_provider(module, site)
            except (ImportError, AttributeError):
                self._cache['energy_kpi'] = None
        return self._cache.get('energy_kpi')
    
    def _load_profile_module(self, component: str) -> Any:
        """
        Load a profile-specific module.
        
        Order of resolution:
        1. Try {profile}.dynreact.{component}
        2. Fallback to dynreact.{component} (OSS default)
        
        Example: profile="ras", component="snapshot"
        Tries: ShortTermRAS.dynreact.snapshot -> dynreact.snapshot
        """
        # Try profile-specific first
        profile_module_name = f"{self.profile}.dynreact.{component}"
        try:
            return importlib.import_module(profile_module_name)
        except ImportError as e:
            # Fallback to OSS default
            default_module_name = f"dynreact.{component}"
            try:
                return importlib.import_module(default_module_name)
            except ImportError:
                raise ImportError(
                    f"Could not load {component} for profile '{self.profile}'.\n"
                    f"Tried:\n"
                    f"  1. {profile_module_name}\n"
                    f"  2. {default_module_name}\n"
                    f"Original error: {e}"
                )
    
    def _create_provider(self, module: Any, *args, **kwargs) -> Any:
        """
        Create a provider instance from a module.
        Looks for:
        1. A class with "Impl" suffix (e.g., SnapshotProviderImpl)
        2. A factory function named 'create' or 'create_provider'
        3. The first concrete class implementing the expected interface
        """
        # Try to find implementation class
        impl_class = None
        
        # Strategy 1: Look for *Impl class
        for name, obj in vars(module).items():
            if name.endswith('Impl') and isinstance(obj, type):
                impl_class = obj
                break
        
        # Strategy 2: Look for factory functions
        if not impl_class:
            if hasattr(module, 'create'):
                factory = getattr(module, 'create')
                return factory(*args, **kwargs)
            elif hasattr(module, 'create_provider'):
                factory = getattr(module, 'create_provider')
                return factory(*args, **kwargs)
        
        # Strategy 3: Instantiate the found class
        if impl_class:
            try:
                return impl_class(*args, **kwargs)
            except Exception as e:
                raise RuntimeError(
                    f"Failed to instantiate {impl_class.__name__} "
                    f"from {module.__name__} with args {args}: {e}"
                )
        
        raise ImportError(
            f"No implementation found in module {module.__name__}. "
            f"Expected: *Impl class, create(), or create_provider() function"
        )
