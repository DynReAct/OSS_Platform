"""Read-only Jenkins readiness checks for a pinned OSS snapshot and scenario inputs.

Never print REST_URL, HTTP response bodies or exception messages: the endpoint
is supplied through a Jenkins credential. No snapshot or agent is modified.
"""
from datetime import datetime
import os
from urllib.parse import quote, urlsplit

import requests


class PreflightFailure(Exception):
    """An actionable diagnostic containing no endpoint or response data."""


def timestamp(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone required")
    return parsed


def main(get=None):
    base = os.environ.get("REST_URL", "").rstrip("/")
    snapshot_id = os.environ.get("SNAPSHOT_VERSION", "")
    try:
        parts = urlsplit(base)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ValueError("Invalid URL")
        requested = timestamp(snapshot_id)
    except (TypeError, ValueError):
        print("CONFIG_ERROR: REST_URL and a timezone-qualified SNAPSHOT_VERSION are required; endpoint withheld.")
        return 1
    get = get or requests.get

    def read(path, label, **kwargs):
        try:
            response = get(base + path, timeout=(4, 30), **kwargs)
        except requests.RequestException:
            raise PreflightFailure(f"{label}: REQUEST_FAILED (endpoint/details withheld)") from None
        if not response.ok:
            raise PreflightFailure(f"{label}: HTTP_{response.status_code} (endpoint/body withheld)")
        try:
            return response.json()
        except ValueError:
            raise PreflightFailure(f"{label}: INVALID_JSON") from None

    try:
        site = read("/site", "SITE")
        equipment = {str(item["id"]): item for item in site["equipment"]}
        # This job's 6/7 are FIN01/FIN02. Detect an accidentally wired RAS URL.
        for key, name in (("6", "FIN01"), ("7", "FIN02")):
            if equipment.get(key, {}).get("name_short") != name:
                raise PreflightFailure(f"PROFILE_MISMATCH: expected OSS equipment {key}={name}")
        snapshot = read("/snapshots/" + quote(snapshot_id, safe=""), "SNAPSHOT")
        if timestamp(snapshot["timestamp"]) != requested:
            raise PreflightFailure("SNAPSHOT_MISMATCH: response is not the pinned timestamp")
        orders = {order["id"]: order for order in snapshot["orders"]}
        for material in snapshot["material"]:
            if material["order"] not in orders:
                raise PreflightFailure("SNAPSHOT_INVALID: material refers to an absent order")
        from dynreact.shortterm.common.data.data_setup import DataSetup
        from dynreact.shortterm.short_term_planning import _select_materials_by_equipment
        data = DataSetup.__new__(DataSetup)
        data.last_snapshot_data = snapshot
        data.all_materials_params = data.get_all_materials_params()
        data.all_equipment_params = data.get_all_equipments_materials()
        scenarios = [
            ("4/5", os.getenv("SCENARIO_4_5_EQUIPMENT", "7").split(), 1),
            ("6", os.getenv("SCENARIO_6_EQUIPMENT", "7").split(), 2),
            ("7", os.getenv("SCENARIO_7_EQUIPMENTS", "6 7").split(), 1),
            ("8", os.getenv("SCENARIO_8_EQUIPMENTS", "6 7").split(), 2),
        ]
        selected_equipment = set()
        for label, equipments, count in scenarios:
            if not equipments or any(eq not in equipment for eq in equipments):
                raise PreflightFailure(f"SCENARIO_{label}: UNKNOWN_OR_EMPTY_EQUIPMENT")
            for eq in equipments:
                data.all_equipment_params.setdefault(int(eq), [])
            selected = _select_materials_by_equipment(data, equipments, count)
            # Multi-equipment auctions deliberately select fewer than count when
            # only shared orders remain; the integration test uses the same rule.
            if any(not selected[eq] for eq in equipments):
                raise PreflightFailure(f"SCENARIO_{label}: NO_ELIGIBLE_MATERIAL")
            if len(equipments) == 1 and len(selected[equipments[0]]) < count:
                raise PreflightFailure(f"SCENARIO_{label}: INSUFFICIENT_DISTINCT_ORDERS")
            if label == "8":
                expected = os.environ.get("SCENARIO_8_ORDER_ID", "")
                chosen = {str(data.get_material_params(mat)["order"]["id"])
                          for materials in selected.values() for mat in materials}
                if not expected or expected not in chosen:
                    raise PreflightFailure("SCENARIO_8: EXPECTED_ORDER_NOT_SELECTED")
            selected_equipment.update(equipments)
            print(f"SCENARIO_{label}: INPUT_OK ({sum(map(len, selected.values()))} materials)")
        for eq in sorted(selected_equipment):
            status = read(f"/costs/status/{quote(eq, safe='')}/{quote(snapshot_id, safe='')}",
                          f"COST_STATUS_{eq}", params={"unit": "material"})
            if timestamp(status["snapshot_id"]) != requested or str(status["targets"]["equipment"]) != eq:
                raise PreflightFailure(f"COST_STATUS_{eq}: SNAPSHOT_OR_EQUIPMENT_MISMATCH")
        print(f"PASS: pinned OSS snapshot {snapshot_id}, scenario inputs and initial cost statuses are usable.")
        return 0
    except PreflightFailure as exc:
        print(str(exc))
    except (KeyError, TypeError, ValueError, AttributeError):
        print("DATA_INVALID: unexpected site/snapshot/status schema or incomplete scenario data (details withheld)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
