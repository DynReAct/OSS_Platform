import sys
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

if "dash_ag_grid" not in sys.modules:
    sys.modules["dash_ag_grid"] = types.ModuleType("dash_ag_grid")

from dynreact.gui.perf_energy import _build_http_backend


class PerfEnergyHttpConfigTest(unittest.TestCase):

    def test_http_backend_requires_service_equipment_per_equipment(self):
        with self.assertRaisesRegex(
            ValueError,
            r"Energy HTTP configuration for `PKL01` is missing `service_equipment`\."
        ):
            _build_http_backend(
                {
                    "DYNREACT_ENERGY_PERF": "http://energy-service",
                    "equipment": {
                        "PKL01": {}
                    },
                }
            )

    def test_http_backend_accepts_model_driven_equipment_mapping(self):
        backend = _build_http_backend(
            {
                "DYNREACT_ENERGY_PERF": "http://energy-service",
                "equipment": {
                    "PKL01": {
                        "service_equipment": "TD1",
                    }
                },
            }
        )

        self.assertEqual(backend._supported["PKL01"]["service_equipment"], "TD1")


if __name__ == "__main__":
    unittest.main()
