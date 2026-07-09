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

from dynreact.gui.snapshot_rows import require_snapshot_rows_provider

@dataclass(frozen=True)
class ScheduledCoil:
    """Represent one scheduled coil prepared for energy evaluation.

    Attributes:
        equipment_name: Site equipment name associated with the coil.
        coil_id: Coil or material identifier used in the snapshot.
        order_id: Production order identifier.
        start_time: Planned processing start time.
        end_time: Planned processing end time.
        duration_min: Planned processing duration in minutes.
        time_gap_min: Idle gap since the previous coil on the same equipment.
        order: Order object when available from snapshot-based analysis.
        coil: Coil object when available from snapshot-based analysis.
        lot_id: Lot identifier associated with the coil.
        row: Raw snapshot row when the data originates from a row provider.
    """

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
    """Normalize one datetime to a timezone-aware local timestamp."""
    return value.astimezone() if value.tzinfo is not None else value.replace(tzinfo=datetime.now().astimezone().tzinfo)


def _parse_ras_datetime(value: str | None) -> datetime | None:
    """Parse one RAS timestamp using the supported export formats."""
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
    """Convert one value to ``float`` using DynReAct CSV conventions."""
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    stripped = str(value).strip()
    if stripped == "":
        return default
    return float(stripped.replace(",", "."))


def _number_from_mixed(value: Any, default: float = 0.0) -> float:
    """Extract a numeric value from mixed alphanumeric strings.

    This helper is used for fields such as ``D00`` or ``A023`` where the
    semantic payload is numeric but the raw source also contains letters.
    """
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    stripped = str(value).strip()
    if stripped == "":
        return default
    direct = stripped.replace(",", ".")
    try:
        return float(direct)
    except ValueError:
        pass
    digits = "".join(ch for ch in direct if ch.isdigit() or ch in '.-')
    if digits in {"", "-", ".", "-."}:
        return default
    try:
        return float(digits)
    except ValueError:
        return default


def _trim_prediction_outliers(values: list[float], sigma_factor: float = 3.0) -> list[float]:
    """Remove extreme predictions before deriving uncertainty bounds.

    Args:
        values: Raw model prediction values for the same coil.
        sigma_factor: Number of standard deviations used as the cutoff.

    Returns:
        Filtered predictions. If filtering would remove every value, the
        original list is returned.
    """
    if len(values) < 3:
        return values
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    sd = math.sqrt(variance)
    if not math.isfinite(sd) or sd == 0.0:
        return values
    lower = mean - sigma_factor * sd
    upper = mean + sigma_factor * sd
    filtered = [value for value in values if lower <= value <= upper]
    return filtered or values


def _preferred_prediction_keys(service_equipment: str) -> list[str]:
    """Return model keys ordered by preference for one service equipment."""
    return [
        f"ensemble_stack_{service_equipment}",
        f"hgb_{service_equipment}",
        f"rf_{service_equipment}",
        f"lin_{service_equipment}",
    ]


def _pick_preferred_prediction(predictions: dict[str, Any], service_equipment: str) -> tuple[str | None, float | None]:
    """Return the best available prediction according to the preference order.

    Args:
        predictions: Mapping from model key to predicted energy.
        service_equipment: Service-side equipment identifier.

    Returns:
        A tuple containing the selected model key and its predicted energy. If
        no finite value is available, both elements are ``None``.
    """
    for key in _preferred_prediction_keys(service_equipment):
        value = predictions.get(key)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return key, float(value)
    return None, None


def _prediction_summary(predictions: dict[str, Any], service_equipment: str) -> str:
    """Render a compact summary of candidate model predictions for the UI."""
    parts: list[str] = []
    for key in _preferred_prediction_keys(service_equipment):
        value = predictions.get(key)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            rendered = f"{float(value):,.2f}"
        elif value is None:
            rendered = "n/a"
        else:
            rendered = str(value)
        parts.append(f"{key}={rendered}")
    return " | ".join(parts)


class EnergyBackend:
    """Define the common contract implemented by all energy analysis backends."""

    def available_equipment(self) -> list[dict[str, str]]:
        """Return checklist options for the equipment selector."""
        raise NotImplementedError

    def analyse(self, equipment_names: list[str], start_time: datetime, end_time: datetime) -> tuple[list[dict[str, Any]], str]:
        """Run the energy analysis for the selected equipment and window."""
        raise NotImplementedError


