import logging
from datetime import datetime, timedelta
from typing import Sequence, Literal, Any

from dynreact.app import state, config
import dash
from dash import html, dcc, callback, Output, Input, State
import dash_ag_grid as dash_ag
import plotly.graph_objects as go

from dynreact.auth.authentication import dash_authenticated
from dynreact.base.EnergyService import EnergyPrediction, EnergyPredictionResultsFailed
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.ModelUtils import ModelUtils
from dynreact.base.model import Lot, Order, LotTimes, Site, Material
from dynreact.gui.gui_utils import GuiUtils

energy_types: Sequence[Literal["electric", "heat"]] = state.energy_prediction_types()
translations_key = "ngy2"
if len(energy_types) > 0:
    dash.register_page(__name__, path="/perfmodels/energy2")

_table_cols = [
        {"field": "equipment_name", "pinned": True},
        #{"field": "coil_id", "headerName": "Coil", "pinned": True},
        {"field": "order_id", "headerName": "Order", "pinned": True},
        {"field": "units", "headerName": "Units", "headerTooltip": "Number of material units belonging to this order"},
        {"field": "lot_id", "headerName": "Lot"},
        {"field": "start_time", "headerName": "Start", "filter": "agDateColumnFilter", "width": 250},
        {"field": "end_time", "headerName": "End", "filter": "agDateColumnFilter", "width": 250},
        {"field": "duration_min", "headerName": "Duration (min)", "filter": "agNumberColumnFilter"},
        {"field": "power_kw", "headerName": "Power (kW)", "filter": "agNumberColumnFilter", "valueFormatter": {"function": "formatCell(params.value, 4)"}},
        {"field": "energy_kwh", "headerName": "Ensemble energy (kWh)", "filter": "agNumberColumnFilter", "valueFormatter": {"function": "formatCell(params.value, 4)"}},
        {"field": "uncertainty_min_kwh", "headerName": "Uncertainty min (kWh)", "filter": "agNumberColumnFilter"},
        {"field": "uncertainty_max_kwh", "headerName": "Uncertainty max (kWh)", "filter": "agNumberColumnFilter"},
        {"field": "energy_cost_eur", "headerName": "Cost (EUR)", "filter": "agNumberColumnFilter"},
        {"field": "unit_price_eur_mwh", "headerName": "Unit price (EUR/MWh)", "filter": "agNumberColumnFilter"},
        {"field": "source", "headerName": "Source"},
    ]

def layout(*args, **kwargs):
    energy_type = kwargs.get("type")
    if energy_type not in energy_types:
        energy_type = energy_types[0]
    equipment = kwargs.get("equipment")
    if equipment is not None:
        equipment = tuple([int(e) for e in equipment] if isinstance(equipment, Sequence) else [int(equipment)])
    return html.Div([
        html.H1("Energy prediction", id="ngy2-title"),
        html.Div([
            html.Span("Energy type"),
            dcc.Dropdown(id="ngy2-type", options=energy_types, value=energy_type, style={"min-width": "8em"}),
            html.Span("Provider: "),
            html.Span(id="ngy2-model-label"),
            html.Span("Snapshot:"),
            GuiUtils.create_snapshots_selector_prev_next(translations_key),
        ], style={"display": "grid", "grid-template-columns": "repeat(4, auto)", "align-items": "center",
                                        "justify-content": "start", "row-gap": "1em", "column-gap": "1em", "padding-bottom": "1em"}),
        # ======= Models table ==============
        html.Div([html.Div("Supported equipment", style={"fontWeight": "bold", "marginBottom": "0.5rem"}),
                  dcc.Checklist(id="ngy2-equipment-checklist", value=[],
                                inline=True, inputStyle={"marginRight": "0.35rem", "marginLeft": "0.75rem"})],
                 style={"marginBottom": "1rem"}),
        html.Div(
            [
                html.Div([html.Label("From", htmlFor="ngy2-perf-energy-from", style={"fontWeight": "bold"}),
                          dcc.Input(id="ngy2-perf-energy-from", type="datetime-local")],
                         style={"display": "flex", "flexDirection": "column", "gap": "0.35rem"}),
                html.Div([html.Label("Until", htmlFor="ngy2-perf-energy-until", style={"fontWeight": "bold"}),
                          dcc.Input(id="ngy2-perf-energy-until", type="datetime-local")],
                         style={"display": "flex", "flexDirection": "column", "gap": "0.35rem"}),
                html.Div([html.Button("Start", id="ngy2-perf-energy-start", className="dynreact-button")],
                         style={"display": "flex", "alignItems": "end"}),
            ],
            style={"display": "flex", "gap": "1rem", "flexWrap": "wrap", "marginBottom": "1rem"},
        ),
        html.Div("Waiting for input.", id="ngy2-perf-energy-status", style={"marginBottom": "1rem"}),
        html.Div("Total price: 0.00 EUR", id="ngy2-perf-energy-total-price",
                 style={"fontWeight": "bold", "marginBottom": "1rem"}),
        dcc.Loading(
            [
                dash_ag.AgGrid(id="ngy2-perf-energy-table", columnDefs=_table_cols, rowData=[],
                               className="ag-theme-alpine",
                               defaultColDef={"sortable": True, "filter": True, "resizable": True},
                               style={"height": "340px", "width": "100%", "marginBottom": "1rem"},
                               columnSize="responsiveSizeToFit"),
                dcc.Graph(id="ngy2-perf-energy-graph", figure=_empty_figure()),
            ],
            delay_show=100,
        ),
        dcc.ConfirmDialog(id="ngy2-perf-energy-validation-dialog"),
        dcc.Store(id="ngy2-lots-included", storage_type="memory"),   # lot_ids: list[str]
        dcc.Store(id="ngy2-initial-equipments", storage_type="memory", data=equipment)
    ], id=translations_key)


