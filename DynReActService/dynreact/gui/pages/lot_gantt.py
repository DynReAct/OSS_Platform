import random
from datetime import timedelta
from typing import Sequence

import dash
from dash import html, clientside_callback, ClientsideFunction, Output, Input, State, dcc, callback
from pydantic import TypeAdapter

from dynreact.app import state
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import PlannedWorkingShift
from dynreact.gui.pages.components import lots_view


dash.register_page(__name__, path="/lots-gantt")
translations_key = "lots-gantt"
cnt = 0


def layout(*args, **kwargs):
    return html.Div([
        html.H1("Lots", id="lots-gantt-title"),
        lots_view("lots-gantt", initial_hidden=False),
        dcc.Store(id="lots-gantt-undefined", storage_type="memory"),
        dcc.Store(id="lots-gantt-undefined2", storage_type="memory"),
        dcc.Store(id="lots-gantt-shifts", storage_type="memory"),
        html.Br(),html.Br(),html.Br(),
    ])

@callback(
    Output("lots-gantt-undefined", "data"),
    Output("lots-gantt-undefined2", "data"),
    Output("lots-gantt-shifts", "data"),
    Input("selected-snapshot", "data"),
)
def _snapshot_updated(snap: str|None):
    global cnt
    snap = DatetimeUtils.parse_date(snap)
    if snap is None:
        return None, None, None
    cnt = cnt+1
    if cnt > 1e9:
        cnt = 1

    shifts_provider = state.get_shifts_provider()
    all_shifts = shifts_provider.load_all(snap, snap + timedelta(days=10), limit=1_000)
    all_shifts = {eq: [sh.model_dump(mode="json", exclude_unset=True, exclude_none=True) for sh in shifts] for eq, shifts in all_shifts.items()}
    return -cnt, None, all_shifts


clientside_callback(
    ClientsideFunction(
        namespace="createlots",
        function_name="showLotsSwimlane"
    ),
    Output("lots-gantt-lots-swimlane", "title"),
    Input("lots-gantt-undefined", "data"),
    Input("lots-gantt-shifts", "data"),
    Input("lots-gantt-lots-swimlane", "id"),
    Input("lots-gantt-undefined2", "data"),
    Input("lots-gantt-swimlane-mode", "value"),
)

clientside_callback(
    ClientsideFunction(
        namespace="createlots",
        function_name="setLotsSwimlaneMode"
    ),
    Output("lots-gantt-lotsview-header", "title"),
    Input("lots-gantt-swimlane-mode", "value"),
    State("lots-gantt-lots-swimlane", "id")
)
