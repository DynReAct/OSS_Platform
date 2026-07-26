from __future__ import annotations

import csv
import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Protocol, cast

import requests


@dataclass(frozen=True)
class EnergyBackendContext:
    """Runtime accessors used by shared energy backends."""

    get_site: Callable[[], Any]
    get_snapshot_provider: Callable[[], Any]
    get_snapshot: Callable[[datetime], Any]
    get_coils_by_order: Callable[[datetime], dict[str, list[Any]]]


@dataclass(frozen=True)
class ScheduledCoil:
    """Represent one scheduled coil prepared for energy evaluation."""

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


class SnapshotRowsProvider(Protocol):
    """Snapshot provider protocol for raw RAS row access."""

    def get_snapshot_rows(self, snapshot: datetime | None = None) -> list[dict[str, str]]:
        """Return raw snapshot rows for an optional snapshot timestamp."""
        ...


class _LegacySnapshotRowsProvider:
    """Compatibility adapter for snapshot providers exposing raw CSV files only."""

    def __init__(self, provider: Any):
        self._provider = provider

    def get_snapshot_rows(self, snapshot: datetime | None = None) -> list[dict[str, str]]:
        snapshot_id = self._resolve_snapshot_id(snapshot)
        if snapshot_id is None:
            return []
        file_name = self._resolve_snapshot_file(snapshot_id)
        if file_name is None:
            return []
        with Path(file_name).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            return [
                {str(key): "" if value is None else str(value) for key, value in row.items()}
                for row in reader
            ]

    def _resolve_snapshot_id(self, snapshot: datetime | None) -> datetime | None:
        find_time = getattr(self._provider, "_find_time", None)
        if callable(find_time):
            resolved = find_time(snapshot)
            return resolved if isinstance(resolved, datetime) else None
        current_snapshot_id = getattr(self._provider, "current_snapshot_id", None)
        if callable(current_snapshot_id):
            resolved = current_snapshot_id() if snapshot is None else snapshot
            return resolved if isinstance(resolved, datetime) else None
        return snapshot

    def _resolve_snapshot_file(self, snapshot_id: datetime) -> str | None:
        snapshot_files = getattr(self._provider, "_snapshot_files", None)
        if not isinstance(snapshot_files, dict) or snapshot_id not in snapshot_files:
            snapshots = getattr(self._provider, "snapshots", None)
            if callable(snapshots):
                resolved = snapshots(
                    datetime.fromtimestamp(0, tz=snapshot_id.tzinfo),
                    datetime.fromtimestamp(9_999_999_999, tz=snapshot_id.tzinfo),
                )
                if resolved is not None:
                    list(resolved)
                snapshot_files = getattr(self._provider, "_snapshot_files", None)
        if isinstance(snapshot_files, dict):
            file_name = snapshot_files.get(snapshot_id)
            if file_name:
                return str(file_name)
        file_name = getattr(self._provider, "_file", None)
        return str(file_name) if file_name else None


def require_snapshot_rows_provider(provider: Any) -> SnapshotRowsProvider:
    """Accept snapshot providers by capability instead of profile-specific type."""
    if callable(getattr(provider, "get_snapshot_rows", None)):
        return cast(SnapshotRowsProvider, provider)
    if callable(getattr(provider, "_find_time", None)) and (
        isinstance(getattr(provider, "_snapshot_files", None), dict) or getattr(provider, "_file", None) is not None
    ):
        return cast(SnapshotRowsProvider, _LegacySnapshotRowsProvider(provider))
    raise ValueError(
        "The HTTP energy backend requires a snapshot provider exposing get_snapshot_rows()."
    )


def _ensure_local_datetime(value: datetime) -> datetime:
    return value.astimezone() if value.tzinfo is not None else value.replace(tzinfo=datetime.now().astimezone().tzinfo)


def _parse_ras_datetime(value: str | None) -> datetime | None:
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
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    stripped = str(value).strip()
    if stripped == "":
        return default
    return float(stripped.replace(",", "."))


def _number_from_mixed(value: Any, default: float = 0.0) -> float:
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
    digits = "".join(ch for ch in direct if ch.isdigit() or ch in ".-")
    if digits in {"", "-", ".", "-."}:
        return default
    try:
        return float(digits)
    except ValueError:
        return default


def _trim_prediction_outliers(values: list[float], sigma_factor: float = 3.0) -> list[float]:
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
    return [
        f"ensemble_stack_{service_equipment}",
        f"hgb_{service_equipment}",
        f"rf_{service_equipment}",
        f"lin_{service_equipment}",
    ]


def _pick_preferred_prediction(predictions: dict[str, Any], service_equipment: str) -> tuple[str | None, float | None]:
    for key in _preferred_prediction_keys(service_equipment):
        value = predictions.get(key)
        if isinstance(value, (int, float)) and math.isfinite(float(value)):
            return key, float(value)
    return None, None


def _prediction_summary(predictions: dict[str, Any], service_equipment: str) -> str:
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
    """Common contract implemented by energy analysis backends."""

    def available_equipment(self) -> list[dict[str, str]]:
        raise NotImplementedError

    def analyse(self, equipment_names: list[str], start_time: datetime, end_time: datetime) -> tuple[list[dict[str, Any]], str]:
        raise NotImplementedError