GuiUtils.create_snapshot_callbacks(translations_key)


@callback(
    Output("ngy2-lots-included", "data"),
    Output("ngy2-perf-energy-from", "value"),
    Output("ngy2-perf-energy-until", "value"),
    Input({"role": "snapshot-selector", "page": translations_key}, "data"),
    Input("ngy2-equipment-checklist", "value"),
)
def snapshot_changed(snapshot: str|None, active_equipment: Sequence[int]):
    snap = DatetimeUtils.parse_date(snapshot)
    if snap is None or not dash_authenticated(config):
        return None, None, None
    start = snap
    snap_obj = state.get_snapshot(snap)
    lots_included = [lot for eq, lots in snap_obj.lots.items() if eq in active_equipment for lot in lots if lot.active and lot.end_time is not None]
    end_times = [lot.end_time for lot in lots_included]
    lot_ids = [lot.id for lot in lots_included]
    end = max(end_times) if len(end_times) > 0 else snap
    return lot_ids, DatetimeUtils.format(state.as_timezone(start), use_zone=False), DatetimeUtils.format(state.as_timezone(end), use_zone=False)


@callback(
    Output("ngy2-model-label", "children"),
    Output("ngy2-model-label", "title"),
    Output("ngy2-equipment-checklist", "options"),
    Output("ngy2-equipment-checklist", "value"),
    Input("ngy2-type", "value"),
    State("ngy2-equipment-checklist", "value"),
    State("ngy2-initial-equipments", "data")
)
def type_changed(energy_type: Literal["electric", "heat"]|None, previous_equipments: list[int] | None, initial_equipment: Sequence[int]|None):
    if not energy_type or not dash_authenticated(config):
        return None, None, None, None
    service = state.get_energy_service(energy_type)
    if service is None:
        return None, None, None, None
    meta = service.service()
    label = meta.label or meta.id
    description = meta.description
    site = state.get_site()
    equipments = [e for e in site.equipment if meta.equipment is None or e.id in meta.equipment]
    equipment_options = [{"value": e.id, "label": e.name_short or str(e.id), "title": f"Id: {e.id}"} for e in equipments]
    if previous_equipments is not None and len(previous_equipments) > 0:
        value = previous_equipments
    elif initial_equipment is not None:
        value = initial_equipment
    else:
        value = [e.id for e in equipments]
    return label, description, equipment_options, value


