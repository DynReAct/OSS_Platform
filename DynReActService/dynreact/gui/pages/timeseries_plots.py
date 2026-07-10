import types
import typing
from datetime import timedelta, datetime
from typing import Sequence, Any

import dash_ag_grid as dash_ag

import dash
import numpy as np
from dash import html, clientside_callback, ClientsideFunction, Output, Input, State, dcc, callback, ALL
import plotly.express as px
import plotly.graph_objects as go
from pydantic import BaseModel

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.ModelUtils import ModelUtils
from dynreact.base.model import Equipment, Site, LotTimes

dash.register_page(__name__, path="/lots/ts-plots")
translations_key = "ts-plots"
cnt = 0


def layout(*args, **kwargs):
    processes = state.get_site().processes
    process: str | None = kwargs.get("process")
    equipments = state.get_site().equipment if process is None or process == "" else state.get_site().get_process_equipment(process)
    equipment = _plants_for_ids(kwargs.get("equipment"), equipments) or equipments
    process = process or equipment[0].process
    return html.Div([
        html.H1("Timeseries plots", id=f"{translations_key}-title"),
        html.Div([
            html.Div([
                html.H2("Equipment", id=f"{translations_key}-eq-header"),
                html.Div([
                    html.Span("Snapshot"), html.Span(id=f"{translations_key}-snapshot"),
                    html.Span("Select process:", id=f"{translations_key}-proc-select-label"),
                    dcc.Dropdown(options=[{"value": p.name_short, "label": p.name_short} for p in processes],
                                 value=process, id=f"{translations_key}-proc-select", style={"min-width": "12em"}),
                    html.Span("Select equipment:", id=f"{translations_key}-eq-select-label"),
                    dcc.Dropdown(options=[{"value": e.id, "label": e.name_short} for e in state.get_site().get_process_equipment(process)], value=[e.id for e in equipment], multi=True,
                                 id=f"{translations_key}-eq-select", style={"min-width": "12em"}),
                    html.Span("Select end lots:", id=f"{translations_key}-endlot-select-label"),
                    html.Div(id=f"{translations_key}-endlots-section", className="grid-2 gap-1"),
                    html.Div("End time:", id=f"{translations_key}-endtime-label"),
                    html.Span(id=f"{translations_key}-endtime", style={"padding": "0.2em 0"}),
                    #html.Span("Select planning start:", id=f"{translations_key}-planning-start-label"),
                    #html.Div([
                    #    dcc.Input(type="date", id=f"{translations_key}-planning-start-date"),
                    #    dcc.Input(type="time", id=f"{translations_key}-planning-start-time"),
                    #], className="lot2-planning-start", style={"padding": "0.5em 0"})
                ], className="grid-2 gap-1"),
            ], className="settings-panel"),
            html.Div([
                html.H2("Data points", id=f"{translations_key}-data-header"),
                html.Div([
                    html.Span("Data points:", id=f"{translations_key}-data-select-label"),
                    dcc.Dropdown(options=[], multi=True, value=None, id=f"{translations_key}-data-select", style={"min-width": "12em"}),
                ], className="grid-2 gap-1"),
            ], className="settings-panel")
        ], style={"display": "flex", "column-gap": "4em", "flex-wrap": "wrap", "row-gap": "1em"}),
        html.H2("Plot", id=f"{translations_key}-plot-header"),
        dcc.Graph(id=f"{translations_key}-graph")
    ], id=translations_key)


@callback(Output("ts-plots-snapshot", "children"),
          Input("selected-snapshot", "data"))
def snapshot_changed(snapshot):
    return snapshot

@callback(Output("ts-plots-eq-select", "options"),
          Output("ts-plots-eq-select", "value"),
          Input("ts-plots-proc-select", "value"),
          State("ts-plots-eq-select", "value"))
def process_changed(proc: str|None, selected_plants: Sequence[int]|None):
    if proc is None or not dash_authenticated(config):
        return [], None
    equipment = state.get_site().get_process_equipment(proc)
    options = [{"value": eq.id, "label": eq.name_short} for eq in equipment]
    selected = [e.id for e in equipment if e.id in selected_plants] if selected_plants is not None else []
    if len(selected) == 0:
        selected = [equipment[0].id]
    return options, selected


@callback(Output("ts-plots-endlots-section", "children"),
          Input("ts-plots-eq-select", "value"),
          State("selected-snapshot", "data"),
          State({"role": "lot-select", "equipment": ALL}, "value"),)