class HttpEnergyBackend(EnergyBackend):
    """Execute the analysis by calling the external energy FastAPI service."""

    def __init__(
        self,
        base_url: str,
        *,
        region: str,
        timeout: float,
        token: str | None = None,
        equipment: dict[str, dict[str, Any]] | None = None,
        uncertainty_sigma_factor: float = 3.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._region = region
        self._timeout = timeout
        self._supported = equipment or {}
        self._uncertainty_sigma_factor = uncertainty_sigma_factor
        self._session = requests.Session()
        self._session.headers.update({"accept": "application/json"})
        if token:
            self._session.headers["X-Token"] = token

    def available_equipment(self) -> list[dict[str, str]]:
        """Return selector options for supported equipment present at the site."""
        site_names = {eq.name_short for eq in state.get_site().get_process_all_equipment()}
        return [{"label": eq, "value": eq} for eq in self._supported if eq in site_names]

    def analyse(self, equipment_names: list[str], start_time: datetime, end_time: datetime) -> tuple[list[dict[str, Any]], str]:
        """Run the HTTP-backed analysis and prepare UI-ready result rows.

        Args:
            equipment_names: Selected site equipment names.
            start_time: Lower bound of the analysis window.
            end_time: Upper bound of the analysis window.

        Returns:
            A tuple containing the result rows and a human-readable status
            message.
        """
        provider = require_snapshot_rows_provider(state.get_snapshot_provider())
        rows = provider.get_snapshot_rows()
        selected = {eq: self._supported[eq] for eq in equipment_names if eq in self._supported}
        scheduled = self._scheduled_from_rows(rows, selected, start_time, end_time)
        if len(scheduled) == 0:
            return [], "No scheduled coils were found for the selected equipment and time window."

        result_rows: list[dict[str, Any]] = []
        skipped = 0
        skipped_no_preferred = 0
        fallback_used = 0
        price_rate_limited = 0
        price_unavailable = 0
        for item in scheduled:
            spec = selected[item.equipment_name]
            features = self._features_from_row(item.row or {}, spec, item)
            service_equipment = spec["service_equipment"]
            predictions = self._post_json("/energy_estimation_all", params={"equipment_id": service_equipment}, payload={"features": features})
            prediction_summary = _prediction_summary(predictions, service_equipment)
            selected_model_key, selected_energy = _pick_preferred_prediction(predictions, service_equipment)
            if selected_model_key is None or selected_energy is None:
                skipped += 1
                skipped_no_preferred += 1
                continue
            if selected_model_key != f"ensemble_stack_{service_equipment}":
                fallback_used += 1
            numeric_predictions = [float(val) for val in predictions.values() if isinstance(val, (int, float)) and math.isfinite(float(val))]
            sigma_factor = float(spec.get("uncertainty_sigma_factor", self._uncertainty_sigma_factor))
            numeric_predictions = _trim_prediction_outliers(numeric_predictions, sigma_factor=sigma_factor)
            cost_value: float | None = None
            unit_price_value: float | None = None
            try:
                cost_result = self._post_json(
                    "/order_cost_estimation",
                    params={
                        "model_key": selected_model_key,
                        "order_id": item.coil_id,
                        "duration_min": item.duration_min,
                        "start_time_iso": item.start_time.isoformat(),
                        "region": self._region,
                    },
                    payload={"features": features},
                )
                raw_cost = cost_result.get("total_cost_eur")
                if isinstance(raw_cost, (int, float)):
                    cost_value = round(float(raw_cost), 4)
                raw_unit_price = (cost_result.get("unit_price") or {}).get("price_eur_mwh")
                if isinstance(raw_unit_price, (int, float)):
                    unit_price_value = round(float(raw_unit_price), 3)
            except requests.HTTPError as exc:
                message = str(exc)
                if "429" in message and "Too Many Requests" in message:
                    price_rate_limited += 1
                elif "502" in message or "upstream pricing provider" in message:
                    price_unavailable += 1
                else:
                    raise
            result_rows.append(
                {
                    "equipment": item.equipment_name,
                    "coil_id": item.coil_id,
                    "order_id": item.order_id,
                    "lot_id": item.lot_id,
                    "start_time": item.start_time.isoformat(),
                    "end_time": item.end_time.isoformat(),
                    "duration_min": round(item.duration_min, 2),
                    "energy_model_key": selected_model_key,
                    "ensemble_energy_kwh": round(float(selected_energy), 3),
                    "uncertainty_min_kwh": round(min(numeric_predictions), 3) if numeric_predictions else None,
                    "uncertainty_max_kwh": round(max(numeric_predictions), 3) if numeric_predictions else None,
                    "energy_cost_eur": cost_value,
                    "unit_price_eur_mwh": unit_price_value,
                    "model_predictions": prediction_summary,
                }
            )
        result_rows.sort(key=lambda item: (item["start_time"], item["equipment"], item["coil_id"]))
        status = f"Completed the energy analysis for {len(result_rows)} scheduled coils. Skipped {skipped} coils."
        if skipped_no_preferred > 0:
            status += f" {skipped_no_preferred} skipped coils had no finite prediction from the preferred models (ensemble, hgb, rf, lin)."
        if fallback_used > 0:
            status += f" Used fallback models for {fallback_used} coils when the ensemble prediction was unavailable."
        if price_rate_limited > 0:
            status += f" Live pricing was temporarily rate-limited for {price_rate_limited} coils, so their energy is shown without cost."
        if price_unavailable > 0:
            status += f" Live pricing was unavailable for {price_unavailable} coils, so their energy is shown without cost."
        return result_rows, status

    def _scheduled_from_rows(
        self,
        rows: list[dict[str, str]],
        selected: dict[str, dict[str, str]],
        start_time: datetime,
        end_time: datetime,
    ) -> list[ScheduledCoil]:
        """Extract scheduled coils from raw snapshot rows.

        Args:
            rows: Raw snapshot rows as returned by the configured provider.
            selected: Mapping of selected equipment names to their config blocks.
            start_time: Lower bound of the analysis window.
            end_time: Upper bound of the analysis window.

        Returns:
            Scheduled coils intersecting the requested time window.
        """
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

    def _features_from_row(self, row: dict[str, str], spec: dict[str, Any], item: ScheduledCoil) -> dict[str, Any]:
        """Build the feature payload for one scheduled coil row.

        Args:
            row: Raw snapshot row.
            spec: Equipment-specific configuration block.
            item: Scheduled coil metadata derived from the row.

        Returns:
            Feature mapping expected by the energy estimation service.
        """
        feature_table = spec.get("feature_table")
        if isinstance(feature_table, dict) and len(feature_table) > 0:
            resolved = self._resolve_feature_table(row, spec, item, feature_table)
            required = self._required_feature_names(spec, resolved)
            return {name: resolved[name] for name in required}
        service_equipment = str(spec.get("service_equipment") or item.equipment_name).strip() or item.equipment_name
        raise ValueError(
            "Energy HTTP configuration for equipment "
            f"`{item.equipment_name}` (service `{service_equipment}`) is missing `feature_table`."
        )

    def _required_feature_names(self, spec: dict[str, Any], resolved: dict[str, Any]) -> list[str]:
        """Return the union of required feature names across configured models.

        Args:
            spec: Equipment-specific configuration block.
            resolved: Fully resolved feature map for the current row.

        Returns:
            Ordered feature names that should be sent to the service.
        """
        models = spec.get("model_features")
        if not isinstance(models, dict) or len(models) == 0:
            return list(resolved.keys())
        required: list[str] = []
        seen: set[str] = set()
        for feature_names in models.values():
            if not isinstance(feature_names, list):
                continue
            for name in feature_names:
                if not isinstance(name, str) or name in seen or name not in resolved:
                    continue
                seen.add(name)
                required.append(name)
        return required or list(resolved.keys())

    def _resolve_feature_table(
        self,
        row: dict[str, str],
        spec: dict[str, Any],
        item: ScheduledCoil,
        feature_table: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve a declarative feature table into concrete feature values.

        Args:
            row: Raw snapshot row.
            spec: Equipment-specific configuration block.
            item: Scheduled coil metadata.
            feature_table: Declarative mapping of feature names to descriptors.

        Returns:
            Concrete feature values ready to be serialized.
        """
        resolved: dict[str, Any] = {}
        for feature_name, descriptor in feature_table.items():
            if not isinstance(feature_name, str):
                continue
            resolved[feature_name] = self._resolve_feature_value(feature_name, descriptor, row, spec, item)
        return resolved

    def _resolve_feature_value(
        self,
        feature_name: str,
        descriptor: Any,
        row: dict[str, str],
        spec: dict[str, Any],
        item: ScheduledCoil,
    ) -> Any:
        """Resolve one declarative feature descriptor into a concrete value.

        Args:
            feature_name: Logical feature name expected by the model.
            descriptor: Descriptor declaring the value source and coercion rules.
            row: Raw snapshot row.
            spec: Equipment-specific configuration block.
            item: Scheduled coil metadata.

        Returns:
            The resolved feature value, already coerced and scaled if needed.

        Raises:
            ValueError: If the descriptor uses an unsupported source or a
                required value cannot be produced.
        """
        if not isinstance(descriptor, dict):
            return descriptor

        source = str(descriptor.get("source") or "row").strip().lower()
        required = bool(descriptor.get("required", False))
        default = descriptor.get("default", 0.0 if str(descriptor.get("type") or "").strip().lower() == "number" else "")
        raw_value: Any
        if source == "row":
            raw_value = self._row_value(row, descriptor)
        elif source == "computed":
            raw_value = self._computed_value(descriptor, spec, item)
        elif source == "literal":
            raw_value = descriptor.get("value")
        else:
            raise ValueError(f"Unsupported energy feature source `{source}` for `{feature_name}`.")

        if _is_missing_value(raw_value):
            fallback_field = descriptor.get("fallback_computed")
            if isinstance(fallback_field, str) and fallback_field.strip() != "":
                raw_value = self._computed_value({"field": fallback_field}, spec, item)

        if _is_missing_value(raw_value):
            if required:
                columns = descriptor.get("columns") or descriptor.get("column") or descriptor.get("field") or source
                raise ValueError(f"Missing required energy feature `{feature_name}` from `{columns}`.")
            raw_value = default

        value_type = str(descriptor.get("type") or "").strip().lower()
        if value_type == "number":
            parser = _number_from_mixed if bool(descriptor.get("extract_digits", False)) else _number
            value = parser(raw_value, _number(default))
        else:
            value = raw_value
        scale = descriptor.get("scale")
        if isinstance(scale, (int, float)):
            value = float(value) * float(scale)
        return value

    def _row_value(self, row: dict[str, str], descriptor: dict[str, Any]) -> Any:
        """Read one raw value from a row-based descriptor definition."""
        columns = descriptor.get("columns")
        if isinstance(columns, list):
            for column in columns:
                if not isinstance(column, str):
                    continue
                value = row.get(column)
                if not _is_missing_value(value):
                    return value
            return None
        column = descriptor.get("column")
        if isinstance(column, str):
            return row.get(column)
        return None

    def _computed_value(self, descriptor: dict[str, Any], spec: dict[str, Any], item: ScheduledCoil) -> Any:
        """Resolve one computed feature from scheduled-coil metadata.

        Args:
            descriptor: Descriptor containing the computed field name.
            spec: Equipment-specific configuration block.
            item: Scheduled coil metadata.

        Returns:
            Computed value derived from the scheduled item.

        Raises:
            ValueError: If the computed field name is unsupported.
        """
        field = str(descriptor.get("field") or "").strip()
        if field == "duration_min":
            return item.duration_min
        if field == "time_gap_min":
            return item.time_gap_min
        if field == "coil_id":
            return item.coil_id
        if field == "order_id":
            return item.order_id
        if field == "lot_id":
            return item.lot_id
        if field == "start_time_iso":
            return item.start_time.isoformat()
        if field == "end_time_iso":
            return item.end_time.isoformat()
        if field == "performance_column":
            column_name = spec.get("performance_column")
            return item.row.get(column_name) if isinstance(column_name, str) and item.row is not None else None
        raise ValueError(f"Unsupported computed energy field `{field}`.")

    def _post_json(self, path: str, params: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
        """POST one JSON request to the configured energy service endpoint."""
        response = self._session.post(f"{self._base_url}{path}", params=params, json=payload, timeout=self._timeout)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}


class FileEnergyBackend(EnergyBackend):
    """Evaluate the analysis locally from formulas stored in a JSON context."""

    def __init__(self, file_path: str) -> None:
        self._path = Path(file_path)
        if not self._path.is_absolute():
            self._path = (Path.cwd() / self._path).resolve()
        with self._path.open("r", encoding="utf-8") as handle:
            self._context = _normalize_energy_context(json.load(handle))

    def available_equipment(self) -> list[dict[str, str]]:
        """Return selector options for locally configured equipment."""
        equipment_cfg = self._context.get("equipment") or {}
        site_names = {eq.name_short for eq in state.get_site().get_process_all_equipment()}
        return [{"label": eq, "value": eq} for eq in equipment_cfg if eq in site_names]

    def analyse(self, equipment_names: list[str], start_time: datetime, end_time: datetime) -> tuple[list[dict[str, Any]], str]:
        """Run the local formula-based analysis for the selected time window.

        Args:
            equipment_names: Selected site equipment names.
            start_time: Lower bound of the analysis window.
            end_time: Upper bound of the analysis window.

        Returns:
            A tuple containing the result rows and a status message.
        """
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
        """Evaluate configured local formulas for one scheduled coil.

        Args:
            item: Scheduled coil to evaluate.
            equipment_cfg: Effective equipment configuration after defaults.

        Returns:
            Evaluated energy, uncertainty, cost, and unit-price metrics.
        """
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
    """Extract scheduled coils from a generic snapshot-based data source.

    Args:
        snapshot: Snapshot object providing orders, lots, and timing data.
        equipment_names: Selected site equipment names.
        start_time: Lower bound of the analysis window.
        end_time: Upper bound of the analysis window.

    Returns:
        Scheduled coils intersecting the requested time window.
    """
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
    """Evaluate one local formula using a restricted expression namespace.

    Args:
        expression: Formula expression declared in the JSON context.
        variables: Runtime variables made available to the formula.

    Returns:
        Evaluated numeric result as ``float``.
    """
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
    """Build the variable dictionary used by file-based formula backends.

    Args:
        item: Scheduled coil being evaluated.
        equipment_cfg: Effective equipment configuration after defaults.

    Returns:
        Variable mapping exposed to local formula expressions.
    """
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
    """Return the configured energy provider URI from runtime settings."""
    provider = (config.energy_provider or "").strip()
    if provider == "":
        raise ValueError("DYNREACT_ENERGY is not configured.")
    return provider


def _provider_file_path(provider: str) -> Path | None:
    """Resolve one file-backed provider URI into an absolute path."""
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
    """Resolve the HTTP authentication token, preferably from the environment."""
    token = http_cfg.get("token")
    if token:
        return str(token)
    token_env = str(http_cfg.get("token_env") or "DYNREACT_ENERGY_HTTP_TOKEN").strip()
    return os.getenv(token_env)


def _build_http_backend(http_cfg: dict[str, Any]) -> HttpEnergyBackend:
    """Instantiate the HTTP backend from one normalized config block."""
    base_url = str(http_cfg.get("DYNREACT_ENERGY_PERF") or http_cfg.get("base_url") or "").strip()
    if base_url == "":
        raise ValueError("Energy HTTP configuration is missing `DYNREACT_ENERGY_PERF`.")
    equipment = http_cfg.get("equipment")
    if not isinstance(equipment, dict) or len(equipment) == 0:
        raise ValueError("Energy HTTP configuration is missing `equipment` mappings.")
    for equipment_name, spec in equipment.items():
        if not isinstance(spec, dict):
            raise ValueError(f"Energy HTTP configuration for `{equipment_name}` must be a mapping.")
        feature_table = spec.get("feature_table")
        if not isinstance(feature_table, dict) or len(feature_table) == 0:
            raise ValueError(
                f"Energy HTTP configuration for `{equipment_name}` is missing `feature_table`."
            )
    return HttpEnergyBackend(
        base_url,
        region=str(http_cfg.get("region") or "DE"),
        timeout=float(http_cfg.get("timeout", 20.0)),
        token=_resolve_http_token(http_cfg),
        equipment=equipment,
        uncertainty_sigma_factor=float(http_cfg.get("uncertainty_sigma_factor", 3.0)),
    )


def _normalize_energy_context(context: dict[str, Any]) -> dict[str, Any]:
    """Normalize legacy and structured energy context layouts in-place."""
    normalized = dict(context)
    functions_cfg = normalized.get("energy_functions")
    if isinstance(functions_cfg, dict):
        normalized["defaults"] = functions_cfg.get("defaults", normalized.get("defaults") or {})
        normalized["equipment"] = functions_cfg.get("equipment", normalized.get("equipment") or {})
    http_cfg = normalized.get("http")
    if isinstance(http_cfg, dict):
        equipment_cfg = http_cfg.get("equipment")
        if isinstance(equipment_cfg, dict):
            for spec in equipment_cfg.values():
                if not isinstance(spec, dict):
                    continue
                feature_table = spec.get("feature_table")
                legacy_features = spec.get("features")
                if not isinstance(feature_table, dict) and isinstance(legacy_features, dict):
                    spec["feature_table"] = legacy_features
    return normalized


def _is_missing_value(value: Any) -> bool:
    """Return whether one raw value should be treated as missing."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def _friendly_energy_error(exc: Exception) -> tuple[str, str]:
    """Convert one backend exception into user-facing dialog and status text."""
    message = str(exc)
    if "429" in message and "Too Many Requests" in message:
        dialog = "Live electricity pricing is temporarily rate-limited. Energy estimation is available, but price calculation cannot be completed right now. Please retry in a moment."
        status = "Energy analysis could not finish because the live pricing provider is temporarily rate-limited."
        return dialog, status
    if "502" in message or "upstream pricing provider" in message:
        dialog = "Live electricity pricing is temporarily unavailable for the selected time range. Please retry later."
        status = "Energy analysis could not finish because live pricing data is currently unavailable."
        return dialog, status
    return message, f"Analysis failed: {message}"


def _build_backend_from_context(path: Path, context: dict[str, Any]) -> EnergyBackend:
    """Instantiate one backend from a parsed energy context document."""
    normalized = _normalize_energy_context(context)
    provider_type = str(normalized.get("provider") or "file").strip().lower()
    if provider_type == "file":
        return FileEnergyBackend(str(path))
    if provider_type == "http":
        http_cfg: dict[str, Any]
        if isinstance(normalized.get("http"), dict):
            http_cfg = normalized["http"]
        else:
            http_cfg = normalized
        return _build_http_backend(http_cfg)
    raise ValueError(f"Unsupported energy context provider `{provider_type}` in {path}.")


def _build_backend() -> EnergyBackend|None:
    """Instantiate the backend selected by the current runtime configuration."""
    provider = _energy_source().strip()
    file_path = _provider_file_path(provider)
    if file_path is not None and os.path.isfile(file_path):
        with file_path.open("r", encoding="utf-8") as handle:
            context = json.load(handle)
        return _build_backend_from_context(file_path, context)
    if provider.endswith(".json") or provider.startswith("./") or provider.startswith("../") or provider.startswith("/"):
        path = Path(provider)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if os.path.isfile(path):
            with path.open("r", encoding="utf-8") as handle:
                context = json.load(handle)
            return _build_backend_from_context(path, context)
    if provider.startswith("http://") or provider.startswith("https://"):
        return HttpEnergyBackend(provider, region="DE", timeout=20.0, token=os.getenv("DYNREACT_ENERGY_HTTP_TOKEN"))
    if provider.startswith("http:") and not provider.startswith("http://"):
        return HttpEnergyBackend(provider[len("http:"):], region="DE", timeout=20.0, token=os.getenv("DYNREACT_ENERGY_HTTP_TOKEN"))
    if provider.startswith("https:") and not provider.startswith("https://"):
        return HttpEnergyBackend(provider[len("https:"):], region="DE", timeout=20.0, token=os.getenv("DYNREACT_ENERGY_HTTP_TOKEN"))
    # raise ValueError(f"Unsupported DYNREACT_ENERGY value: {provider}")
    return None


_backend = _build_backend()


def _table_columns() -> list[dict[str, Any]]:
    """Return the AgGrid column definition for the main energy result table."""
    return [
        {"field": "equipment", "pinned": True},
        {"field": "coil_id", "headerName": "Coil", "pinned": True},
        {"field": "order_id", "headerName": "Order"},
        {"field": "lot_id", "headerName": "Lot"},
        {"field": "start_time", "headerName": "Start"},
        {"field": "end_time", "headerName": "End"},
        {"field": "duration_min", "headerName": "Duration (min)", "filter": "agNumberColumnFilter"},
        {"field": "energy_model_key", "headerName": "Model"},
        {"field": "ensemble_energy_kwh", "headerName": "Estimated energy (kWh)", "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '' : d3.format(',.2f')(params.value)"}},
        {"field": "uncertainty_min_kwh", "headerName": "Uncertainty min (kWh)", "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '' : d3.format(',.2f')(params.value)"}},
        {"field": "uncertainty_max_kwh", "headerName": "Uncertainty max (kWh)", "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '' : d3.format(',.2f')(params.value)"}},
        {"field": "energy_cost_eur", "headerName": "Cost (EUR)", "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '' : d3.format(',.2f')(params.value)"}},
        {"field": "unit_price_eur_mwh", "headerName": "Unit price (EUR/MWh)", "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '' : d3.format(',.2f')(params.value)"}},
        {"field": "model_predictions", "headerName": "Candidate predictions", "tooltipField": "model_predictions", "minWidth": 360, "flex": 2},
    ]