@callback(
    Output("ngy2-perf-energy-validation-dialog", "displayed"),
    Output("ngy2-perf-energy-validation-dialog", "message"),
    Output("ngy2-perf-energy-status", "children"),
    Output("ngy2-perf-energy-table", "rowData"),
    Output("ngy2-perf-energy-graph", "figure"),
    Input("ngy2-perf-energy-start", "n_clicks"),
    State("ngy2-type", "value"),
    State({"role": "snapshot-selector", "page": translations_key}, "data"),
    State("ngy2-lots-included", "data"),
    State("ngy2-perf-energy-from", "value"),
    State("ngy2-perf-energy-until", "value"),
    prevent_initial_call=True,
)
def run_energy_analysis(_: int, energy_type: Literal["electric", "heat"]|None, snapshot: str|None, lots_included: Sequence[str]|None,
                        start_value: str | None, end_value: str | None) -> tuple[bool, str, str, list[dict[str, Any]], go.Figure]:
    snap = DatetimeUtils.parse_date(snapshot)
    if not snap or not energy_type or not lots_included or len(lots_included) == 0:
        return True, "Selection empty", "Waiting for valid input.", dash.no_update, dash.no_update
    snap_obj = state.get_snapshot(snap)
    start_time = state.as_timezone(DatetimeUtils.parse_date(start_value))
    end_time = state.as_timezone(DatetimeUtils.parse_date(end_value))
    if end_time <= start_time:
        return True, "The 'Until' timestamp must be later than the 'From' timestamp.", "Waiting for valid input.", dash.no_update, dash.no_update
    equipment_with_lots: dict[int, list[Lot]] = {eq: lots for eq, lots in {eq: [lot for lot in lots if lot.id in lots_included and lot.start_time < end_time and lot.end_time > start_time]
                                                                for eq, lots in snap_obj.lots.items()}.items() if len(lots) > 0}
    if len(equipment_with_lots) == 0 or not start_value or not end_value:
        return True, "Please select at least one equipment and both time bounds before starting the analysis.", "Waiting for valid input.", dash.no_update, dash.no_update
    equipment_with_lots = {eq: sorted(lots, key=lambda lot: lot.end_time) for eq, lots in equipment_with_lots.items()} # sort lots by end time, for each equipment
    equipment_with_lots = dict(sorted(equipment_with_lots.items()))  # sort by equipments
    equipment_with_orders: dict[int, list[Order]] = {eq: [snap_obj.get_order(order, do_raise=True) for lot in lots for order in lot.orders] for eq, lots in equipment_with_lots.items()}
    energy_service = state.get_energy_service(energy_type)
    mat_based: bool = energy_service.service().material_based
    success = 0
    last_error = None
    results: dict[int, Sequence[EnergyPrediction]] = {}
    rows_by_equipment: dict[int, list[dict[str, Any]]] = {}
    sp = state.get_snapshot_provider()
    site = state.get_site()
    for equipment, orders in equipment_with_orders.items():
        try:
            order_ids = [o.id for o in orders]
            materials: dict[str, list[Material]]|None = None
            mat_ids: list[str]|None = None
            if mat_based:
                processes = state.get_site().processes
                materials = {}
                mat_ids = []
                for mat in snap_obj.material:
                    if mat.order in order_ids:
                        if mat.order not in materials:
                            materials[mat.order] = []
                        materials[mat.order].append(mat)
                        mat_ids.append(mat.id)
                for mats in materials.values():
                    mat_processes = {mat.id: next((p for p in processes if mat.current_process in p.process_ids), None) for mat in mats}
                    process_indices = {mat_id: processes.index(p) if p is not None else 1_000_000 for mat_id, p in mat_processes.items()}
                    order_indices = {mat.id: mat.order_positions.get(p.name_short, 1_000) if p is not None and mat.order_positions is not None else 0 for mat, p in zip(mats, mat_processes)}
                    mats.sort(key=lambda mat: (process_indices[mat.id], order_indices[mat.id]))  # sort by process ids and order indices
            process = site.get_equipment(equipment, do_raise=True).process
            lot_times = ModelUtils.get_order_lot_times_with_fallback(site, sp, snapshot=snap_obj.timestamp, order=order_ids, process=process) if not mat_based \
                    else ModelUtils.get_material_lot_times_with_fallback(site, sp, snapshot=snap_obj.timestamp, material=mat_ids, process=process)
            order_lot_times: dict[str, LotTimes] = {o: dct[process] for o, dct in lot_times.items() if process in dct}
            #order_lot_times_sorted = [order_lot_times.get(o) if order_lot_times is not None else None for o in order_ids]
            start_times: list[datetime] = []
            end_times: list[datetime] = []
            latest_end = snap_obj.timestamp
            if mat_based:
                empty = tuple()
                entries = [(o, mat) for o in orders for mat in materials.get(o.id, empty)]
            else:
                entries = [(o, None) for o in orders]
            for order, mat in entries:
                key = order.id if not mat_based else mat.id
                start = order_lot_times[key].start if key in order_lot_times else latest_end
                start_times.append(start)
                end = order_lot_times[key].end if key in order_lot_times else start + timedelta(hours=order.material_count if not mat_based else 1)
                end_times.append(end)
                latest_end = end
            res = energy_service.bulk_energy_consumption(orders, equipment, material=materials, missing_value_ensemble=snap_obj.orders)
            if isinstance(res, EnergyPredictionResultsFailed):
                msg = f"Model application failed: {res.reason}: {res.message}"
                if res.details:
                    msg += f" ({res.details})"
                last_error = Exception(msg)
                continue
            results_eq: Sequence[EnergyPrediction] = res.results
            results[equipment] = results_eq

            # "ensemble_energy_kwh": round(float(ensemble_energy), 3),
            #             "uncertainty_min_kwh": round(min(numeric_predictions), 3) if numeric_predictions else None,
            #             "uncertainty_max_kwh": round(max(numeric_predictions), 3) if numeric_predictions else None,
            #             "energy_cost_eur": round(float(cost_result.get("total_cost_eur", 0.0)), 4),
            #             "unit_price_eur_mwh"
            eq = site.get_equipment(equipment, do_raise=True)
            equipment_name = eq.name or eq.name_short or str(eq.id)
            durations = [end_times[idx] - start_times[idx] for idx in range(len(start_times))]
            rows = [{"equipment": equipment, "equipment_name": equipment_name, "order_id": entries[idx][0].id,
                          "lot_id": entries[idx][0].lots.get(process) if entries[idx][0].lots is not None else None,
                          "units": entries[idx][0].material_count if not mat_based else 1,
                          "start_time": DatetimeUtils.format(start_times[idx], use_zone=False).replace("T", " "),
                          "end_time":  DatetimeUtils.format(end_times[idx], use_zone=False).replace("T", " "),
                          "duration_min": round(durations[idx].total_seconds()/60),
                          "power_kw": p.predicted_energy/durations[idx].total_seconds()*3_600,
                          "energy_kwh": p.predicted_energy} for idx, p in enumerate(results_eq)]
            rows_by_equipment[equipment] = rows
            #rows, status = _backend.analyse(equipment_ids, start_time, end_time)
            success += 1
        except Exception as exc:
            logging.getLogger(__name__).exception(exc)
            last_error = exc
    if success == 0 and last_error:
        return True, str(last_error), f"Analysis failed: {last_error}", [], _empty_figure()
    return False, "", "", [row for rows in rows_by_equipment.values() for row in rows], _build_figure(site, rows_by_equipment, start_time, end_time)


