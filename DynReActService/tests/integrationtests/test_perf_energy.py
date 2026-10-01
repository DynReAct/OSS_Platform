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
from dynreact.base.impl.EnergyBackends import _derived_planned_speed_va


class _DummyMaterialProperties:
    width_va_in_planned = 950.0
    thickness_nww_out_planned = 0.22
    va_width = 940.0
    va_thickness = 0.21


class _DummyOrder:
    material_properties = _DummyMaterialProperties()


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

    def test_planned_va_speed_is_derived_from_performance_and_geometry(self):
        speed = _derived_planned_speed_va(_DummyOrder(), 20.0)
        self.assertIsNotNone(speed)
        self.assertAlmostEqual(speed, 20_000.0 / (7856.0 * 0.95 * 0.00022 * 60.0), places=6)

    def test_planned_va_speed_falls_back_to_actual_geometry(self):
        class _FallbackProps:
            width_va_in_planned = None
            thickness_nww_out_planned = None
            va_width = 930.0
            va_thickness = 0.2

        class _FallbackOrder:
            material_properties = _FallbackProps()

        speed = _derived_planned_speed_va(_FallbackOrder(), 18.0)
        self.assertIsNotNone(speed)
        self.assertAlmostEqual(speed, 18_000.0 / (7856.0 * 0.93 * 0.0002 * 60.0), places=6)


if __name__ == "__main__":
    unittest.main()