def _demand_table_columns() -> list[dict[str, Any]]:
    """Return the AgGrid column definition for the total demand table."""
    return [
        {"field": "time", "headerName": "Time", "pinned": True},
        {"field": "interval_end", "headerName": "Interval end"},
        {"field": "total_energy_kwh", "headerName": "Total energy demand (kWh)", "filter": "agNumberColumnFilter", "valueFormatter": {"function": "params.value == null ? '' : d3.format(',.3f')(params.value)"}},
        {"field": "active_coils", "headerName": "Active coils", "filter": "agNumberColumnFilter"},
    ]


def _empty_figure() -> go.Figure:
    """Return the empty Plotly figure used before analysis results exist."""
    fig = go.Figure()
    fig.update_layout(template="plotly_white", height=650, title="Energy estimation results", xaxis_title="Time", yaxis_title="Energy per coil (kWh)")
    return fig


def _empty_demand_figure() -> go.Figure:
    """Return the empty Plotly figure used for total demand before analysis."""
    fig = go.Figure()
    fig.update_layout(template="plotly_white", height=520, title="Total energy demand", xaxis_title="Time", yaxis_title="Total energy demand (kWh / interval)")
    return fig


def _build_figure(rows: list[dict[str, Any]], start_value: str, end_value: str) -> go.Figure:
    """Build the main Plotly figure for per-coil and cumulative energy results."""
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
        fig.add_trace(go.Scatter(x=x_values + list(reversed(x_values)), y=y_high + list(reversed(y_low)), fill="toself", fillcolor=f"rgba(99,110,250,0.10)", line={"color": "rgba(0,0,0,0)"}, hoverinfo="skip", showlegend=False, legendgroup=equipment_name, name=f"{equipment_name} uncertainty"))
        fig.add_trace(go.Scatter(x=x_values, y=y_values, mode="lines+markers", line={"color": color, "width": 2}, marker={"size": 5}, name=f"{equipment_name} energy", legendgroup=equipment_name))
        fig.add_trace(go.Scatter(x=x_values, y=cum_energy, mode="lines", line={"color": color, "dash": "dash", "width": 2}, name=f"{equipment_name} cum. energy", yaxis="y2", hovertemplate="%{y:,.2f} kWh<extra></extra>", legendgroup=equipment_name))
        fig.add_trace(go.Scatter(x=x_values, y=cum_cost, mode="lines", line={"color": color, "dash": "dot", "width": 2}, name=f"{equipment_name} cum. cost", yaxis="y3", hovertemplate="%{y:,.2f} EUR<extra></extra>", legendgroup=equipment_name))
    fig.update_layout(
        template="plotly_white",
        height=760,
        margin={"l": 80, "r": 180, "t": 110, "b": 70},
        xaxis={"title": "Time", "range": [datetime.fromisoformat(start_value), datetime.fromisoformat(end_value)]},
        yaxis={"title": "Energy per coil (kWh)", "tickformat": ",.0f"},
        yaxis2={"title": "Cumulative energy (kWh)", "overlaying": "y", "side": "right", "tickformat": ",.0f", "showgrid": False},
        yaxis3={"title": "Cumulative cost (EUR)", "anchor": "free", "overlaying": "y", "side": "right", "position": 0.90, "tickformat": ",.2f", "tickprefix": "EUR ", "showgrid": False},
        legend={"orientation": "v", "y": 1.0, "yanchor": "top", "x": 1.02, "xanchor": "left", "font": {"size": 11}, "bgcolor": "rgba(255,255,255,0.75)"},
    )
    return fig