def set_lot_selection(equipment: Sequence[int]|None, snapshot: str|None, previous_end_lots: Sequence[str|None]|None):
    snapshot = DatetimeUtils.parse_date(snapshot)
    if not dash_authenticated(config) or not snapshot or not equipment or len(equipment) == 0:
        return [], None
    snap_obj = state.get_snapshot(time=snapshot)
    children = []
    site = state.get_site()
    previous_end_lots = previous_end_lots or []
    for eq in equipment:
        eq_obj = site.get_equipment(eq, do_raise=True)
        children.append(html.Span(f"{eq_obj.name_short or eq_obj.id}"))
        lots = snap_obj.lots.get(eq)
        lots = [lot for lot in lots if lot.active and lot.end_time is not None] if lots else []
        lots.sort(key=lambda lot: lot.end_time)
        lot_ids = [lot.id for lot in lots]
        options = [{"value": lot.id, "label": lot.id} for lot in lots]
        value = next((lot for lot in previous_end_lots if lot in lot_ids), None) or (lot_ids[-1] if len(lot_ids) > 0 else None)
        drop = dcc.Dropdown(options=options, value=value, id={"role": "lot-select", "equipment": eq}, style={"min-width": "10em"})
        children.append(drop)
    return children


@callback(Output("ts-plots-endtime", "children"),
          Input({"role": "lot-select", "equipment": ALL}, "value"),
          State("selected-snapshot", "data"))
def lot_changed(selected_lots: Sequence[str|None]|None, snapshot: str|None):
    snapshot = DatetimeUtils.parse_date(snapshot)
    if not dash_authenticated(config) or not snapshot or not selected_lots:
        return None
    snap_obj = state.get_snapshot(time=snapshot)
    selected_lots = [lt for lt in selected_lots if lt]
    all_lots = [lot for lots in snap_obj.lots.values() for lot in lots if lot.id in selected_lots and lot.end_time is not None]
    max_time = state.as_timezone(max(lot.end_time for lot in all_lots) if len(all_lots) > 0 else snap_obj.timestamp)
    return DatetimeUtils.format(max_time, use_zone=False).replace("T", " ")

@callback(Output("ts-plots-data-select", "options"),
          Output("ts-plots-data-select", "value"),
          Input("ts-plots-eq-select", "value"),
          State("ts-plots-data-select", "value"),
          State("selected-snapshot", "data"))
def equipment_changed(equipment: Sequence[int]|None, previous_selected: Sequence[str]|None, snapshot: str|None):
    if not dash_authenticated(config):
        return [], None
    site = state.get_site()
    relevant_fields = state.get_cost_provider().relevant_fields(site.get_equipment(equipment[0], do_raise=True)) if equipment and len(equipment) > 0 else None
    snap_obj = state.get_snapshot(time=DatetimeUtils.parse_date(snapshot))
    mat_props = snap_obj.orders[0].material_properties
    options = []
    if isinstance(mat_props, BaseModel):
        _none_type = type(None)

        def _is_numeric(tp: type | None):
            if tp == float or tp == int:
                return True
            if tp == str or tp == bool or tp == _none_type:
                return False
            if isinstance(tp, types.UnionType):
                args: tuple[Any, ...] = typing.get_args(tp)
                return float in args or int in args
            return False

        for field, field_info in mat_props.model_fields.items():
            if _is_numeric(field_info.annotation):
                options.append({"value": field, "label": field})
        if relevant_fields is not None:

            def field_sort_id(f: dict[str, Any]) -> int:
                _id = f.get("value")
                is_material_prop = False
                if _id not in relevant_fields:
                    mat_id = "material_properties." + _id
                    is_material_prop = mat_id in relevant_fields
                field_id = mat_id if is_material_prop else _id
                if field_id in relevant_fields:
                    return relevant_fields.index(field_id)
                return len(relevant_fields)
            options.sort(key=field_sort_id)
        selected = None
        if previous_selected is not None:
            selected = [ps for ps in previous_selected if any(o["value"] == ps for o in options)]
            if len(selected) == len(previous_selected):
                selected = dash.no_update
        if (not selected or (isinstance(selected, Sequence) and len(selected) == 0)) and len(options) > 0:
            selected = [options[0]["value"]]
        return options, selected


@callback(Output("ts-plots-graph", "figure"),
          Input("ts-plots-eq-select", "value"),
          Input("ts-plots-data-select", "value"),
          Input({"role": "lot-select", "equipment": ALL}, "value"),
          State("selected-snapshot", "data"),
          State("ts-plots-proc-select", "value"),
          State("lang", "data"),)
