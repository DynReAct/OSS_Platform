from datetime import timedelta, datetime
from typing import Sequence, Literal
from dynreact.app import state, config
import dash
from dash import html, dcc, callback, Output, Input, State
import plotly.graph_objects as go

from dynreact.auth.authentication import dash_authenticated
from dynreact.base.EnergyService import ServiceResultsFailed
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.gui.gui_utils import GuiUtils

energy_types: Sequence[Literal["electric", "heat"]] = state.energy_prediction_types()
translations_key = "ngy_prc"
_FORMAT = "%Y-%m-%dT%H:%M"
if len(energy_types) > 0:
    dash.register_page(__name__, path="/perfmodels/energy-price")


def layout(*args, **kwargs):
    energy_type = kwargs.get("type")
    if energy_type not in energy_types:
        energy_type = energy_types[0]
    start = (DatetimeUtils.parse_date(kwargs.get("start")) or DatetimeUtils.now()).astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    end = (DatetimeUtils.parse_date(kwargs.get("end")) or start + timedelta(days=2)).astimezone()

    return html.Div([
        html.H1("Energy prices", id=f"{translations_key}-title"),
        html.Div([
            html.Div([
                html.Span("Snapshot:"),
                GuiUtils.create_snapshots_selector_prev_next(translations_key),
                html.Span("Energy type"),
                dcc.Dropdown(id=f"{translations_key}-type", options=energy_types, value=energy_type, style={"min-width": "8em"}),
                #html.Span("Provider: "),
                #html.Span(id=f"{translations_key}-model-label"),
            ], className="ltp-settings-card", style={"display": "grid", "grid-template-columns": "repeat(2, auto)", "align-items": "center",
                                            "justify-content": "start", "row-gap": "1em", "column-gap": "1em", "padding": "1em", "margin-bottom": "1em"}),
            html.Div(id=f"{translations_key}-provider-info", className="ltp-settings-card", style={"display": "grid", "grid-template-columns": "repeat(2, auto)", "align-items": "center",
                                        "justify-content": "start", "row-gap": "0.5em", "column-gap": "1em", "padding": "1em"})
        ], style={"display": "flex", "flex-wrap": "wrap", "column-gap": "4em", "row-gap": "1em"}),
        html.Div(
            [
                html.Div([html.Label("From", htmlFor=f"{translations_key}-from", style={"fontWeight": "bold"}),
                          dcc.Input(id=f"{translations_key}-from", type="datetime-local", value=start.strftime(_FORMAT))],
                         style={"display": "flex", "flexDirection": "column", "gap": "0.35rem"}),
                html.Div([html.Label("Until", htmlFor=f"{translations_key}-until", style={"fontWeight": "bold"}),
                          dcc.Input(id=f"{translations_key}-until", type="datetime-local", value=end.strftime(_FORMAT))],
                         style={"display": "flex", "flexDirection": "column", "gap": "0.35rem"}),
                html.Div([html.Button("Start", id=f"{translations_key}-start", className="dynreact-button")],
                         style={"display": "flex", "alignItems": "end"}),
            ],
            style={"display": "flex", "gap": "1rem", "flexWrap": "wrap", "marginBottom": "1rem"},
        ),
        html.Div([
            dcc.Loading(
                [
                    dcc.Graph(id=f"{translations_key}-energy-price-graph", figure=_empty_figure()),
                ],
                delay_show=100,
            ),
        ]),
        dcc.ConfirmDialog(id=f"{translations_key}-validation-dialog"),
    ])


GuiUtils.create_snapshot_callbacks(translations_key)


@callback(
    #Output(f"{translations_key}-model-label", "children"),
    #Output(f"{translations_key}-model-label", "title"),
    #Output(f"{translations_key}-license-block", "hidden"),
    #Output(f"{translations_key}-attribution", "children"),
    #Output(f"{translations_key}-license", "children"),
    Output(f"{translations_key}-provider-info", "children"),
    Input(f"{translations_key}-type", "value"),
)
def type_changed(energy_type: Literal["electric", "heat"]|None):
    if not energy_type or not dash_authenticated(config):
        return []
    service = state.get_energy_cost_service(energy_type)
    if service is None:
        return []
    children = []
    meta = service.service()
    label = meta.label or meta.id
    description = meta.description
    children.append(html.Span("Provider"))
    children.append(html.Span(label, title=description))
    if meta.attribution:
        children.append(html.Span("Attribution"))
        children.append(html.Span(meta.attribution))
    if meta.license_info:
        license = meta.license_info
        if meta.license_details:
            license += " (" + meta.license_details + ")"
        children.append(html.Span("License"))
        children.append(html.Span(license))
    return children


@callback(
    Output(f"{translations_key}-validation-dialog", "displayed"),
    Output(f"{translations_key}-validation-dialog", "message"),
    Output(f"{translations_key}-energy-price-graph", "figure"),
    Input(f"{translations_key}-start", "n_clicks"),
    State(f"{translations_key}-type", "value"),
    State({"role": "snapshot-selector", "page": translations_key}, "data"),
    State(f"{translations_key}-from", "value"),
    State(f"{translations_key}-until", "value"),
    # prevent_initial_call=True,  # show immediately?
)
def update_graph(_: int, energy_type: Literal["electric", "heat"]|None, snapshot: str|None,
                 start_value: str | None, end_value: str | None) -> tuple[bool, str, go.Figure]:
    cost_service = state.get_energy_cost_service(energy_type)
    if cost_service is None:
        return True, "Cost service not found", dash.no_update
    start_time = DatetimeUtils.parse_date(start_value)
    end_time = DatetimeUtils.parse_date(end_value)
    local_tz = start_time.astimezone().tzinfo
    start_time = start_time.replace(tzinfo=local_tz)
    end_time = end_time.replace(tzinfo=local_tz)
    try:
        costs = cost_service.energy_costs(start_time, end_time)
        if isinstance(costs, ServiceResultsFailed):
            return True, f"Failed to determine energy costs: {costs.reason}, {costs.message}.", dash.no_update
        if len(costs.entries) == 0:
            return True, f"No price entries found", dash.no_update
    except Exception as e:
        return True, f"Internal error: {e}", dash.no_update
    fig = go.Figure()
    x_values = []
    y_values = []
    for entry in costs.entries:
        x_values.append(entry.validity[0])
        y_values.append(entry.costs_per_mwh)
    fig.add_trace(go.Scatter(x=x_values, y=y_values, mode="lines+markers", line={"color": "red", "shape": "hv"}, name=f"Energy costs"))
    fig.update_layout(
        template="plotly_white",
        height=568,
        title="Energy price",
        xaxis={"title": "Time", "range": [start_value, end_value]},
        yaxis={"title": f"Costs ({costs.cost_unit}/MWh)"},
        #yaxis2={"title": "Cumulative energy (kWh)", "overlaying": "y", "side": "right"},
        legend={"orientation": "h", "y": 1.02, "x": 0},
    )
    return False, "", fig


def _empty_figure() -> go.Figure:
    """Return the initial empty figure."""
    fig = go.Figure()
    fig.update_layout(template="plotly_white", height=650, title="Energy price", xaxis_title="Time", yaxis_title="Costs")
    return fig