def _total_energy_demand_interval_min() -> int:
    """Return the configured aggregation interval for total demand in minutes."""
    provider = _energy_source().strip()
    file_path = _provider_file_path(provider)
    if file_path is not None and os.path.isfile(file_path):
        with file_path.open("r", encoding="utf-8") as handle:
            context = _normalize_energy_context(json.load(handle))
        configured = context.get("total_energy_demand_interval_min")
        if isinstance(configured, (int, float)) and float(configured) > 0:
            return int(float(configured))
    return 5


def _build_total_demand_rows(rows: list[dict[str, Any]], start_value: str, end_value: str, interval_min: int) -> list[dict[str, Any]]:
    """Aggregate predicted energy into fixed-width demand buckets.

    Args:
        rows: Per-coil energy rows already prepared for the UI.
        start_value: Analysis start time in ISO format.
        end_value: Analysis end time in ISO format.
        interval_min: Aggregation interval in minutes.

    Returns:
        Row dictionaries describing total demand per time bucket.
    """
    if len(rows) == 0:
        return []
    interval_seconds = max(1, int(interval_min)) * 60
    analysis_start = _ensure_local_datetime(datetime.fromisoformat(start_value))
    analysis_end = _ensure_local_datetime(datetime.fromisoformat(end_value))
    if analysis_end <= analysis_start:
        return []

    buckets: list[dict[str, Any]] = []
    bucket_start = analysis_start
    while bucket_start < analysis_end:
        bucket_end = min(bucket_start + timedelta(seconds=interval_seconds), analysis_end)
        total_energy = 0.0
        active_coils = 0
        for row in rows:
            row_start = _ensure_local_datetime(datetime.fromisoformat(row["start_time"]))
            row_end = _ensure_local_datetime(datetime.fromisoformat(row["end_time"]))
            overlap_start = max(bucket_start, row_start)
            overlap_end = min(bucket_end, row_end)
            overlap_seconds = max(0.0, (overlap_end - overlap_start).total_seconds())
            if overlap_seconds <= 0.0:
                continue
            duration_seconds = max(1.0, (row_end - row_start).total_seconds())
            total_energy += float(row.get("ensemble_energy_kwh") or 0.0) * (overlap_seconds / duration_seconds)
            active_coils += 1
        buckets.append(
            {
                "time": bucket_start.isoformat(),
                "interval_end": bucket_end.isoformat(),
                "total_energy_kwh": round(total_energy, 3),
                "active_coils": active_coils,
            }
        )
        bucket_start = bucket_end
    return buckets


