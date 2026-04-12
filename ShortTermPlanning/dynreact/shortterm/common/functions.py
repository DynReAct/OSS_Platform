"""
 Module: functions.py 

Functions that depend on the material parameters and equipment status.
These functions depend on how these values are given.
"""
import os
import json
from pathlib import Path
from datetime import datetime, timedelta
import random
import requests
from dynreact.shortterm.common.data.data_functions import get_transition_cost_and_status

def calculate_production_cost(material_params: dict, equipment_status: dict, verbose: int) -> float | None:
    """
    Calculates the production cost incurred by processing the given MATERIAL
    with the given EQUIPMENT. Returns None if the equipment cannot process the material.

    :param dict equipment_status: Status of the EQUIPMENT
    :param dict material_params: Parameters of the MATERIAL
    :param int verbose: Verbosity Level

    :return: Production cost
    :rtype: float
    """
    prod_cost, _ = get_transition_cost_and_status(material_params=material_params, equipment_status=equipment_status, verbose=verbose)
    return prod_cost


def get_new_equipment_status(material_params: dict, equipment_status: dict, verbose: int) -> dict | None:
    """
    Get the status of the EQUIPMENT after processing the given MATERIAL

    :param dict equipment_status: Status of the EQUIPMENT
    :param dict material_params: Parameters of the MATERIAL
    :param int verbose: Verbosity Level

    :return: New equipment status
    :rtype: float
    """
    _, new_status = get_transition_cost_and_status(material_params=material_params, equipment_status=equipment_status, verbose=verbose)
    return new_status

def _resolve_path(file_path: str) -> Path:
    """Resolve one local path using the same fallback roots as the STP runtime."""
    resolved_path = Path(file_path)

    if not resolved_path.exists() and not resolved_path.is_absolute():
        candidate_roots = (
            Path.cwd(),
            Path("/app"),
            Path(__file__).resolve().parents[3],
            Path(__file__).resolve().parents[5],
        )
        for root in candidate_roots:
            candidate = root / resolved_path
            if candidate.exists():
                resolved_path = candidate
                break
    return resolved_path


def _duration_unit_to_seconds(unit: str | int | float | None) -> float:
    """Convert one JSON transport-times unit to seconds."""
    if unit is None:
        return 1.0
    if isinstance(unit, (int, float)):
        return float(unit)
    normalized = str(unit).strip().upper()
    mapping = {
        "PT1S": 1.0,
        "PT1M": 60.0,
        "PT1H": 3600.0,
        "SECOND": 1.0,
        "SECONDS": 1.0,
        "MINUTE": 60.0,
        "MINUTES": 60.0,
        "HOUR": 3600.0,
        "HOURS": 3600.0,
    }
    if normalized in mapping:
        return mapping[normalized]
    raise ValueError(f"Unsupported transport time unit: {unit}")


def _normalize_transport_times_json(data: dict) -> dict[str, dict[str, int]]:
    """Convert DynReAct JSON transport times into the nested STP dictionary."""
    cfg = data.get("transport_times") if isinstance(data.get("transport_times"), dict) else data
    matrix = cfg.get("equipment_matrix") or {}
    unit_seconds = _duration_unit_to_seconds(cfg.get("unit"))
    transport_times: dict[str, dict[str, int]] = {}
    for origin, destinations in matrix.items():
        if not isinstance(destinations, dict):
            continue
        origin_key = str(origin)
        transport_times[origin_key] = {}
        for destination, duration in destinations.items():
            transport_times[origin_key][str(destination)] = int(float(duration) * unit_seconds)
    return transport_times


def _normalize_transport_times_links(links: list[dict], unit: str | int | float | None = None) -> dict[str, dict[str, int]]:
    """Convert one edge-list representation into the nested STP dictionary."""
    unit_seconds = _duration_unit_to_seconds(unit)
    transport_times: dict[str, dict[str, int]] = {}
    for item in links:
        if not isinstance(item, dict):
            continue
        origin = item.get("from", item.get("origin"))
        destination = item.get("to", item.get("destination"))
        duration = item.get("required_time", item.get("time", item.get("duration")))
        if origin is None or destination is None or duration is None:
            continue
        origin_key = str(origin)
        if origin_key not in transport_times:
            transport_times[origin_key] = {}
        transport_times[origin_key][str(destination)] = int(float(duration) * unit_seconds)
    return transport_times


def _parse_transport_times_payload(data: dict | list) -> dict[str, dict[str, int]]:
    """Parse one transport-times payload returned by file or HTTP sources."""
    if isinstance(data, list):
        return _normalize_transport_times_links(data)
    if not isinstance(data, dict):
        return {}
    if isinstance(data.get("transport_times"), dict) or "equipment_matrix" in data:
        return _normalize_transport_times_json(data)
    links = data.get("links", data.get("results"))
    if isinstance(links, list):
        return _normalize_transport_times_links(links, data.get("unit"))
    return {}


def load_transport_times(file_path: str) -> dict[str, dict[str, int]]:
    """
    Extract transport times from a local JSON file.

    JSON files may either contain the DynReAct `site.json` structure with a
    `transport_times` block or a standalone transport-times object.
    """
    resolved_path = _resolve_path(file_path)
    if not resolved_path.exists():
        print(f"File not found: {file_path}")
        return {}
    if resolved_path.suffix.lower() != ".json":
        raise ValueError(f"Unsupported transport times file format for {resolved_path}. Expected one JSON file.")
    print(f"Opening JSON file: {resolved_path}")
    with resolved_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return _parse_transport_times_payload(data)


def load_transport_times_http(base_url: str, timeout: float = 20.0) -> dict[str, dict[str, int]]:
    """
    Extract transport times from an HTTP service.

    Supported responses:
    - DynReAct-style JSON with `transport_times` / `equipment_matrix`
    - A standalone `equipment_matrix` object
    - A list of edges with `from`, `to`, `required_time`
    - Objects exposing the edge list under `links` or `results`
    """
    candidate_urls = [base_url.rstrip("/")]
    for suffix in ("/transport_times", "/transport-times", "/transportTimes"):
        candidate = base_url.rstrip("/") + suffix
        if candidate not in candidate_urls:
            candidate_urls.append(candidate)

    last_error: Exception | None = None
    for candidate_url in candidate_urls:
        try:
            print(f"Loading transport times from URL: {candidate_url}")
            response = requests.get(candidate_url, timeout=timeout, headers={"accept": "application/json"})
            response.raise_for_status()
            data = response.json()
            parsed = _parse_transport_times_payload(data)
            if len(parsed) > 0:
                return parsed
        except (requests.RequestException, ValueError, TypeError) as exc:
            last_error = exc
            continue

    if last_error is not None:
        print(f"Failed to load transport times from {base_url}: {last_error}")
    return {}

def get_transport_times(transport_times_url: str) -> dict:
#TODO: add docs

    print(f"TRANSPORT_TIMES_URL: {transport_times_url}, type: {type(transport_times_url)}")

    if not isinstance(transport_times_url, str):
        print(f"Transport times URL is not a string: {transport_times_url}")
        return {}

    if transport_times_url.startswith("default+file:"):
        file_path = transport_times_url.split("default+file:")[1]
        print(f"Loading transport times from file: {file_path}")

        return load_transport_times(file_path)

    elif transport_times_url.startswith("http://") or transport_times_url.startswith("https://"):
        return load_transport_times_http(transport_times_url)

    print(f"Unknown transport times URL: {transport_times_url}")

    return {}