class HttpEnergyBackend(EnergyBackend):
    """Execute the analysis by calling the external energy FastAPI service."""

    def __init__(
        self,
        base_url: str,
        *,
        region: str,
        timeout: float,
        context: EnergyBackendContext,
        token: str | None = None,
        equipment: dict[str, dict[str, Any]] | None = None,
        uncertainty_sigma_factor: float = 3.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._region = region
        self._timeout = timeout
        self._context = context
        self._supported = equipment or {}
        self._uncertainty_sigma_factor = uncertainty_sigma_factor
        self._session = requests.Session()
        self._session.headers.update({"accept": "application/json"})
        if token:
            self._session.headers["X-Token"] = token

    def available_equipment(self) -> list[dict[str, str]]:
        site_names = {eq.name_short for eq in self._context.get_site().get_process_all_equipment()}
        return [{"label": eq, "value": eq} for eq in self._supported if eq in site_names]

    def analyse(self, equipment_names: list[str], start_time: datetime, end_time: datetime) -> tuple[list[dict[str, Any]], str]:
        provider = require_snapshot_rows_provider(self._context.get_snapshot_provider())
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
        if not isinstance(descriptor, dict):
            return descriptor

        source = str(descriptor.get("source") or "row").strip().lower()
        required = bool(descriptor.get("required", False))
        default = descriptor.get("default", 0.0 if str(descriptor.get("type") or "").strip().lower() == "number" else "")
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
        response = self._session.post(f"{self._base_url}{path}", params=params, json=payload, timeout=self._timeout)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, dict) else {}


class FileEnergyBackend(EnergyBackend):
    """Evaluate the analysis locally from formulas stored in a JSON context."""

    def __init__(self, file_path: str, *, context: EnergyBackendContext) -> None:
        self._context_runtime = context
        self._path = Path(file_path)
        if not self._path.is_absolute():
            self._path = (Path.cwd() / self._path).resolve()
        with self._path.open("r", encoding="utf-8") as handle:
            self._context = normalize_energy_context(json.load(handle))

    def available_equipment(self) -> list[dict[str, str]]:
        equipment_cfg = self._context.get("equipment") or {}
        site_names = {eq.name_short for eq in self._context_runtime.get_site().get_process_all_equipment()}
        return [{"label": eq, "value": eq} for eq in equipment_cfg if eq in site_names]

    def analyse(self, equipment_names: list[str], start_time: datetime, end_time: datetime) -> tuple[list[dict[str, Any]], str]:
        snapshot_id = self._context_runtime.get_snapshot_provider().current_snapshot_id()
        snapshot = self._context_runtime.get_snapshot(snapshot_id)
        if snapshot is None:
            return [], "Snapshot not available."
        scheduled = _scheduled_from_snapshot(self._context_runtime, snapshot, equipment_names, start_time, end_time)
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
        price_expr = equipment_cfg.get("unit_price_eur_mwh", "50.0")
        energy_expr = equipment_cfg.get("ensemble_energy_kwh", "coil_weight_t * duration_min * 10.0")
        cost_expr = equipment_cfg.get("cost_eur", "ensemble_energy_kwh * unit_price_eur_mwh / 1000.0")
        min_expr = equipment_cfg.get("uncertainty_min_kwh", "ensemble_energy_kwh * uncertainty_min_factor")
        max_expr = equipment_cfg.get("uncertainty_max_kwh", "ensemble_energy_kwh * uncertainty_max_factor")
        variables = _file_eval_context(self._context_runtime, item, equipment_cfg)
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


def _scheduled_from_snapshot(
    context: EnergyBackendContext,
    snapshot: Any,
    equipment_names: list[str],
    start_time: datetime,
    end_time: datetime,
) -> list[ScheduledCoil]:
    start_time = _ensure_local_datetime(start_time)
    end_time = _ensure_local_datetime(end_time)
    coils_by_order = context.get_coils_by_order(snapshot.timestamp)
    site = context.get_site()
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


def _file_eval_context(context: EnergyBackendContext, item: ScheduledCoil, equipment_cfg: dict[str, Any]) -> dict[str, Any]:
    coil = item.coil
    order = item.order
    props = getattr(order, "material_properties", {}) or {}
    equipment = context.get_site().get_equipment_by_name(item.equipment_name)
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


def provider_file_path(provider: str) -> Path | None:
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


def resolve_http_token(http_cfg: dict[str, Any]) -> str | None:
    token = http_cfg.get("token")
    if token:
        return str(token)
    token_env = str(http_cfg.get("token_env") or "DYNREACT_ENERGY_HTTP_TOKEN").strip()
    return os.getenv(token_env)


def build_http_backend(http_cfg: dict[str, Any], *, context: EnergyBackendContext) -> HttpEnergyBackend:
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
        token=resolve_http_token(http_cfg),
        equipment=equipment,
        uncertainty_sigma_factor=float(http_cfg.get("uncertainty_sigma_factor", 3.0)),
        context=context,
    )


def normalize_energy_context(context: dict[str, Any]) -> dict[str, Any]:
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
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip() == ""
    return False


def build_backend_from_context(path: Path, context: dict[str, Any], *, runtime_context: EnergyBackendContext) -> EnergyBackend:
    normalized = normalize_energy_context(context)
    provider_type = str(normalized.get("provider") or "file").strip().lower()
    if provider_type == "file":
        return FileEnergyBackend(str(path), context=runtime_context)
    if provider_type == "http":
        http_cfg = normalized["http"] if isinstance(normalized.get("http"), dict) else normalized
        return build_http_backend(http_cfg, context=runtime_context)
    raise ValueError(f"Unsupported energy context provider `{provider_type}` in {path}.")