def _build_total_demand_figure(rows: list[dict[str, Any]], start_value: str, end_value: str, interval_min: int) -> go.Figure:
    """Build the Plotly figure for aggregated total energy demand."""
    demand_rows = _build_total_demand_rows(rows, start_value, end_value, interval_min)
    if len(demand_rows) == 0:
        return _empty_demand_figure()
    x_values = [datetime.fromisoformat(row["time"]) for row in demand_rows]
    y_values = [row["total_energy_kwh"] for row in demand_rows]
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=x_values,
            y=y_values,
            mode="lines+markers",
            line={"color": "#0f766e", "width": 2},
            marker={"size": 5},
            fill="tozeroy",
            fillcolor="rgba(15,118,110,0.12)",
            hovertemplate="%{x}<br>%{y:,.3f} kWh<extra></extra>",
            name="Total energy demand",
        )
    )
    fig.update_layout(
        template="plotly_white",
        height=520,
        title=f"Total energy demand ({interval_min}-minute intervals)",
        xaxis={"title": "Time", "range": [datetime.fromisoformat(start_value), datetime.fromisoformat(end_value)]},
        yaxis={"title": "Total energy demand (kWh / interval)", "tickformat": ",.3f"},
        margin={"l": 80, "r": 40, "t": 80, "b": 60},
    )
    return fig


