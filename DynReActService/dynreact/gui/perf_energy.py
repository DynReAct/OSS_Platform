"""Configurable energy analysis page.

The energy page is selected through the `DYNREACT_ENERGY` configuration.
Recommended values follow the standard DynReAct file-provider style:

- `default+file:./data/energy_context.json` for the local OSS evaluator.
- `ras+file:./data/context/energy_context.json` for the RAS HTTP-backed evaluator.

Legacy values such as `http:http://host:port` or `file:./data/energy_context.json`
are still accepted for backwards compatibility.
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import dash
import dash_ag_grid as dash_ag
import plotly.graph_objects as go
import requests
from dash import Input, Output, State, callback, dcc, html

from dynreact.app import config, state

try:
    from dynreact.snapshot.ras import RasSnapshotProvider
except Exception:
    RasSnapshotProvider = None

@dataclass(frozen=True)
class ScheduledCoil:
    """Scheduled coil-like unit to be analysed."""

    equipment_name: str
    coil_id: str
    order_id: str
    start_time: datetime
    end_time: datetime
    duration_min: float
    time_gap_min: float
    order: Any
    coil: Any | None
    lot_id: str | None
    row: dict[str, str] | None = None


def _ensure_local_datetime(value: datetime) -> datetime:
    """Normalize a datetime to a timezone-aware local value."""
    return value.astimezone() if value.tzinfo is not None else value.replace(tzinfo=datetime.now().astimezone().tzinfo)


def _parse_ras_datetime(value: str | None) -> datetime | None:
    """Parse one RAS datetime string."""
    if value is None:
        return None
    stripped = value.strip()
    if stripped == "":
        return None
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d.%m.%Y %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return datetime.strptime(stripped, pattern).astimezone()
        except ValueError:
            continue
    return None


def _number(value: Any, default: float = 0.0) -> float:
    """Convert one value to float using DynReAct-style CSV conventions."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    stripped = str(value).strip()
    if stripped == "":
        return default
    return float(stripped.replace(",", "."))


class EnergyBackend:
    """Common interface for energy backends."""

    def available_equipment(self) -> list[dict[str, str]]:
        """Return selector options."""
        raise NotImplementedError

    def analyse(self, equipment_names: list[str], start_time: datetime, end_time: datetime) -> tuple[list[dict[str, Any]], str]:
        """Run the energy analysis."""
        raise NotImplementedError


