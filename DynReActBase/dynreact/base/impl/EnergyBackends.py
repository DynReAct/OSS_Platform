from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

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


_STEEL_DENSITY_KG_M3 = 7856.0


def _va_speed_from_performance_tph(
    performance_tph: Any,
    width_mm: Any,
    thickness_mm: Any,
    *,
    density_kg_m3: float = _STEEL_DENSITY_KG_M3,
) -> float | None:
    """Convert throughput in t/h plus strip geometry into line speed in m/min."""
    throughput_tph = _number_from_mixed(performance_tph, default=0.0)
    width_m = _number_from_mixed(width_mm, default=0.0) / 1000.0
    thickness_m = _number_from_mixed(thickness_mm, default=0.0) / 1000.0
    if throughput_tph <= 0.0 or width_m <= 0.0 or thickness_m <= 0.0 or density_kg_m3 <= 0.0:
        return None
    area_m2 = width_m * thickness_m
    kg_per_hour = throughput_tph * 1000.0
    meters_per_hour = kg_per_hour / (density_kg_m3 * area_m2)
    return meters_per_hour / 60.0


def _derived_planned_speed_va(order: Any, performance_tph: Any) -> float | None:
    """Derive the VA planned speed from throughput and planned geometry."""
    mat_props = getattr(order, "material_properties", None)
    if mat_props is None:
        return None
    width_mm = getattr(mat_props, "width_va_in_planned", None)
    thickness_mm = getattr(mat_props, "thickness_nww_out_planned", None)
    if _is_missing_value(width_mm):
        width_mm = getattr(mat_props, "va_width", None)
    if _is_missing_value(thickness_mm):
        thickness_mm = getattr(mat_props, "va_thickness", None)
    return _va_speed_from_performance_tph(performance_tph, width_mm, thickness_mm)


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
        snapshot_id = self._context.get_snapshot_provider().current_snapshot_id()
        snapshot = self._context.get_snapshot(snapshot_id)
        if snapshot is None:
            return [], "Snapshot not available."
        scheduled = _scheduled_from_snapshot(self._context, snapshot, equipment_names, start_time, end_time)
        if len(scheduled) == 0:
            return [], "No scheduled coils were found for the selected equipment and time window."

        result_rows: list[dict[str, Any]] = []
        skipped = 0
        skipped_no_preferred = 0
        fallback_used = 0
        price_rate_limited = 0
        price_unavailable = 0
        for item in scheduled:
            spec = self._supported.get(item.equipment_name)
            if spec is None:
                continue
            service_equipment = str(spec.get("service_equipment") or item.equipment_name).strip() or item.equipment_name
            features = self._features_from_snapshot(spec, item)
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

    def _service_metadata(self) -> dict[str, Any]:
        cached = getattr(self, "_metadata_cache", None)
        if isinstance(cached, dict):
            return cached
        response = self._session.get(f"{self._base_url}/model", timeout=self._timeout)
        response.raise_for_status()
        data = response.json()
        self._metadata_cache = data if isinstance(data, dict) else {}
        return self._metadata_cache

    def _features_from_snapshot(self, spec: dict[str, Any], item: ScheduledCoil) -> dict[str, Any]:
        service_equipment = str(spec.get("service_equipment") or item.equipment_name).strip() or item.equipment_name
        metadata = self._service_metadata()
        relevant_fields = metadata.get("relevant_fields") or {}
        model_features = metadata.get("model_features") or {}
        equipment_fields = relevant_fields.get(service_equipment)
        if not isinstance(equipment_fields, dict) or len(equipment_fields) == 0:
            raise ValueError(f"Energy service metadata does not define `relevant_fields` for `{service_equipment}`.")
        equipment_models = model_features.get(service_equipment)
        required_names = self._required_feature_names(equipment_models, equipment_fields)
        resolved = {
            feature_name: self._resolve_metadata_mapping(feature_name, descriptor, item)
            for feature_name, descriptor in equipment_fields.items()
            if feature_name in required_names
        }
        return {name: resolved[name] for name in required_names}

    def _required_feature_names(self, equipment_models: Any, equipment_fields: dict[str, Any]) -> list[str]:
        if not isinstance(equipment_models, dict) or len(equipment_models) == 0:
            return list(equipment_fields.keys())
        required: list[str] = []
        seen: set[str] = set()
        for feature_names in equipment_models.values():
            if not isinstance(feature_names, list):
                continue
            for name in feature_names:
                if not isinstance(name, str) or name in seen or name not in equipment_fields:
                    continue
                seen.add(name)
                required.append(name)
        return required or list(equipment_fields.keys())

    def _resolve_metadata_mapping(self, feature_name: str, descriptor: Any, item: ScheduledCoil) -> Any:
        if isinstance(descriptor, str):
            descriptor = {"source": descriptor}
        if not isinstance(descriptor, dict):
            return descriptor
        source = str(descriptor.get("source") or "").strip()
        if source == "":
            raise ValueError(f"Energy service metadata for `{feature_name}` is missing a source expression.")
        required = bool(descriptor.get("required", True))
        raw_value = self._resolve_source_path(source, item)
        if _is_missing_value(raw_value):
            if required:
                raise ValueError(f"Missing required energy feature `{feature_name}` from `{source}`.")
            raw_value = descriptor.get("default")
        scale = descriptor.get("scale")
        if isinstance(scale, (int, float)) and raw_value is not None:
            raw_value = float(_number_from_mixed(raw_value)) * float(scale)
        return raw_value

    def _resolve_source_path(self, source: str, item: ScheduledCoil) -> Any:
        if source == "duration_min":
            return item.duration_min
        if source == "time_gap_min":
            return item.time_gap_min
        if source == "weight":
            return getattr(item.coil, "weight", None) if item.coil is not None else getattr(item.order, "actual_weight", None)
        if source == "derived_planned_speed_va[$EQUIPMENT]":
            equipment = self._context.get_site().get_equipment_by_name(item.equipment_name)
            if equipment is None:
                return None
            performance = getattr(item.order, "equipment_performance", None)
            throughput_tph = performance.get(equipment.id) if isinstance(performance, dict) else None
            return _derived_planned_speed_va(item.order, throughput_tph)
        if source == "equipment_performance[$EQUIPMENT]":
            equipment = self._context.get_site().get_equipment_by_name(item.equipment_name)
            if equipment is None:
                return None
            performance = getattr(item.order, "equipment_performance", None)
            if isinstance(performance, dict):
                return performance.get(equipment.id)
            return None
        root_name, _, remainder = source.partition(".")
        root: Any
        if root_name == "order":
            root = item.order
        elif root_name == "coil":
            root = item.coil
        elif root_name == "equipment":
            root = self._context.get_site().get_equipment_by_name(item.equipment_name)
        else:
            raise ValueError(f"Unsupported energy metadata source `{source}`.")
        value = root
        for part in remainder.split(".") if remainder else []:
            if value is None:
                return None
            if isinstance(value, dict):
                value = value.get(part)
            else:
                value = getattr(value, part, None)
        return value

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
        service_equipment = str(spec.get("service_equipment") or "").strip()
        if service_equipment == "":
            raise ValueError(
                f"Energy HTTP configuration for `{equipment_name}` is missing `service_equipment`."
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