def data_changed(equipments: Sequence[int]|None, data: Sequence[str]|None, end_lots: Sequence[str|None]|None, snapshot: str|None, process: str|None, lang: str|None):
    snapshot = DatetimeUtils.parse_date(snapshot)
    fig = go.Figure()
    if not dash_authenticated(config) or not snapshot or not process or not equipments:
        return fig
    snap_obj = state.get_snapshot(time=snapshot)
    snap_provider = state.get_snapshot_provider()
    site = state.get_site()
    is_de = lang and lang.startswith("de")
    lt_label = "Los" if is_de else "Lot"
    order_label = "Auftrag" if is_de else "order"
    time_label = "Zeit" if is_de else "time"
    is_single_equipment = len(equipments) < 2
    is_single_datapoint = len(data) < 2
    colors = ["red", "blue", "green", "orange"]
    num_colors = len(colors)
    trace_cnt = 0
    equipment_objects = {e: site.get_equipment(e, do_raise=True) for e in equipments}
    for data_point in data:
        for eq_idx, equipment in enumerate(equipments):
            eq_obj = equipment_objects[equipment]
            lots = snap_obj.lots.get(equipment)
            lots = [lot for lot in lots if lot.active and lot.end_time is not None] if lots else []
            if len(lots) == 0:
                continue
            lots.sort(key=lambda lot: lot.end_time)
            if end_lots is not None:
                end_lot = end_lots[eq_idx] if eq_idx < len(end_lots) else None
                end_lot_idx = next((idx for idx, lot in enumerate(lots) if lot.id == end_lot), None)
                if end_lot_idx is None:
                    continue
                lots = lots[:end_lot_idx+1]
            orders = [order for lot in lots for order in lot.orders]
            order_lot_times: dict[str, dict[str, LotTimes]]|None = ModelUtils.get_order_lot_times_with_fallback(site, snap_provider, snapshot=snap_obj.timestamp, order=orders, process=process)
            xs = []
            ys = []
            custom_orders = []
            if order_lot_times is not None:
                for order in orders:
                    if order not in order_lot_times or process not in order_lot_times[order]:
                        continue
                    order_obj = snap_obj.get_order(order)
                    if not order_obj:
                        continue
                    props = order_obj.material_properties
                    value = getattr(props, data_point) if hasattr(props, data_point) else None
                    if value is None or (isinstance(value, float) and np.isnan(value)):
                        continue
                    times = order_lot_times[order][process]
                    xs.append(times.start)
                    xs.append(times.end)
                    ys.append(value)
                    ys.append(value)
                    lt = order_obj.lots.get(process) if order_obj.lots is not None else None
                    custom_orders.append((order, lt))
                    custom_orders.append((order, lt))
            else:
                raise NotImplementedError("If order lot times are missing, we cannot yet draw the line...")
            if len(xs) == 0:
                continue
            if is_single_equipment or is_single_datapoint:
                color = colors[trace_cnt % num_colors]
            else:
                color = colors[eq_idx % num_colors]
            trace_cnt += 1
            equipment_name = eq_obj.name_short or str(eq_obj.id)
            new_line = go.Scatter(x=xs, y=ys, customdata=custom_orders, mode="lines+markers", line={"color": color, "width": 2}, marker={"size": 7}, name=f"{equipment_name}: {data_point}", legendgroup=equipment_name,
                                  hovertemplate=f"{lt_label}: %{{customdata[1]}}, {order_label}: %{{customdata[0]}}, {data_point}: %{{y:,.2f}}, {time_label}: %{{x}}<extra></extra>")
            fig.add_trace(new_line)
    data_label = ", ".join(data)
    if is_single_equipment:
        e = equipment_objects[equipments[0]]
        title = f"{e.name_short or e.id}: {data_label}"
    else:
        title = f"{process}: {data_label}"
    fig_layout = {"title": title, "font": {"size": 16}}
    if len(data_label) < 20:
        fig_layout["yaxis"] = {"title": data_label}
    fig.update_layout(fig_layout)
    return fig


def _plants_for_ids(equipment: str|None, site: Site) -> list[Equipment]|None:
    if not equipment:
        return None
    plant_ids = [p for p in (p.strip() for p in equipment.split(",")) if p != ""]
    return [_plant_for_id(site.equipment, p) for p in plant_ids]

def _plant_for_id(plants: list[Equipment], plant_id0: str) -> Equipment:
    plant = next((p for p in plants if str(p.id) == plant_id0), None)
    if plant is not None:
        return plant
    plant_id = plant_id0.upper()
    plant = next((p for p in plants if (p.name_short is not None and p.name_short.upper() == plant_id) or (p.name is not None and p.name.upper() == plant_id)), None)
    if plant is None:
        raise Exception(f"Plant not found: {plant_id0}")
    return plant