class HttpEnergyBackend(EnergyBackend):
    """Backend that delegates the analysis to the external FastAPI service."""

    def __init__(
        self,
        base_url: str,
        *,
        region: str,
        timeout: float,
        token: str | None = None,
        equipment: dict[str, dict[str, str]] | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._region = region
        self._timeout = timeout
        self._supported = equipment or {}
        self._session = requests.Session()
        self._session.headers.update({"accept": "application/json"})
        if token:
            self._session.headers["X-Token"] = token

    def available_equipment(self) -> list[dict[str, str]]:
        site_names = {eq.name_short for eq in state.get_site().get_process_all_equipment()}
        return [{"label": eq, "value": eq} for eq in self._supported if eq in site_names]

    def analyse(self, equipment_names: list[str], start_time: datetime, end_time: datetime) -> tuple[list[dict[str, Any]], str]:
        provider = state.get_snapshot_provider()
        if RasSnapshotProvider is None or not isinstance(provider, RasSnapshotProvider):
            raise ValueError("The HTTP energy backend currently requires the RAS snapshot provider.")
        rows = provider.get_snapshot_rows()
        selected = {eq: self._supported[eq] for eq in equipment_names if eq in self._supported}
        scheduled = self._scheduled_from_rows(rows, selected, start_time, end_time)
        if len(scheduled) == 0:
            return [], "No scheduled coils were found for the selected equipment and time window."

        result_rows: list[dict[str, Any]] = []
        skipped = 0
        for item in scheduled:
            spec = selected[item.equipment_name]
            features = self._features_from_row(item.row or {}, spec, item.duration_min, item.time_gap_min)
            service_equipment = spec["service_equipment"]
            predictions = self._post_json("/energy_estimation_all", params={"equipment_id": service_equipment}, payload={"features": features})
            ensemble_key = f"ensemble_stack_{service_equipment}"
            ensemble_energy = predictions.get(ensemble_key)
            if ensemble_energy is None:
                skipped += 1
                continue
            cost_result = self._post_json(
                "/order_cost_estimation",
                params={
                    "model_key": ensemble_key,
                    "order_id": item.coil_id,
                    "duration_min": item.duration_min,
                    "start_time_iso": item.start_time.isoformat(),
                    "region": self._region,
                },
                payload={"features": features},
            )
            numeric_predictions = [float(val) for val in predictions.values() if isinstance(val, (int, float))]
            result_rows.append(
                {
                    "equipment": item.equipment_name,
                    "coil_id": item.coil_id,
                    "order_id": item.order_id,
                    "lot_id": item.lot_id,
                    "start_time": item.start_time.isoformat(),
                    "end_time": item.end_time.isoformat(),
                    "duration_min": round(item.duration_min, 2),
                    "ensemble_energy_kwh": round(float(ensemble_energy), 3),
                    "uncertainty_min_kwh": round(min(numeric_predictions), 3) if numeric_predictions else None,
                    "uncertainty_max_kwh": round(max(numeric_predictions), 3) if numeric_predictions else None,
                    "energy_cost_eur": round(float(cost_result.get("total_cost_eur", 0.0)), 4),
                    "unit_price_eur_mwh": round(float((cost_result.get("unit_price") or {}).get("price_eur_mwh", 0.0)), 3),
                    "source": "http",
                }
            )
        result_rows.sort(key=lambda item: (item["start_time"], item["equipment"], item["coil_id"]))
        return result_rows, f"Completed the energy analysis for {len(result_rows)} scheduled coils. Skipped {skipped} coils."

    def _scheduled_from_rows(
        self,
        rows: list[dict[str, str]],
        selected: dict[str, dict[str, str]],
        start_time: datetime,
        end_time: datetime,
    ) -> list[ScheduledCoil]:
        grouped: dict[str, list[ScheduledCoil]] = {eq: [] for eq in selected}
        for row in rows:
            coil_id = (row.get("MatID") or row.get("Me-ID-Primary") or "").strip()
            order_id = (row.get("Production Order NR") or "").strip()
            if coil_id == "" or order_id == "":
                continue
            for equipment_name, spec in selected.items():
                lot_id = (row.get(f"{spec['lot_prefix']}LotID") or "").strip()
                if not lot_id.startswith(equipment_name):
                    continue
                start_val = _parse_ras_datetime(row.get(f"{spec['lot_prefix']}_Coil_Start"))
                end_val = _parse_ras_datetime(row.get(f"{spec['lot_prefix']}_Coil_End"))
                if start_val is None or end_val is None:
                    continue
                if end_val < start_time or start_val > end_time:
                    continue
                grouped[equipment_name].append(
                    ScheduledCoil(
                        equipment_name=equipment_name,
                        coil_id=coil_id,
                        order_id=order_id,
                        start_time=start_val,
                        end_time=end_val,
                        duration_min=(end_val - start_val).total_seconds() / 60.0,
                        time_gap_min=0.0,
                        order=None,
                        coil=None,
                        lot_id=lot_id,
                        row=row,
                    )
                )
        result: list[ScheduledCoil] = []
        for equipment_name, items in grouped.items():
            previous_end: datetime | None = None
            for item in sorted(items, key=lambda current: (current.start_time, current.coil_id)):
                time_gap = 0.0 if previous_end is None else max(0.0, (item.start_time - previous_end).total_seconds() / 60.0)
                result.append(
                    ScheduledCoil(
                        equipment_name=item.equipment_name,
                        coil_id=item.coil_id,
                        order_id=item.order_id,
                        start_time=item.start_time,
                        end_time=item.end_time,
                        duration_min=item.duration_min,
                        time_gap_min=time_gap,
                        order=item.order,
                        coil=item.coil,
                        lot_id=item.lot_id,
                        row=item.row,
                    )
                )
                previous_end = item.end_time
        return result

    def _features_from_row(self, row: dict[str, str], spec: dict[str, str], duration_min: float, time_gap_min: float) -> dict[str, Any]:
        service_equipment = spec["service_equipment"]
        if service_equipment in ("TD1", "TD2"):
            return {
                "Length Out": _number(row.get("Final Length (mm)")),
                "Length In": _number(row.get("HRC Width (mm)")),
                "Thickness-Planned-Out (TD)": _number(row.get("Thickness-Planned-Out (TD) (mm)")),
                "Thickness-Planned-In (TD)": _number(row.get("Thickness-Planned-In (TD) (mm)")),
                "Weight Out": _number(row.get("Weight (t)")) * 1000.0,
                "Steelgrade": _number(row.get("Steelgrade")),
                "Planned Performance (TD)": _number(row.get(spec["performance_column"])),
            }
        return {
            "Width input actual": _number(row.get("Width-Out (NW) (mm)") or row.get("Width-Out (VA) (mm)")),
            "Thickness input actual": _number(row.get("Thickness-Planned-Out (NW) (mm)")),
            "Mat-ID of HRC": row.get("Mat-ID-In") or row.get("Me-ID-Primary") or "",
            "Tin layer up": _number(row.get("Tin Layer Up")),
            "Tin layer down": _number(row.get("Tin Layer Down")),
            "Speed acutal": _number(row.get(spec["performance_column"])),
            "Weight Input (t)": _number(row.get("Weight (t)")),
            "Processing time (min)": duration_min,
            "Time_gap": time_gap_min,
        }

    def _post_json(self, path: str, params: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        response = self._session.post(f"{self._base_url}{path}", params=params, json=payload, timeout=self._timeout)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}


class FileEnergyBackend(EnergyBackend):
    """Backend that evaluates local formulas from a JSON context file."""

    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)
        if not self._path.is_absolute():
            self._path = (Path.cwd() / self._path).resolve()
        with self._path.open("r", encoding="utf-8") as handle:
            self._context = _normalize_energy_context(json.load(handle))

    def available_equipment(self) -> list[dict[str, str]]:
        equipment_cfg = self._context.get("equipment") or {}
        site_names = {eq.name_short for eq in state.get_site().get_process_all_equipment()}
        return [{"label": eq, "value": eq} for eq in equipment_cfg if eq in site_names]

    def analyse(self, equipment_names: list[str], start_time: datetime, end_time: datetime) -> tuple[list[dict[str, Any]], str]:
        snapshot_id = state.get_snapshot_provider().current_snapshot_id()
        snapshot = state.get_snapshot(snapshot_id)
        if snapshot is None:
            return [], "Snapshot not available."
        scheduled = _scheduled_from_snapshot(snapshot, equipment_names, start_time, end_time)
        if len(scheduled) == 0:
            return [], "No scheduled coils were found for the selected equipment and time window."
        defaults = self._context.get("defaults") or {}
        result_rows: list[dict[str, Any]] = []
        for item in scheduled:
            equipment_cfg = defaults | ((self._context.get("equipment") or {}).get(item.equipment_name) or {})
            metrics = self._evaluate_metrics(item, equipment_cfg)
            result_rows.append(
                {
                    "equipment": item.equipment_name,
                    "coil_id": item.coil_id,
                    "order_id": item.order_id,
                    "lot_id": item.lot_id,
                    "start_time": item.start_time.isoformat(),
                    "end_time": item.end_time.isoformat(),
                    "duration_min": round(item.duration_min, 2),
                    "ensemble_energy_kwh": round(float(metrics["ensemble_energy_kwh"]), 3),
                    "uncertainty_min_kwh": round(float(metrics["uncertainty_min_kwh"]), 3),
                    "uncertainty_max_kwh": round(float(metrics["uncertainty_max_kwh"]), 3),
                    "energy_cost_eur": round(float(metrics["energy_cost_eur"]), 4),
                    "unit_price_eur_mwh": round(float(metrics["unit_price_eur_mwh"]), 3),
                    "source": "file",
                }
            )
        result_rows.sort(key=lambda item: (item["start_time"], item["equipment"], item["coil_id"]))
        return result_rows, f"Completed the local energy analysis for {len(result_rows)} scheduled coils using {self._path.name}."

    def _evaluate_metrics(self, item: ScheduledCoil, equipment_cfg: dict[str, Any]) -> dict[str, float]:
        price_expr = equipment_cfg.get("price_eur_mwh", "80.0")
        energy_expr = equipment_cfg.get("energy_kwh", "coil_weight_t * duration_min * 10.0")
        cost_expr = equipment_cfg.get("cost_eur", "ensemble_energy_kwh * unit_price_eur_mwh / 1000.0")
        min_expr = equipment_cfg.get("uncertainty_min_kwh", "ensemble_energy_kwh * uncertainty_min_factor")
        max_expr = equipment_cfg.get("uncertainty_max_kwh", "ensemble_energy_kwh * uncertainty_max_factor")
        variables = _file_eval_context(item, equipment_cfg)
        unit_price = _safe_eval(price_expr, variables)
        variables["unit_price_eur_mwh"] = unit_price
        ensemble_energy = _safe_eval(energy_expr, variables)
        variables["ensemble_energy_kwh"] = ensemble_energy
        cost = _safe_eval(cost_expr, variables)
        variables["energy_cost_eur"] = cost
        uncertainty_min = _safe_eval(min_expr, variables)
        uncertainty_max = _safe_eval(max_expr, variables)
        return {
            "ensemble_energy_kwh": ensemble_energy,
            "energy_cost_eur": cost,
            "uncertainty_min_kwh": uncertainty_min,
            "uncertainty_max_kwh": uncertainty_max,
            "unit_price_eur_mwh": unit_price,
        }


