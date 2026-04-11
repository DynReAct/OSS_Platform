import sys
import types
import unittest
from contextlib import contextmanager

from dynreact.app_config import DynReActSrvConfig
from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.model import Site
from dynreact.base.ShiftsProvider import ShiftsProvider
from dynreact.base.impl.FileSnapshotProvider import FileSnapshotProvider
from dynreact.plugins import Plugins
from dynreact.state import DynReActSrvState


@contextmanager
def patched_modules(*modules: tuple[str, types.ModuleType]):
    originals: dict[str, types.ModuleType | None] = {}
    try:
        for name, module in modules:
            originals[name] = sys.modules.get(name)
            sys.modules[name] = module
        yield
    finally:
        for name, original in originals.items():
            if original is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = original


class _ExplicitSnapshotProvider(SnapshotProvider):

    def __init__(self, provider_url: str, site: Site):
        self.provider_url = provider_url
        self.site = site


class _ProfileSnapshotProvider(SnapshotProvider):

    def __init__(self, provider_url: str, site: Site):
        self.provider_url = provider_url
        self.site = site


class _PackageSnapshotProvider(SnapshotProvider):

    def __init__(self, provider_url: str, site: Site):
        self.provider_url = provider_url
        self.site = site


class _ProfileShiftsProvider(ShiftsProvider):

    def __init__(self, provider_url: str | None, site: Site):
        self.provider_url = provider_url
        self.site = site


def build_short_term_modules():
    package_module = types.ModuleType("dynreact.shortterm")
    base_module = types.ModuleType("dynreact.shortterm.ShortTermPlanning")

    class FakeShortTermPlanningBase:

        def __init__(self, uri: str):
            self.uri = uri

        def stp_config_params(self):
            return {"uri": self.uri}

    base_module.ShortTermPlanning = FakeShortTermPlanningBase
    return package_module, base_module, FakeShortTermPlanningBase


