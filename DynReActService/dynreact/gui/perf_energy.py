"""Configurable energy analysis page.

The energy page is selected through the `DYNREACT_ENERGY` configuration.
Recommended values follow the standard DynReAct file-provider style:

- `default+file:./data/energy_context.json` for the local OSS evaluator.
- `ras+file:./data/config/energy_context.json` for the RAS HTTP-backed evaluator.

Legacy values such as `http:http://host:port` or `file:./data/energy_context.json`
are still accepted for backwards compatibility.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import dash
import dash_ag_grid as dash_ag
import plotly.graph_objects as go
from dash import Input, Output, State, callback, dcc, html

from dynreact.app import config, state

from dynreact.base.impl.EnergyBackends import (
    EnergyBackend,
    EnergyBackendContext,
    HttpEnergyBackend,
    _ensure_local_datetime,
    build_backend_from_context,
    build_http_backend,
    normalize_energy_context,
    provider_file_path,
)



def _runtime_context() -> EnergyBackendContext:
    return EnergyBackendContext(
        get_site=state.get_site,
        get_snapshot_provider=state.get_snapshot_provider,
        get_snapshot=state.get_snapshot,
        get_coils_by_order=state.get_coils_by_order,
    )


def _energy_source() -> str:
    """Return the configured energy provider URI from runtime settings."""
    provider = (config.energy_provider or "").strip()
    if provider == "":
        raise ValueError("DYNREACT_ENERGY is not configured.")
    return provider

def _build_http_backend(http_cfg: dict[str, Any]) -> HttpEnergyBackend:
    """Instantiate the HTTP backend from one normalized config block."""
    return build_http_backend(http_cfg, context=_runtime_context())



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


def _build_backend() -> EnergyBackend|None:
    """Instantiate the backend selected by the current runtime configuration."""
    provider = _energy_source().strip()
    file_path = provider_file_path(provider)
    if file_path is not None and os.path.isfile(file_path):
        with file_path.open("r", encoding="utf-8") as handle:
            context = json.load(handle)
        return build_backend_from_context(file_path, context, runtime_context=_runtime_context())
    if provider.endswith(".json") or provider.startswith("./") or provider.startswith("../") or provider.startswith("/"):
        path = Path(provider)
        if not path.is_absolute():
            path = (Path.cwd() / path).resolve()
        if os.path.isfile(path):
            with path.open("r", encoding="utf-8") as handle:
                context = json.load(handle)
            return build_backend_from_context(path, context, runtime_context=_runtime_context())
    if provider.startswith("http://") or provider.startswith("https://"):
        return HttpEnergyBackend(provider, region="DE", timeout=20.0, token=os.getenv("DYNREACT_ENERGY_HTTP_TOKEN"), context=_runtime_context())
    if provider.startswith("http:") and not provider.startswith("http://"):
        return HttpEnergyBackend(provider[len("http:"):], region="DE", timeout=20.0, token=os.getenv("DYNREACT_ENERGY_HTTP_TOKEN"), context=_runtime_context())
    if provider.startswith("https:") and not provider.startswith("https://"):
        return HttpEnergyBackend(provider[len("https:"):], region="DE", timeout=20.0, token=os.getenv("DYNREACT_ENERGY_HTTP_TOKEN"), context=_runtime_context())
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
        fig.add_trace(go.Scatter(x=x_values + list(reversed(x_values)), y=y_high + list(reversed(y_low)), fill="toself", fillcolor="rgba(99,110,250,0.10)", line={"color": "rgba(0,0,0,0)"}, hoverinfo="skip", showlegend=False, legendgroup=equipment_name, name=f"{equipment_name} uncertainty"))
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
    file_path = provider_file_path(provider)
    if file_path is not None and os.path.isfile(file_path):
        with file_path.open("r", encoding="utf-8") as handle:
            context = normalize_energy_context(json.load(handle))
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