def _scheduled_from_snapshot(snapshot: Any, equipment_names: list[str], start_time: datetime, end_time: datetime) -> list[ScheduledCoil]:
    """Extract scheduled coils from a generic snapshot."""
    start_time = _ensure_local_datetime(start_time)
    end_time = _ensure_local_datetime(end_time)
    coils_by_order = state.get_coils_by_order(snapshot.timestamp)
    site = state.get_site()
    scheduled: list[ScheduledCoil] = []
    for equipment_name in equipment_names:
        equipment = site.get_equipment_by_name(equipment_name)
        if equipment is None:
            continue
        process_name = equipment.process
        for order in snapshot.orders:
            if not getattr(order, "lots", None) or not getattr(order, "lot_start_end_times", None):
                continue
            lot_id = order.lots.get(process_name)
            times = order.lot_start_end_times.get(process_name) if order.lot_start_end_times else None
            if lot_id is None or times is None or not lot_id.startswith(equipment_name):
                continue
            order_start, order_end = (_ensure_local_datetime(times[0]), _ensure_local_datetime(times[1]))
            if order_end < start_time or order_start > end_time:
                continue
            coils = sorted(coils_by_order.get(order.id, []), key=lambda coil: (coil.order_position or 0, coil.id))
            if len(coils) == 0:
                coils = [None]
            slot = (order_end - order_start) / len(coils)
            previous_end: datetime | None = None
            for index, coil in enumerate(coils):
                coil_start = order_start + index * slot
                coil_end = order_start + (index + 1) * slot
                time_gap = 0.0 if previous_end is None else max(0.0, (coil_start - previous_end).total_seconds() / 60.0)
                scheduled.append(
                    ScheduledCoil(
                        equipment_name=equipment_name,
                        coil_id=coil.id if coil is not None else order.id,
                        order_id=order.id,
                        start_time=coil_start,
                        end_time=coil_end,
                        duration_min=(coil_end - coil_start).total_seconds() / 60.0,
                        time_gap_min=time_gap,
                        order=order,
                        coil=coil,
                        lot_id=lot_id,
                    )
                )
                previous_end = coil_end
    return scheduled


