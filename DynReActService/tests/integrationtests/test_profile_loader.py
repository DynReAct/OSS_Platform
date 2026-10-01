import sys
import types
import unittest
from contextlib import contextmanager
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import dash

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dynreact.app_config import DynReActSrvConfig
from dynreact.plugins import Plugins


@contextmanager
def patched_modules(*pairs: tuple[str, types.ModuleType]):
    original = {name: sys.modules.get(name) for name, _ in pairs}
    try:
        for name, module in pairs:
            sys.modules[name] = module
        yield
    finally:
        for name, module in original.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


class ProfileLoaderTest(unittest.TestCase):

    def test_load_short_term_planning_uses_default_uri(self):
        fake_mod = types.ModuleType("dynreact.shortterm.ShortTermPlanning")

        class FakePlanning:
            def __init__(self, uri):
                self.uri = uri

        fake_mod.ShortTermPlanning = FakePlanning
        plugins = Plugins(DynReActSrvConfig(short_term_planning="default+file:./stp.json"))
        with patched_modules(("dynreact.shortterm.ShortTermPlanning", fake_mod)):
            provider = plugins.load_short_term_planning()
        self.assertIsInstance(provider, FakePlanning)
        self.assertEqual(provider.uri, "default+file:./stp.json")

    def test_load_stp_page_returns_error_layout_for_missing_frontend(self):
        plugins = Plugins(DynReActSrvConfig(stp_frontend="missing.frontend.module"))
        layout = plugins.load_stp_page()
        self.assertIsNotNone(layout)

    def test_stp_page_preloads_custom_frontend(self):
        calls = {"count": 0}
        fake_state = types.SimpleNamespace(get_stp_page=lambda: calls.__setitem__("count", calls["count"] + 1))
        fake_config = types.SimpleNamespace(stp_frontend="dynreact.stp_gui_ras.agentPageRas")
        module_path = Path(__file__).resolve().parents[2] / "dynreact" / "gui" / "pages" / "stp_page.py"
        spec = spec_from_file_location("test_stp_page_custom", module_path)
        self.assertIsNotNone(spec)
        module = module_from_spec(spec)
        fake_app = types.ModuleType("dynreact.app")
        fake_app.state = fake_state
        fake_app.config = fake_config
        original_register_page = dash.register_page
        dash.register_page = lambda *args, **kwargs: None
        try:
            with patched_modules(("dynreact.app", fake_app)):
                spec.loader.exec_module(module)
        finally:
            dash.register_page = original_register_page
        self.assertEqual(calls["count"], 1)


if __name__ == "__main__":
    unittest.main()