class ProfileLoaderTest(unittest.TestCase):

    def test_explicit_class_reference_supports_module_class_path(self):
        module = types.ModuleType("dynreact.test_explicit")
        module.MySpProvider = _ExplicitSnapshotProvider
        with patched_modules(("dynreact.test_explicit", module)):
            provider = Plugins._load_module(
                "dynreact.snapshot",
                "class:dynreact.test_explicit.MySpProvider,customs+file:./snapshot.csv",
                None,
                SnapshotProvider,
                Site(processes=[], equipment=[], storages=[], material_categories=[]),
                do_raise=True,
            )
        self.assertIsInstance(provider, _ExplicitSnapshotProvider)
        self.assertEqual(provider.provider_url, "customs+file:./snapshot.csv")

    def test_profile_module_loads_first_matching_subclass(self):
        module = types.ModuleType("dynreact.snapshot.ras")
        module.RasSnapshotProvider = _ProfileSnapshotProvider
        with patched_modules(("dynreact.snapshot.ras", module)):
            provider = Plugins._load_module(
                "dynreact.snapshot",
                "ras+file:./snapshots",
                "ras",
                SnapshotProvider,
                Site(processes=[], equipment=[], storages=[], material_categories=[]),
                do_raise=True,
            )
        self.assertIsInstance(provider, _ProfileSnapshotProvider)
        self.assertEqual(provider.provider_url, "ras+file:./snapshots")

    def test_explicit_class_reference_takes_precedence_over_profile(self):
        explicit_module = types.ModuleType("dynreact.test_explicit")
        explicit_module.MySpProvider = _ExplicitSnapshotProvider
        profile_module = types.ModuleType("dynreact.snapshot.ras")
        profile_module.RasSnapshotProvider = _ProfileSnapshotProvider
        with patched_modules(
            ("dynreact.test_explicit", explicit_module),
            ("dynreact.snapshot.ras", profile_module),
        ):
            provider = Plugins._load_module(
                "dynreact.snapshot",
                "class:dynreact.test_explicit.MySpProvider,customs+file:./snapshot.csv",
                "ras",
                SnapshotProvider,
                Site(processes=[], equipment=[], storages=[], material_categories=[]),
                do_raise=True,
            )
        self.assertIsInstance(provider, _ExplicitSnapshotProvider)
        self.assertEqual(provider.provider_url, "customs+file:./snapshot.csv")

    def test_default_snapshot_provider_takes_precedence_over_profile(self):
        profile_module = types.ModuleType("dynreact.snapshot.ras")
        profile_module.RasSnapshotProvider = _ProfileSnapshotProvider
        cfg = DynReActSrvConfig(
            config_provider="default+file:./site.json",
            snapshot_provider="default+file:./snapshots",
            profile="ras",
        )
        with patched_modules(("dynreact.snapshot.ras", profile_module)):
            plugins = Plugins(cfg)
            plugins.get_config_provider = lambda: types.SimpleNamespace(site_config=lambda: Site(processes=[], equipment=[], storages=[], material_categories=[]))
            provider = plugins.get_snapshot_provider()
        self.assertIsInstance(provider, FileSnapshotProvider)

    def test_missing_profile_module_raises_instead_of_falling_back(self):
        cfg = DynReActSrvConfig(
            config_provider="test",
            profile="missing_profile",
            shifts_provider=None,
        )
        plugins = Plugins(cfg)
        plugins.get_config_provider = lambda: types.SimpleNamespace(site_config=lambda: Site(processes=[], equipment=[], storages=[], material_categories=[]))
        with self.assertRaises(Exception):
            plugins.get_shifts_provider()

    def test_profile_shifts_provider_is_used_without_explicit_config(self):
        module = types.ModuleType("dynreact.shifts.ras")
        module.RasShiftsProvider = _ProfileShiftsProvider
        cfg = DynReActSrvConfig(
            config_provider="test",
            profile="ras",
            shifts_provider=None,
        )
        plugins = Plugins(cfg)
        plugins.get_config_provider = lambda: types.SimpleNamespace(site_config=lambda: Site(processes=[], equipment=[], storages=[], material_categories=[]))
        with patched_modules(("dynreact.shifts.ras", module)):
            provider = plugins.get_shifts_provider()
        self.assertIsInstance(provider, _ProfileShiftsProvider)
        self.assertIsNone(provider.provider_url)

    def test_state_short_term_profile_no_longer_depends_on_container(self):
        shortterm_package, shortterm_base_module, ShortTermPlanning = build_short_term_modules()
        common_module = types.ModuleType("dynreact.shortterm.common")

        class _KeySearch:

            @staticmethod
            def set_global(*args, **kwargs):
                return None

        common_module.KeySearch = _KeySearch

        cfg = DynReActSrvConfig(short_term_planning="ras+file:./stp.json", profile="ras")
        with patched_modules(
            ("dynreact.shortterm", shortterm_package),
            ("dynreact.shortterm.ShortTermPlanning", shortterm_base_module),
            ("dynreact.shortterm.common", common_module),
        ):
            class FakeShortTermPlanning(ShortTermPlanning):

                def __init__(self, uri: str):
                    self.uri = uri

                def stp_config_params(self):
                    return {"uri": self.uri}

            profile_module = types.ModuleType("dynreact.shortterm.ras")
            profile_module.RasShortTermPlanning = FakeShortTermPlanning
            with patched_modules(("dynreact.shortterm.ras", profile_module)):
                state = DynReActSrvState(cfg, Plugins(cfg))
                params = state.get_stp_config_params()
        self.assertEqual(params["uri"], "ras+file:./stp.json")

    def test_state_short_term_default_takes_precedence_over_profile(self):
        shortterm_package, shortterm_base_module, ShortTermPlanning = build_short_term_modules()
        common_module = types.ModuleType("dynreact.shortterm.common")

        class _KeySearch:

            @staticmethod
            def set_global(*args, **kwargs):
                return None

        common_module.KeySearch = _KeySearch

        cfg = DynReActSrvConfig(short_term_planning="default+file:./stp.json", profile="ras")
        with patched_modules(
            ("dynreact.shortterm", shortterm_package),
            ("dynreact.shortterm.ShortTermPlanning", shortterm_base_module),
            ("dynreact.shortterm.common", common_module),
        ):
            class FakeShortTermPlanning(ShortTermPlanning):

                def __init__(self, uri: str):
                    self.uri = uri

                def stp_config_params(self):
                    return {"uri": f"profile:{self.uri}"}

            profile_module = types.ModuleType("dynreact.shortterm.ras")
            profile_module.RasShortTermPlanning = FakeShortTermPlanning
            with patched_modules(("dynreact.shortterm.ras", profile_module)):
                state = DynReActSrvState(cfg, Plugins(cfg))
                params = state.get_stp_config_params()
        self.assertEqual(params["uri"], "default+file:./stp.json")


if __name__ == "__main__":
    unittest.main()