def _safe_eval(expression: str, variables: dict[str, Any]) -> float:
    """Evaluate one local energy expression with a restricted namespace."""
    allowed = {
        "abs": abs,
        "min": min,
        "max": max,
        "round": round,
        "math": math,
        "float": float,
        "int": int,
    }
    return float(eval(expression, {"__builtins__": {}}, allowed | variables))


def _file_eval_context(item: ScheduledCoil, equipment_cfg: dict[str, Any]) -> dict[str, Any]:
    """Build the variable context for file-based formula evaluation."""
    coil = item.coil
    order = item.order
    props = getattr(order, "material_properties", {}) or {}
    equipment = state.get_site().get_equipment_by_name(item.equipment_name)
    finishing_type = props.get("finishing_type")
    width_mm = _number(props.get("width"), _number(props.get("material_width"), 0.0))
    thickness_initial_mm = _number(props.get("thickness_initial"), _number(props.get("material_thickness_initial"), 0.0))
    thickness_final_mm = _number(props.get("thickness_final"), _number(props.get("material_thickness_final"), 0.0))
    return {
        "equipment": item.equipment_name,
        "equipment_id": getattr(equipment, "id", None),
        "process": getattr(equipment, "process", ""),
        "throughput_capacity": _number(getattr(equipment, "throughput_capacity", 0.0), 0.0),
        "coil_id": item.coil_id,
        "order_id": item.order_id,
        "duration_min": item.duration_min,
        "time_gap_min": item.time_gap_min,
        "start_time": item.start_time,
        "end_time": item.end_time,
        "storage": getattr(coil, "current_storage", None) if coil is not None else None,
        "coil_weight_t": _number(getattr(coil, "weight", None), _number(getattr(order, "actual_weight", None), 0.0)),
        "order_weight_t": _number(getattr(order, "actual_weight", None), 0.0),
        "target_weight_t": _number(getattr(order, "target_weight", None), 0.0),
        "coil_position": getattr(coil, "order_position", 1) if coil is not None else 1,
        "material_count": getattr(order, "material_count", 1) or 1,
        "width_mm": width_mm,
        "thickness_initial_mm": thickness_initial_mm,
        "thickness_final_mm": thickness_final_mm,
        "reduction_ratio": ((thickness_initial_mm - thickness_final_mm) / thickness_initial_mm) if thickness_initial_mm > 0 else 0.0,
        "finishing_type": finishing_type,
        "is_ftype1": 1.0 if finishing_type == "ftype1" else 0.0,
        "is_ftype2": 1.0 if finishing_type == "ftype2" else 0.0,
        "props": props,
        "num": _number,
        "prop": lambda name, default=0.0: _number(props.get(name), default),
        "uncertainty_min_factor": float(equipment_cfg.get("uncertainty_min_factor", 0.9)),
        "uncertainty_max_factor": float(equipment_cfg.get("uncertainty_max_factor", 1.1)),
    }


