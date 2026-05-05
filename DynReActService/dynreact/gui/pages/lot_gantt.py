import random

import dash
from dash import html, clientside_callback, ClientsideFunction, Output, Input, State, dcc, callback

from dynreact.gui.pages.components import lots_view


dash.register_page(__name__, path="/lots-gantt")
translations_key = "lots-gantt"
cnt = 0


def layout(*args, **kwargs):
    return html.Div([
        html.H1("Lots", id="lots-gantt-title"),
        lots_view("lots-gantt", initial_hidden=False),
        dcc.Store(id="lots-gantt-undefined"),
        dcc.Store(id="lots-gantt-undefined2"),
    ])

@callback(
    Output("lots-gantt-undefined", "data"),
    Output("lots-gantt-undefined2", "data"),
    Input("selected-snapshot", "data"),
)
def _snapshot_updated(snap: str|None):
    global cnt
    cnt = cnt+1
    if cnt > 1e9:
        cnt = 1
    return -cnt, None


clientside_callback(
    ClientsideFunction(
        namespace="createlots",
        function_name="showLotsSwimlane"
    ),
    Output("lots-gantt-lots-swimlane", "title"),
    Input("lots-gantt-undefined", "data"),
    Input("lots-gantt-lots-swimlane", "id"),
    Input("lots-gantt-undefined2", "data"),
    Input("lots-gantt-swimlane-mode", "value")
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
