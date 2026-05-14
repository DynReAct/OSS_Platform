from datetime import timedelta
from typing import Literal

import dash
from dash import html, dcc, callback, Output, Input, clientside_callback, ClientsideFunction, State

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import ProductionTargets

dash.register_page(__name__, path="/ltp/performance")
translations_key = "ltp-perf"


# TODO equipment filter
# TODO free start/end date selection
def layout(*args, **kwargs):
    processes = [{"value": proc.name_short, "label": proc.name or proc.name_short, "title": proc.description} for proc in state.get_site().processes]

    return html.Div([
        html.H1("Equipment performance", id="ltp-perf-title"),
        html.Div([
                html.Span("Time selection:"),
                dcc.RadioItems(options=[{"value": "today", "label": "Today"},{"value": "yesterday", "label": "Yesterday"}, {"value": "month", "label": "Current month"}, {"value": "other", "label": "Other"}],
                          value="yesterday", id="ltp-perf-interval-selection"),
                html.Span(),
                html.Span("Start/end:"),
                html.Div(),  # TODO
                html.Span(),
                html.Span("Process:"),
                dcc.Dropdown(id="ltp-perf-process", options=processes, value=processes[0]["value"], style={"width": "18em"}),
                html.Span(),
        ], className="ltp-perf-menu"),
        html.Br(),
        html.Div([
            html.Div([
                "Total production: ",
                html.Span(id="ltp-perf-total-out"),
                "t. By equipment: ",
            ]),
            html.Div(id="ltp-perf-equipment-widget", className="ltp-perf-equipments"),
            html.Br(),
            html.Span("By material structure: "),
            html.Br(),
            html.Div(id="ltp-perf-material-widget")
        ]),
        dcc.Store(id="ltp-perf-start-end", storage_type="memory"),
        dcc.Store(id="ltp-perf-material", storage_type="memory"),
        #dcc.Store(id="ltp-perf-total", storage_type="memory"),
        dcc.Store(id="ltp-perf-dummy-undefined", storage_type="memory"),
    ])

@callback(Output("ltp-perf-start-end", "data"),
          Input("ltp-perf-interval-selection", "value"),
          State("selected-snapshot", "data"))
def shift_duration_changed(interval: Literal["today", "yesterday", "month", "other"]|None, snapshot: str|None):
    if not dash_authenticated(config) or not interval or interval == "other":
        return None
    snapshot_obj = state.get_snapshot(time=DatetimeUtils.parse_date(snapshot))
    end = state.as_timezone(snapshot_obj.timestamp if snapshot_obj is not None else DatetimeUtils.now())
    start = end.replace(hour=0, minute=0, second=0, microsecond=0)
    if interval == "month":
        start = start.replace(day=1)
    elif interval == "yesterday":
        end = start
        start = start - timedelta(days=1)
    return [DatetimeUtils.format(start), DatetimeUtils.format(end)]


@callback(Output("ltp-perf-material", "data"),
          Output("ltp-perf-total-out", "children"),
          Output("ltp-perf-equipment-widget", "children"),
          Input("ltp-perf-start-end", "data"),
          Input("ltp-perf-process", "value"))
def start_end_changed(start_end: tuple[str, str]|None, process: str|None):
    if not start_end or not process or not dash_authenticated(config):
        return None, None, None
    start, end = [DatetimeUtils.parse_date(start_end[0]), DatetimeUtils.parse_date(start_end[1])]
    prod: ProductionTargets = state.get_history_reader().production_aggregate(process, start, end)
    total_weight = sum(t.total_weight for t in prod.target_weight.values()) if prod is not None else None
    if total_weight is not None:
        total_weight = f"{total_weight:.2f}"
    equipments = None
    if prod is not None:
        equipments = []
        equipments.append(html.Span("Equipment"))
        equipments.append(html.Span("Production / t"))
        equipments.append(html.Span())
        equip_objects = state.get_site().get_process_equipment(process)
        for eq in equip_objects:
            if eq.id in prod.target_weight:
                weight = prod.target_weight[eq.id].total_weight
                equipments.append(html.Span(eq.name or eq.name_short or str(eq.id)))
                equipments.append(html.Span(f"{weight:.2f}"))
                equipments.append(html.Span())
    if prod is None or not prod.material_weights or len(prod.material_weights) == 0:
        return None, total_weight, equipments
    material = {}
    for cat in state.get_site().material_categories:
        classes = {cl.id: {"name": cl.name or cl.id, "weight": prod.material_weights.get(cl.id, 0.)} for cl in cat.classes}
        material[cat.id] = {"name": cat.name or cat.id, "classes": classes}
    return material, total_weight, equipments


clientside_callback(
    ClientsideFunction(
        namespace="lots2",
        function_name="setBacklogStructureOverview"
    ),
    Output("ltp-perf-material-widget", "title"),
    Input("ltp-perf-material", "data"),
    Input("ltp-perf-dummy-undefined", "data"),
    State("ltp-perf-material-widget", "id"),
)