def _energy_source() -> str:
    """Return the configured energy provider URI."""
    provider = (config.energy_provider or "").strip()
    if provider == "":
        raise ValueError("DYNREACT_ENERGY is not configured.")
    return provider


def _provider_file_path(provider: str) -> Path | None:
    """Resolve one file-backed provider URI to an absolute path."""
    if provider.startswith("default+file:"):
        provider = provider[len("default+file:"):]
    elif provider.startswith("ras+file:"):
        provider = provider[len("ras+file:"):]
    elif provider.startswith("file:"):
        provider = provider[len("file:"):]
    else:
        return None
    path = Path(provider)
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    return path


def _resolve_http_token(http_cfg: dict[str, Any]) -> str | None:
    """Resolve the HTTP token, preferably from the environment."""
    token = http_cfg.get("token")
    if token:
        return str(token)
    token_env = str(http_cfg.get("token_env") or "DYNREACT_ENERGY_HTTP_TOKEN").strip()
    return os.getenv(token_env)


def _build_http_backend(http_cfg: dict[str, Any]) -> HttpEnergyBackend:
    """Instantiate the HTTP backend from one JSON config block."""
    base_url = str(http_cfg.get("base_url") or "").strip()
    if base_url == "":
        raise ValueError("Energy HTTP configuration is missing `base_url`.")
    equipment = http_cfg.get("equipment")
    if not isinstance(equipment, dict) or len(equipment) == 0:
        raise ValueError("Energy HTTP configuration is missing `equipment` mappings.")
    return HttpEnergyBackend(
        base_url,
        region=str(http_cfg.get("region") or "DE"),
        timeout=float(http_cfg.get("timeout", 20.0)),
        token=_resolve_http_token(http_cfg),
        equipment=equipment,
    )