def _build_figure(site: Site, rows_by_equipment: dict[int, list[dict[str, Any]]], start_value: datetime, end_value: datetime) -> go.Figure:
    """Create the final figure."""
    if len(rows_by_equipment) == 0:
        return _empty_figure()
    fig = go.Figure()
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#17becf", "#8c564b"]
    color_by_equipment: dict[int, str] = {eq: colors[idx % len(colors)] for idx, eq in enumerate(rows_by_equipment.keys())}
    for equipment, equipment_rows in rows_by_equipment.items():
        eq = site.get_equipment(equipment, do_raise=True)
        equipment_name = eq.name or eq.name_short or str(eq.id)
        color = color_by_equipment[equipment]
        x_values = [row["start_time"] for row in equipment_rows]
        y_values = [row["energy_kwh"] for row in equipment_rows]
        #y_low = [row["uncertainty_min_kwh"] for row in equipment_rows]
        #y_high = [row["uncertainty_max_kwh"] for row in equipment_rows]
        cum_energy = []
        #cum_cost = []
        running_energy = 0.0
        #running_cost = 0.0
        for row in equipment_rows:
            running_energy += float(row["energy_kwh"] or 0.0)
            #running_cost += float(row["energy_cost_eur"] or 0.0)
            cum_energy.append(running_energy)
            #cum_cost.append(running_cost)
        # TODO
        #fig.add_trace(go.Scatter(x=x_values + list(reversed(x_values)), y=y_high + list(reversed(y_low)), fill="toself", fillcolor=f"rgba(99,110,250,0.15)", line={"color": "rgba(0,0,0,0)"}, hoverinfo="skip", name=f"{equipment_name} uncertainty"))
        fig.add_trace(go.Scatter(x=x_values, y=y_values, mode="lines+markers", line={"color": color}, name=f"{equipment_name} ensemble"))
        fig.add_trace(go.Scatter(x=x_values, y=cum_energy, mode="lines", line={"color": color, "dash": "dash"}, name=f"{equipment_name} cumulative energy", yaxis="y2"))
        #fig.add_trace(go.Scatter(x=x_values, y=cum_cost, mode="lines", line={"color": color, "dash": "dot"}, name=f"{equipment_name} cumulative cost", yaxis="y3"))
    fig.update_layout(
        template="plotly_white",
        height=720,
        xaxis={"title": "Time", "range": [start_value, end_value]},
        yaxis={"title": "Energy per coil (kWh)"},
        yaxis2={"title": "Cumulative energy (kWh)", "overlaying": "y", "side": "right"},
        #yaxis3={"title": "Cumulative cost (EUR)", "anchor": "free", "overlaying": "y", "side": "right", "position": 0.96},
        legend={"orientation": "h", "y": 1.02, "x": 0},
    )
    return fig


def _empty_figure() -> go.Figure:
    """Return the initial empty figure."""
    fig = go.Figure()
    fig.update_layout(template="plotly_white", height=650, title="Energy estimation results", xaxis_title="Time", yaxis_title="Energy per coil (kWh)")
    return fig