def layout(*args: Any, **kwargs: Any) -> html.Div|None:
    """Render the configurable energy analysis page.

    Returns:
        The page layout when an energy backend is configured, otherwise ``None``
        so the hosting UI can hide the page gracefully.
    """
    if _backend is None:
        return None
    snapshot_id = state.get_snapshot_provider().current_snapshot_id()
    snapshot_label = snapshot_id.strftime("%Y-%m-%d %H:%M:%S %Z") if snapshot_id is not None else "None"
    demand_interval_min = _total_energy_demand_interval_min()
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
                    html.H2("Total Energy Demand"),
                    html.Div([
                        html.Div(f"Aggregation interval: {demand_interval_min} minutes", style={"fontWeight": "bold"}),
                        html.Button("Download total demand csv", id="perf-energy-demand-download", className="dynreact-button"),
                    ], style={"display": "flex", "justifyContent": "space-between", "alignItems": "center", "marginBottom": "0.5rem", "gap": "1rem", "flexWrap": "wrap"}),
                    dash_ag.AgGrid(id="perf-energy-demand-table", columnDefs=_demand_table_columns(), rowData=[], className="ag-theme-alpine", defaultColDef={"sortable": True, "filter": True, "resizable": True}, style={"height": "280px", "width": "100%", "marginBottom": "1rem"}, columnSize="responsiveSizeToFit"),
                    dcc.Graph(id="perf-energy-demand-graph", figure=_empty_demand_figure()),
                ],
                # delay_show=100,   # compatibility issue; rather new feature of Dash
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
    Output("perf-energy-demand-table", "rowData"),
    Output("perf-energy-demand-graph", "figure"),
    Input("perf-energy-start", "n_clicks"),
    State("perf-energy-equipment-checklist", "value"),
    State("perf-energy-from", "value"),
    State("perf-energy-until", "value"),
    prevent_initial_call=True,
)
def run_energy_analysis(_: int, equipment_names: list[str] | None, start_value: str | None, end_value: str | None) -> tuple[Any, ...]:
    """Validate input, run the backend, and build the Dash callback payload."""
    equipment_names = equipment_names or []
    if len(equipment_names) == 0 or not start_value or not end_value:
        return True, "Please select at least one equipment and both time bounds before starting the analysis.", "Waiting for valid input.", dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    start_time = _ensure_local_datetime(datetime.fromisoformat(start_value))
    end_time = _ensure_local_datetime(datetime.fromisoformat(end_value))
    if end_time <= start_time:
        return True, "The 'Until' timestamp must be later than the 'From' timestamp.", "Waiting for valid input.", dash.no_update, dash.no_update, dash.no_update, dash.no_update, dash.no_update
    backend = _backend
    if backend is None:
        return True, "Energy backend is not configured.", "Waiting for valid input.", [], _empty_figure(), "Total price: 0.00 EUR", [], _empty_demand_figure()
    try:
        rows, status = backend.analyse(equipment_names, start_time, end_time)
    except Exception as exc:
        dialog, status = _friendly_energy_error(exc)
        return True, dialog, status, [], _empty_figure(), "Total price: 0.00 EUR", [], _empty_demand_figure()
    total_price = sum(float(row.get("energy_cost_eur") or 0.0) for row in rows)
    missing_price_rows = sum(1 for row in rows if row.get("energy_cost_eur") is None)
    if missing_price_rows > 0:
        total_label = f"Total price: partial result ({total_price:.2f} EUR, pricing missing for {missing_price_rows} coils)"
    else:
        total_label = f"Total price: {total_price:.2f} EUR"
    demand_interval_min = _total_energy_demand_interval_min()
    demand_rows = _build_total_demand_rows(rows, start_value, end_value, demand_interval_min)
    demand_figure = _build_total_demand_figure(rows, start_value, end_value, demand_interval_min)
    return False, "", status, rows, _build_figure(rows, start_value, end_value), total_label, demand_rows, demand_figure


@callback(
    Output("perf-energy-demand-table", "exportDataAsCsv"),
    Output("perf-energy-demand-table", "csvExportParams"),
    Input("perf-energy-demand-download", "n_clicks"),
    State("perf-energy-demand-table", "rowData"),
    prevent_initial_call=True,
)
def export_total_demand_csv(_: int | None, row_data: list[dict[str, Any]] | None) -> tuple[bool, dict[str, Any] | None]:
    """Trigger CSV export for the total energy demand table."""
    if not row_data:
        return False, None
    snapshot_id = state.get_snapshot_provider().current_snapshot_id()
    timestamp = snapshot_id.strftime("%Y%m%d%H%M%S") if snapshot_id is not None else datetime.now().strftime("%Y%m%d%H%M%S")
    options = {"fileName": f"total_energy_demand_{timestamp}.csv", "columnSeparator": ";", "suppressQuotes": True}
    return True, options