def _normalize_energy_context(context: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy and structured energy context layouts."""
    normalized = dict(context)
    functions_cfg = normalized.get("energy_functions")
    if isinstance(functions_cfg, dict):
        normalized["defaults"] = functions_cfg.get("defaults", normalized.get("defaults") or {})
        normalized["equipment"] = functions_cfg.get("equipment", normalized.get("equipment") or {})
    return normalized


def _build_backend_from_context(path: Path, context: dict[str, Any]) -> EnergyBackend:
    """Instantiate one backend from a JSON energy context file."""
    normalized = _normalize_energy_context(context)
    provider_type = str(normalized.get("provider") or "file").strip().lower()
    if provider_type == "file":
        return FileEnergyBackend(str(path))
    if provider_type == "http":
        http_cfg = normalized.get("http") if isinstance(normalized.get("http"), dict) else normalized
        return _build_http_backend(http_cfg)
    raise ValueError(f"Unsupported energy context provider `{provider_type}` in {path}.")


def _build_backend() -> EnergyBackend:
    """Instantiate the configured backend."""
    provider = _energy_source().strip()
    file_path = _provider_file_path(provider)
    if file_path is not None:
        with file_path.open("r", encoding="utf-8") as handle:
            context = json.load(handle)
        return _build_backend_from_context(file_path, context)
    if provider.endswith(".json") or provider.startswith("./") or provider.startswith("../") or provider.startswith("/"):
        path = Path(provider)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        with path.open("r", encoding="utf-8") as handle:
            context = json.load(handle)
        return _build_backend_from_context(path, context)
    if provider.startswith("http://") or provider.startswith("https://"):
        return HttpEnergyBackend(provider, region="DE", timeout=20.0, token=os.getenv("DYNREACT_ENERGY_HTTP_TOKEN"))
    if provider.startswith("http:") and not provider.startswith("http://"):
        return HttpEnergyBackend(provider[len("http:"):], region="DE", timeout=20.0, token=os.getenv("DYNREACT_ENERGY_HTTP_TOKEN"))
    if provider.startswith("https:") and not provider.startswith("https://"):
        return HttpEnergyBackend(provider[len("https:"):], region="DE", timeout=20.0, token=os.getenv("DYNREACT_ENERGY_HTTP_TOKEN"))
    raise ValueError(f"Unsupported DYNREACT_ENERGY value: {provider}")


_backend = _build_backend()


def _table_columns() -> list[dict[str, Any]]:
    """Return the AgGrid column configuration."""
    return [
        {"field": "equipment", "pinned": True},
        {"field": "coil_id", "headerName": "Coil", "pinned": True},
        {"field": "order_id", "headerName": "Order"},
        {"field": "lot_id", "headerName": "Lot"},
        {"field": "start_time", "headerName": "Start"},
        {"field": "end_time", "headerName": "End"},
        {"field": "duration_min", "headerName": "Duration (min)", "filter": "agNumberColumnFilter"},
        {"field": "ensemble_energy_kwh", "headerName": "Ensemble energy (kWh)", "filter": "agNumberColumnFilter"},
        {"field": "uncertainty_min_kwh", "headerName": "Uncertainty min (kWh)", "filter": "agNumberColumnFilter"},
        {"field": "uncertainty_max_kwh", "headerName": "Uncertainty max (kWh)", "filter": "agNumberColumnFilter"},
        {"field": "energy_cost_eur", "headerName": "Cost (EUR)", "filter": "agNumberColumnFilter"},
        {"field": "unit_price_eur_mwh", "headerName": "Unit price (EUR/MWh)", "filter": "agNumberColumnFilter"},
        {"field": "source", "headerName": "Source"},
    ]


def _empty_figure() -> go.Figure:
    """Return the initial empty figure."""
    fig = go.Figure()
    fig.update_layout(template="plotly_white", height=650, title="Energy estimation results", xaxis_title="Time", yaxis_title="Energy per coil (kWh)")
    return fig


def _build_figure(rows: list[dict[str, Any]], start_value: str, end_value: str) -> go.Figure:
    """Create the final figure."""
    if len(rows) == 0:
        return _empty_figure()
    fig = go.Figure()
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#17becf", "#8c564b"]
    color_by_equipment = {name: colors[idx % len(colors)] for idx, name in enumerate(sorted({row["equipment"] for row in rows}))}
    for equipment_name in sorted({row["equipment"] for row in rows}):
        equipment_rows = sorted([row for row in rows if row["equipment"] == equipment_name], key=lambda item: item["start_time"])
        color = color_by_equipment[equipment_name]
        x_values = [datetime.fromisoformat(row["start_time"]) for row in equipment_rows]
        y_values = [row["ensemble_energy_kwh"] for row in equipment_rows]
        y_low = [row["uncertainty_min_kwh"] for row in equipment_rows]
        y_high = [row["uncertainty_max_kwh"] for row in equipment_rows]
        cum_energy = []
        cum_cost = []
        running_energy = 0.0
        running_cost = 0.0
        for row in equipment_rows:
            running_energy += float(row["ensemble_energy_kwh"] or 0.0)
            running_cost += float(row["energy_cost_eur"] or 0.0)
            cum_energy.append(running_energy)
            cum_cost.append(running_cost)
        fig.add_trace(go.Scatter(x=x_values + list(reversed(x_values)), y=y_high + list(reversed(y_low)), fill="toself", fillcolor=f"rgba(99,110,250,0.15)", line={"color": "rgba(0,0,0,0)"}, hoverinfo="skip", name=f"{equipment_name} uncertainty"))
        fig.add_trace(go.Scatter(x=x_values, y=y_values, mode="lines+markers", line={"color": color}, name=f"{equipment_name} ensemble"))
        fig.add_trace(go.Scatter(x=x_values, y=cum_energy, mode="lines", line={"color": color, "dash": "dash"}, name=f"{equipment_name} cumulative energy", yaxis="y2"))
        fig.add_trace(go.Scatter(x=x_values, y=cum_cost, mode="lines", line={"color": color, "dash": "dot"}, name=f"{equipment_name} cumulative cost", yaxis="y3"))
    fig.update_layout(
        template="plotly_white",
        height=720,
        xaxis={"title": "Time", "range": [datetime.fromisoformat(start_value), datetime.fromisoformat(end_value)]},
        yaxis={"title": "Energy per coil (kWh)"},
        yaxis2={"title": "Cumulative energy (kWh)", "overlaying": "y", "side": "right"},
        yaxis3={"title": "Cumulative cost (EUR)", "anchor": "free", "overlaying": "y", "side": "right", "position": 0.96},
        legend={"orientation": "h", "y": 1.02, "x": 0},
    )
    return fig


def layout(*args: Any, **kwargs: Any) -> html.Div:
    """Render the energy page."""
    snapshot_id = state.get_snapshot_provider().current_snapshot_id()
    snapshot_label = snapshot_id.strftime("%Y-%m-%d %H:%M:%S %Z") if snapshot_id is not None else "None"
    return html.Div(
        [
            dcc.ConfirmDialog(id="perf-energy-validation-dialog"),
            html.H1("Energy"),
            html.H2(f"Snapshot: {snapshot_label}"),
            # html.Div([html.Div("Configured source", style={"fontWeight": "bold"}), html.Div(_energy_source(), id="perf-energy-source")], style={"marginBottom": "1rem"}),
            html.Div([html.Div("Supported equipment", style={"fontWeight": "bold", "marginBottom": "0.5rem"}), dcc.Checklist(id="perf-energy-equipment-checklist", options=_backend.available_equipment(), value=[], inline=True, inputStyle={"marginRight": "0.35rem", "marginLeft": "0.75rem"})], style={"marginBottom": "1rem"}),
            html.Div(
                [
                    html.Div([html.Label("From", htmlFor="perf-energy-from", style={"fontWeight": "bold"}), dcc.Input(id="perf-energy-from", type="datetime-local")], style={"display": "flex", "flexDirection": "column", "gap": "0.35rem"}),
                    html.Div([html.Label("Until", htmlFor="perf-energy-until", style={"fontWeight": "bold"}), dcc.Input(id="perf-energy-until", type="datetime-local")], style={"display": "flex", "flexDirection": "column", "gap": "0.35rem"}),
                    html.Div([html.Button("Start", id="perf-energy-start", className="dynreact-button")], style={"display": "flex", "alignItems": "end"}),
                ],
                style={"display": "flex", "gap": "1rem", "flexWrap": "wrap", "marginBottom": "1rem"},
            ),
            html.Div("Waiting for input.", id="perf-energy-status", style={"marginBottom": "1rem"}),
            html.Div("Total price: 0.00 EUR", id="perf-energy-total-price", style={"fontWeight": "bold", "marginBottom": "1rem"}),
            dcc.Loading(
                [
                    dash_ag.AgGrid(id="perf-energy-table", columnDefs=_table_columns(), rowData=[], className="ag-theme-alpine", defaultColDef={"sortable": True, "filter": True, "resizable": True}, style={"height": "340px", "width": "100%", "marginBottom": "1rem"}, columnSize="responsiveSizeToFit"),
                    dcc.Graph(id="perf-energy-graph", figure=_empty_figure()),
                ],
                delay_show=100,
            ),
        ]
    )


@callback(
    Output("perf-energy-validation-dialog", "displayed"),
    Output("perf-energy-validation-dialog", "message"),
    Output("perf-energy-status", "children"),
    Output("perf-energy-table", "rowData"),
    Output("perf-energy-graph", "figure"),
    Output("perf-energy-total-price", "children"),
    Input("perf-energy-start", "n_clicks"),
    State("perf-energy-equipment-checklist", "value"),
    State("perf-energy-from", "value"),
    State("perf-energy-until", "value"),
    prevent_initial_call=True,
)
def run_energy_analysis(_: int, equipment_names: list[str] | None, start_value: str | None, end_value: str | None) -> tuple[bool, str, str, list[dict[str, Any]], go.Figure, str]:
    """Validate input and run the configured analysis backend."""
    equipment_names = equipment_names or []
    if len(equipment_names) == 0 or not start_value or not end_value:
        return True, "Please select at least one equipment and both time bounds before starting the analysis.", "Waiting for valid input.", dash.no_update, dash.no_update, dash.no_update
    start_time = _ensure_local_datetime(datetime.fromisoformat(start_value))
    end_time = _ensure_local_datetime(datetime.fromisoformat(end_value))
    if end_time <= start_time:
        return True, "The 'Until' timestamp must be later than the 'From' timestamp.", "Waiting for valid input.", dash.no_update, dash.no_update, dash.no_update
    try:
        rows, status = _backend.analyse(equipment_names, start_time, end_time)
    except Exception as exc:
        return True, str(exc), f"Analysis failed: {exc}", [], _empty_figure(), "Total price: 0.00 EUR"
    total_price = sum(float(row.get("energy_cost_eur") or 0.0) for row in rows)
    return False, "", status, rows, _build_figure(rows, start_value, end_value), f"Total price: {total_price:.2f} EUR"
