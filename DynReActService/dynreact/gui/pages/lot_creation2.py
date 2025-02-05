import threading
import traceback
from datetime import datetime, timedelta, date
from typing import Literal, Any

import dash
import pandas as pd
from dash import html, callback, Input, Output, dcc, State, no_update, clientside_callback, ClientsideFunction
import plotly.express as px
import dash_ag_grid as dash_ag
from dash.development.base_component import Component
from pydantic import BaseModel

from dynreact.base.LotsOptimizer import LotsOptimizer, LotsOptimizationAlgo, LotsOptimizationState
from dynreact.base.PlantPerformanceModel import PlantPerformanceModel
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.SnapshotProvider import OrderInitMethod
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.ModelUtils import ModelUtils
from dynreact.base.model import Equipment, Order, Lot, ProductionPlanning, ProductionTargets, EquipmentProduction, \
    MidTermTargets, ObjectiveFunction
from pydantic.fields import FieldInfo

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.gui.gui_utils import GuiUtils
from dynreact.gui.pages.components import prepare_lots_for_lot_view, lots_view
from dynreact.gui.pages.optimization_listener import FrontendOptimizationListener


dash.register_page(__name__, path="/lots/create2")
translations_key = "lots2"

lot_creation_thread_name = "lot-creation"
lot_creation_thread: threading.Thread|None = None
lot_creation_listener: FrontendOptimizationListener|None = None

# TODO proper handling of start lots/orders
# TODO option to record optimizaiton history including lots information and possibility to replay/step to specific optimization steps
# TODO option to initialize optimization from existing result
# TODO swimlane visualization
# TODO backlog lots operations: highlight if lots are active or not, show comment maybe?
# TODO init method existing solution
# TODO: use LongTermPlanning and MidTermPlanning classes for targets
def layout(*args, **kwargs):
    process: str|None = kwargs.get("process")  # TODO use store from main layout instead?
    iterations: int = int(kwargs.get("iterations", 10))
    horizon: int = int(kwargs.get("horizon", 24))  # planning horizon in hours
    init_method: Literal["heuristic", "duedate"] = kwargs.get("init")
    if init_method is None:
        init_method = "heuristic"
    tab: Literal["targets", "orders", "settings"] = kwargs.get("tab")
    if tab is None:
        tab = "targets"
    #horizon: int = int(kwargs.get("horizon", 24))  # planning horizon in hours # required at all?
    site = state.get_site()
    layout = html.Div([
        html.H1("Lot creation", id="lots2-title"),
        # ======= Top row: snapshot and process selector =========
        html.Div([
            html.Div([html.Div("Snapshot: "), html.Div(id="lots2-current_snapshot")]),
            html.Div([html.Div("Process: "), dcc.Dropdown(id="lots2-process-selector",
                        options=[{"value": p.name_short, "label": p.name_short,
                                  "title": p.name if p.name is not None else p.name_short} for p in site.processes],
                        value=process,
                        className="lots2-process-selector", persistence=True)]),
            # TODO display here the state of the optimization for the selected process
            # has it been run yet, which settings, etc.?
            # html.Div([html.Div("Results: "), html.Div(id="create_result")]),
            html.Div([
                html.Progress(),
                html.Div("Optimization running")
            ], id="lots2-running-indicator", hidden=True),
            html.Div([
                dcc.Link(html.Button("View solutions", className="dynreact-button"), id="lots2-link-solutions", href="/dash/lots/planned", target="_blank")
            ], id="lots2-link-solutions-wrapper", hidden=True),
        ], className="lots2-selector-flex"),
        html.Div([
            # ===== Settings tabs =========
            html.Div([
                html.Div([
                    html.Button("Targets", id="lots2-tabbutton-targets", className="lots2-tab-button", title="Specify the production targets per plant"),
                    html.Button("Orders", id="lots2-tabbutton-orders", className="lots2-tab-button",title="Fill the order backlog"),
                    html.Button("Optimization", id="lots2-tabbutton-settings", className="lots2-tab-button",
                                title="Select the optimization settings, such as initialization method and number of iteration, and start the optimization"),
                    html.Div()
                ], className="lots-settings-header"),
                html.Div([
                    html.Div(targets_tab(horizon), id="lots2-tab-targets", hidden=True),
                    html.Div(orders_tab(), id="lots2-tab-orders", hidden=True),
                    html.Div(settings_tab(init_method, iterations), id="lots2-tab-settings", hidden=True),
                ], className="lots-settings-body"),
                html.Div([
                    html.Button("Back", id="lots2-tabsnav-prev", className="dynreact-button dynreact-button-small", title="Previous tab"),
                    html.Button("Next", id="lots2-tabsnav-next", className="dynreact-button dynreact-button-small", title="Next tab"),
                ], className="lots-settings-nav")
            ], id="lots2-settings-tabs", className="lots2-settings-tabs", hidden=True),  # hidden iff snapshot or process are unselected

            # For some reason this graph does not work when embedded into something else...
            #html.Div([
            #    html.H3("Objectives"),
                html.Div(
                    dcc.Graph(id="lots2-creation-objectives", config={"displayModeBar": False}, style={"height": 300}),
                    className="lots2-creation-graph", id="lots2-creation-graph")
            #    ])
        ], className="lots2-control-row"),
        lots_view("lots2", *args, **kwargs),
        ltp_dialog(),
        # ========= Stores ================
        dcc.Store(id="lots2-active-tab", data=tab),  # Literal["targets", "orders", "settings"]
        dcc.Store(id="lots2-iterations", data=str(iterations)),  # Literal["targets", "orders", "settings"]
        dcc.Store(id="lots2-orders-data"),  # a dict with keys "snapshot", "process", "orders_selected_cnt", "orders_selected_weight"
        dcc.Store(id="lots2-lots-data"),    # rowData, list of dicts, one row per lot; input for swim lane
        dcc.Store(id="lots2-objectives-history"),     # optimization results, objective function
        dcc.Interval(id="lots2-interval", n_intervals=3_600_000),  # for polling when optimization is running
    ], id="lots2")
    return layout


def targets_tab(horizon: int):
    #checklist_dict = [{"label": "Use lot weight range ?", "value": ""}]
    checklist_dict = [{"value": ""}]    # unchecked

    return [
        html.Div([
            html.Div("Planning horizon"),
            html.Div([
                dcc.Input(type="number", id="lots2-horizon-hours", min=1, max=1024, value=horizon),
                html.Div("hours")
            ])
        ], className="lots2-horizon"),
        html.Div([
            html.Div([
                html.H4("Target production / t"),
                html.Div([
                    html.Button("Initialize: LTP", id="lots2-targets-init-ltp", className="dynreact-button dynreact-button-small", title="Derive from long term planning."),
                    html.Button("Initialize: lots", id="lots2-targets-init-lots", className="dynreact-button dynreact-button-small", title="Derive from currently planned lots."),
                ], className="lots-target-buttons"),
                html.Div([
                    html.Div(dcc.Checklist(id="lots2-check-use-lot-range",
                                           options=checklist_dict, value=[], className="lots2-checkbox")),
                    html.Div("Use lot weight range ?"),
                ], className="lots2-use-range-checkbox"),
                html.Div(id="lots2-details-plants", className="lots2-plants-targets3"),
            ]), html.Div([
                html.H4("Plant performance models"),
                html.Div(id="lots2-details-performance-models", className="lots2-performance-models")
            ], id="lots2-details-performance-wrapper", hidden=True)
        ], className="lots2-production-performance-split"),
    ]


def orders_tab():
    return [
        html.H4("Order backlog", title="Select orders for scheduling from the order backlog."),

        html.Div([
            html.Div("Selected orders:"),
            html.Div(id="lots2-orders-backlog-count"),
            html.Div(", total weight:"),
            html.Div(id="lots2-orders-backlog-weight-acc"),
            html.Div("t. "),
            html.Div(html.Button("Update", id="lots2-orders-backlog-update",
                                 className="dynreact-button dynreact-button-small"), title="Update values")
        ], className="lots2-orders-selection-overview"),

        html.Fieldset([
            html.Legend("Initialize orders"),
            html.Div([
                html.Div("Method:"),
                dcc.Dropdown(id="lots2-orders-init-method", className="lots2-orders-init-method", options=[
                    {"value": "active_process", "label": "Process", "title": "Select all orders at the selected processing stage"},
                    {"value": "active_plant", "label": "Plant", "title": "Select all orders located at the process plants"},
                    {"value": "inactive_lots", "label": "Inactive lots", "title": "Select orders assigned to inactive lots for the selected process"},
                    {"value": "active_lots", "label": "Active lots",  "title": "Select orders assigned to active lots for the selected process"},
                    # current_planning is not a good id here, would be better suited to active_lots
                    {"value": "current_planning", "label": "All lots", "title": "Select orders currently assigned to lots for the selected process"},
                ])
            ], className="lots2-orders-init-menu"),
            # TODO orders init sub-settings
            html.Div([
                html.Div("Exclude processed lots:", title="Exclude lots currently being processed?"),
                html.Div(dcc.Checklist(options=[""], value=[""], id="lots2-init-submenu-processedlots-value"), title="Exclude lots currently being processed?"),
                # Note: this one is always selected and disabled if the one above is selected
                #html.Div("Exclude processed orders:", title="Exclude orders currently being processed?"),
                #html.Div(dcc.Checklist(options=[""], value=[""], id="lots2-init-submenu-processedorders-value"), title="Exclude orders currently being processed?"),

                # The two below should only be visible if method is active_process or active_plant
                html.Div("Exclude active lots:", title="Exclude orders that are currently assigned to an active lot?", id="lots2-init-submenu-activelots-label"),
                html.Div(dcc.Checklist(options=[""], value=[""], id="lots2-init-submenu-activelots-value"), title="Exclude orders that are currently assigned to an active lot?",  id="lots2-init-submenu-activelots"),
                html.Div("Exclude all lots:", title="Exclude orders that are currently assigned to any lot?", id="lots2-init-submenu-alllots-label"),
                html.Div(dcc.Checklist(options=[""], value=[], id="lots2-init-submenu-alllots-value"), title="Exclude orders that are currently assigned to any lot?",  id="lots2-init-submenu-alllots")
            ], id="lots2-orders-init-submenu", className="lots2-orders-init-submenu", hidden=True),  # visible if and only if a main method is selected
            html.Div([
                html.Div(html.Button("Init", id="lots2-orders-backlog-init", className="dynreact-button dynreact-button-small"), title="Initialize orders from backlog"),
                html.Div(html.Button("Clear", id="lots2-orders-backlog-clear", className="dynreact-button dynreact-button-small"), title="Clear order backlog"),
            ], className="lots2-orders-init-buttons")
        ], className="lots2-orders-grouped-menu"),

        # TODO hideable?, use icon (https://wiki.selfhtml.org/wiki/SVG/Tutorials/Icons)
        html.Fieldset([
            html.Legend("Edit orders"),
            html.Div([

                html.Div([
                    html.Div("Processes:"),
                    dcc.Dropdown(id="lots2-oders-lots-processes", className="lots2-order-lots-selector", multi=True),
                    html.Div("Lots:"),
                    dcc.Dropdown(id="lots2-oders-lots-lots", className="lots2-order-lots-selector", multi=True),
                    html.Div(["(", html.Div(id="lots2-orders-lots-order-selected"), "/", html.Div(id="lots2-orders-lots-order-total"), "selected)"], className="flex"),
                    html.Div(html.Button("Select orders", id="lots2-orders-backlog-add-logs",
                             className="dynreact-button dynreact-button-small", disabled=True), title="Add orders from selected lots to backlog"),
                    html.Div(html.Button("Deselect orders", id="lots2-orders-backlog-rm-logs",
                             className="dynreact-button dynreact-button-small", disabled=True), title="Remove orders from selected lots from backlog"),
                ], className="lots2-orders-lots-editor"),
                html.Br(),
                html.Div([
                    html.Div("Backlog operations: "),
                    #html.Div(html.Button("Clear", id="lots2-orders-backlog-clear", className="dynreact-button dynreact-button-small"),
                    #         title="Clear order backlog"),
                    html.Div(html.Button("Select visible", id="lots2-orders-select-visible", className="dynreact-button dynreact-button-small"),
                             title="Select all orders currently visible in the table. Set a column filter to restrict the visible orders/rows first."),
                    html.Div(html.Button("Deselect visible", id="lots2-orders-deselect-visible", className="dynreact-button dynreact-button-small"),
                             title="Deselect all orders currently visible in the table. Set a column filter to restrict the visible orders/rows first."),
                    #html.Div(html.Button("Reset", id="lots2-orders-backlog-reset", className="dynreact-button dynreact-button-small"),
                    #         title="Reset order backlog to default selection"),
                    # TODO html.Div(html.Button("Undo", id="create-orders-backlog-undo", className="dynreact-button"))
                ], className="lots2-orders-backlog-settings-buttons")
            ]) #, id="lots2-orders-backlog-settings")
        ], className="lots2-orders-grouped-menu"),
        html.Br(),
        dash_ag.AgGrid(
            id="lots2-orders-table",
            columnDefs=[{"field": "id", "pinned": True}],
            rowData=[],
            getRowId="params.data.id",
            className="ag-theme-alpine",  # ag-theme-alpine-dark
            style={"height": "70vh", "width": "80vw", "margin-bottom": "5em"},
            columnSizeOptions={"defaultMinWidth": 125},
            columnSize="responsiveSizeToFit",
            # tooltipField is not used, but it must match an existing field for the tooltip to be shown
            defaultColDef={"tooltipComponent": "CoilsTooltip", "tooltipField": "id"},
            dashGridOptions={"rowSelection": "multiple", "suppressRowClickSelection": True, "animateRows": False,
                             "tooltipShowDelay": 100, "tooltipInteraction": True,
                             "popupParent": {"function": "setCoilPopupParent()"}},
            # "autoSize"  # "responsiveSizeToFit" => this leads to essentially vanishing column size
        ),

        html.Div(id="lots2-details-orders", className="lots2-details-orders"),

        # By default, we hide those orders, but the user may decide to display them
        html.Div(id="lots2-details-orders-hidden", className="lots2-details-orders", hidden=True),
    ]


def settings_tab(init_method: Literal["heuristic", "duedate", "snapshot", "result"]|None, iterations: int):
    return [
        html.H4("Lot creation settings"),
        dcc.ConfirmDialog(
            id='lots2-confirm-error',
            message='User information',
        ),

        # Initialization
        html.Div([
            html.Div("Initialization: ", title="Specify the algorithm for the initialization of the lot creation."),
            dcc.Dropdown(id="lots2-init-selector", options=[
                {"value": "heuristic", "label": "Heuristic",
                 "title": "A heuristic initialization that aims to start with a reasonable assignment of orders already, with low costs, but ignoring global constraints."},
                {"value": "duedate", "label": "Due date", "title": "Initialization based on the due dates of orders."},
                {"value": "snapshot", "label": "Snapshot", "title": "Initialization based on planning in current snapshot. "
                                                                    "This only makes sense if the order selection contains a significant number of orders in currently active lots"},
                # TODO show this one only if there are existing runs?
                #{"value": "result", "label": "Existing solution", "title": "Continue a previous optimization run."}
            ], value=init_method, className="lots2-init-selector"),
            # Existing results
            html.Div([
                html.Div("Solution:"),
                dcc.Dropdown(id="lots2-existing-sols")
            ], id="lots2-init-results-selector", className="lots2-existing-sol-selector lots2-panel-col", hidden=True),  # classes do not exist yet
            html.Div("Selected orders:", title="Number of orders selected for the lot creation"),
            html.Div(id="lots2-num-orders"),
            html.Div("Iterations:", title="Specify the maximum number of optimization iterations to run."),
            html.Div([
                html.Div(id="lots2-iterations-value"),
                # Note that 0 iterations actually makes sense... it will result in an optimized arrangement into lots of the selected orders, without altering the order
                dcc.Input(type="range", id="lots2-num-iterations", min=0, max=1000, value=iterations, list="lots2-iterations-options")
            ], className="lots2-iterations-view"),
            html.Div("Comment:", title="Add a comment, explaining for instance the settings applied (target weights, orders included, etc)"),
            html.Div(
                html.Div(dcc.Textarea(rows=1, cols=10, placeholder="Add a comment", id="lots2-comment", value="",
                                      title="Add a comment, explaining for instance the settings applied (target weights, orders included, etc)"))),
            html.Div("Store:", title="Store results?"),
            html.Div(dcc.Checklist(options=[""], value=[""], id="lots2-store-results"), title="Store results?"),
        ], className="lots2-settings-tab-grid"),
        html.Div([
            html.Button("Start", id="lots2-start", className="dynreact-button", disabled=True),
            html.Button("Stop", id="lots2-stop", className="dynreact-button", disabled=True)
        ], id="lots2-control-btns", className="lots2-control-btns"),
    ]

def ltp_dialog():
    return html.Dialog(
        html.Div([
            html.H3("Long term planning results"),
            html.Div([
                dash_ag.AgGrid(
                    id="lots2-ltp-table",
                    columnDefs=[{"field": "id", "pinned": True},
                                {"field": "start_time", "filter": "agDateColumnFilter",
                                 "headerName": "Start time"},
                                {"field": "end_time", "filter": "agDateColumnFilter",
                                 "headerName": "End time"},
                                {"field": "shift_duration", "filter": "agNumberColumnFilter",
                                 "headerName": "Shift duration / h"},
                                {"field": "total_production", "filter": "agNumberColumnFilter",
                                 "headerName": "Total production / t"},
                                {"field": "production_per_shift", "filter": "agNumberColumnFilter",
                                 "headerName": "Avg. production per shift / t"},
                                # {"field": "delete"} # not possible
                                ],
                    defaultColDef={"filter": "agTextColumnFilter", "filterParams": {"buttons": ["reset"]}},
                    rowData=[],
                    getRowId="params.data.id",
                    className="ag-theme-alpine",  # ag-theme-alpine-dark
                    columnSizeOptions={"defaultMinWidth": 125},
                    columnSize="responsiveSizeToFit",
                    dashGridOptions={"rowSelection": "single"}
                )
            ]),
            html.Div([
                html.Button("Cancel", id="lots2-ltp-cancel", className="dynreact-button lots2-ltp-cancel")
            ]) #, className="ltp-materials-buttons")
        ]),
        id="lots2-ltp-dialog", className="dialog-filled lots2-ltp-dialog", open=False)


@callback(Output("lots2-current_snapshot", "children"),
          Input("selected-snapshot", "data"))  # selected-snapshot is a page-global store
def snapshot_changed(snapshot: datetime|None) -> str:
    if snapshot is None:
        return ""
    return str(snapshot)


@callback(
          Output("lots2-settings-tabs", "hidden"),
          Input("selected-snapshot", "data"),
          Input("lots2-process-selector", "value")
)
def toggle_settings_tabs_visibility(snapshot: str|datetime|None, process: str|None) -> bool:
    if not dash_authenticated(config):
        return True
    snapshot = DatetimeUtils.parse_date(snapshot)
    if snapshot is None or process is None:
        return True
    return False


# Change the active tab in the settings menu by clicking one of the selection buttons in the header
@callback(
          Output("lots2-active-tab", "data"),
          State("lots2-active-tab", "data"),
          Input("lots2-tabbutton-targets", "n_clicks"),
          Input("lots2-tabbutton-orders", "n_clicks"),
          Input("lots2-tabbutton-settings", "n_clicks"),
          Input("lots2-tabsnav-prev", "n_clicks"),
          Input("lots2-tabsnav-next", "n_clicks"),
)
def select_settings_tab(active_tab: Literal["targets", "orders", "settings"]|None,  _, __, ___, ____, _v) -> Literal["targets", "orders", "settings"]:
    if not dash_authenticated(config):
        return None
    changed_ids: list[str] = GuiUtils.changed_ids(excluded_ids=[""])
    if len(changed_ids) == 0:  # initial callback
        return active_tab  # must not return no_update here, because it blocks dependent callbacks
    button_id = next((bid for bid in changed_ids if bid.startswith("lots2-tabbutton-")), None)
    new_active_tab: Literal["targets", "orders", "settings"] = "targets"
    if button_id is not None:
        new_active_tab = button_id[len("lots2-tabbutton-"):]
    elif active_tab is not None:
        nav_button_id = next((bid for bid in changed_ids if bid.startswith("lots2-tabsnav-")), None)
        if nav_button_id is not None:
            is_prev: bool = nav_button_id.endswith("prev")
            is_next = not is_prev and nav_button_id.endswith("next")
            if (is_prev and active_tab == "settings") or (is_next and active_tab == "targets"):
                new_active_tab = "orders"
            elif is_next and active_tab == "orders":
                new_active_tab = "settings"
    return new_active_tab


def _tab_button_class(selected: bool) -> str:
    name = "lots2-tab-button"
    if selected:
        name += " lots2-tab-button-active"
    return name

# The active tab in the settings menu changed
@callback(
    # The three tab containers
Output("lots2-tab-targets", "hidden"),
    Output("lots2-tab-orders", "hidden"),
    Output("lots2-tab-settings", "hidden"),
    # The three tab header buttons
    Output("lots2-tabbutton-targets", "className"),
    Output("lots2-tabbutton-orders", "className"),
    Output("lots2-tabbutton-settings", "className"),
    Output("lots2-tabsnav-prev", "hidden"),
    Output("lots2-tabsnav-next", "hidden"),
    # Input: the selected tab
    Input("lots2-active-tab", "data"))
def select_settings_tab(active_tab: Literal["targets", "orders", "settings"]|None):
    targets_selected: bool = active_tab == "targets"
    orders_selected: bool = active_tab == "orders"
    settings_selected: bool = active_tab == "settings"
    previous_hidden: bool = active_tab is None or active_tab == "targets"
    next_hidden: bool = active_tab is None or active_tab == "settings"
    return not targets_selected, not orders_selected, not settings_selected, \
        _tab_button_class(targets_selected), _tab_button_class(orders_selected), _tab_button_class(settings_selected), \
        previous_hidden, next_hidden


@callback(
    Output("lots2-ltp-table", "rowData"),
    Input("lots2-targets-init-ltp", "n_clicks"),
    State("selected-snapshot", "data"),
    State("lots2-process-selector", "value"),
    State("lots2-horizon-hours", "value"),
)
def ltp_table_opened(_, snapshot: str, process: str, horizon_hours: int):
    if not dash_authenticated(config) or process is None or snapshot is None:
        return []
    snapshot = DatetimeUtils.parse_date(snapshot)
    if snapshot is None or horizon_hours is None:
        return []
    persistence: ResultsPersistence = state.get_results_persistence()
    all_start_times: list[datetime] = persistence.start_times_ltp(snapshot - timedelta(days=32), snapshot)
    starttimes_solutions: dict[datetime, list[str]] = {starttime: persistence.solutions_ltp(starttime) for starttime in all_start_times}
    solutions: list[MidTermTargets] = []
    solution_ids: list[str] = []
    for start, solution_ids0 in starttimes_solutions.items():
        for solution_id in solution_ids0:
            sol, storages = persistence.load_ltp(start, solution_id)
            if sol.period[1] <= snapshot:
                continue
            solutions.append(sol)
            solution_ids.append(solution_id)
    columns = [{
            "id": solution_ids[idx],
            "start_time_full": t.period[0],
            "start_time": t.period[0].date(),
            "end_time": t.period[1].date(),
            "shift_duration": (t.sub_periods[0][1] - t.sub_periods[0][0]) / timedelta(hours=1),
            "total_production": t.total_production,
            "production_per_shift": t.total_production / len(t.sub_periods)   # TODO rounded representation?
            #"delete": ""   # not possible
        } for idx, t in enumerate(solutions)]
    return columns

# TODO clear button?
@callback(
    Output("lots2-details-plants", "children"),
    Output("lots2-details-plants", "className"),
    State("selected-snapshot", "data"),
    State("lots2-horizon-hours", "value"),
    State("lots2-details-plants", "children"),
    Input("lots2-process-selector", "value"),
    Input("lots2-active-tab", "data"),
    Input("lots2-targets-init-lots", "n_clicks"),
    Input("lots2-ltp-table", "selectedRows"),
    Input("lots2-check-use-lot-range", "value")
)
def update_plants(snapshot: str,
                  horizon_hours: int,
                  components: list[Component]|None,
                  process: str,
                  active_tab: Literal["targets", "orders", "settings"]|None,
                  _,
                  # TODO row in ltp popup selected
                  selected_rows: list[dict[str, any]]|None,
                  use_lot_range0: list[Literal[""]]
                  ) -> tuple[list[Component], list[any]]:
    use_lot_range: bool = len(use_lot_range0) > 0
    if use_lot_range:
        my_parent_classname = "lots2-plants-targets5"
    else:
        my_parent_classname = "lots2-plants-targets3"

    if not dash_authenticated(config) or process is None or snapshot is None:
        return None, my_parent_classname
    if active_tab != "targets":
        return no_update, my_parent_classname
    changed = GuiUtils.changed_ids()
    is_ltp_init = "lots2-ltp-table" in changed and len(selected_rows) > 0
    re_init: bool = "lots2-targets-init-lots" in changed or is_ltp_init
    toggle_lot_range: bool = "lots2-check-use-lot-range" in changed
    snapshot = DatetimeUtils.parse_date(snapshot)
    plants: list[Equipment] = state.get_site().get_process_equipment(process)
    elements = []
    # TODO alternatively, we could use targets from the long term planning, or based on the plant capacity and duration
    # FIXME why does this fail regularly?
    if not is_ltp_init:
        _, targets = state.get_snapshot_solution(process, snapshot, timedelta(hours=horizon_hours))
    else:
        targets = _targets_from_ltp(selected_rows[0], process, snapshot, horizon_hours)
    target_weights: dict[int, float] = {plant: t.total_weight for plant, t in targets.target_weight.items()}
    for plant in plants:
        if components is not None and not re_init:
            # get vals from components
            existing = next((c for c in components if c.get("props").get("data-plant") == str(plant.id)), None)
            if existing is not None:
                existing_index = components.index(existing)
                elements.append(components[existing_index - 2])
                elements.append(components[existing_index - 1])
                elements.append(existing)
                if use_lot_range:
                    div2 = html.Div(
                        dcc.Input(type="number", min="0", value=str(0), placeholder="Lot size minimum in t"),
                        title="Lot size minimum in t", className="lot2-size-min",
                        style={'display': 'block'},
                        **{"data-plant": str(plant.id), "data-default": str(0)})

                    div3 = html.Div(
                        dcc.Input(type="number", min="0", value=str(0), placeholder="Lot size maximum in t"),
                        title="Lot size maximum in t", className="lot2-size-max",
                        style={'display': 'block'},
                        **{"data-plant": str(plant.id), "data-default": str(0)})

                    found_in_components = False
                    for c in components:
                        if c.get("props").get("data-plant") == str(plant.id):
                            if c.get("props").get("className") == "lot2-size-min":
                                elements.append(c)
                                found_in_components = True
                            if c.get("props").get("className") == "lot2-size-max":
                                elements.append(c)
                    if not found_in_components:  # append empty elements
                        elements.append(div2)
                        elements.append(div3)
                continue
        # set start vals
        target = round(target_weights.get(plant.id, 0))
        checkbox = html.Div(dcc.Checklist(options=[""], value=[""] if target > 0 else []),
                            title="Include plant " + str(plant.name_short if plant.name_short is not None else plant.id) + " in planning?")
        elements.append(checkbox)
        elements.append(GuiUtils.plant_element(plant))
        div = html.Div(dcc.Input(type="number", min="0", value=str(target), placeholder="Target production in t"),
                       title="Target production in t", className="create-plant-input", **{"data-plant": str(plant.id), "data-default": str(target) })
        elements.append(div)
        if use_lot_range:   # visible
            div2 = html.Div(dcc.Input(type="number", min="0", value=str(0), placeholder="Lot size minimum in t"),
                            title="Lot size minimum in t", className="lot2-size-min",
                            style={'display': 'block'},
                            **{"data-plant": str(plant.id), "data-default": str(target)})

            div3 = html.Div(dcc.Input(type="number", min="0", value=str(0), placeholder="Lot size maximum in t"),
                            title="Lot size maximum in t", className="lot2-size-max",
                            style={'display': 'block'},
                            **{"data-plant": str(plant.id), "data-default": str(target)})
            elements.append(div2)
            elements.append(div3)

    # TODO display total tonnes
    # my_parent_classname for formatting purpose
    return elements, my_parent_classname


def _targets_from_ltp(selected_row: dict[str, any], process: str, start_time: datetime, horizon_hours: int) -> ProductionTargets:
    start_time_ltp = DatetimeUtils.parse_date(selected_row.get("start_time_full"))
    solution_ltp = selected_row.get("id")
    persistence: ResultsPersistence = state.get_results_persistence()
    mid_term, storage = persistence.load_ltp(start_time_ltp, solution_ltp)
    targets: ProductionTargets = ModelUtils.mid_term_targets_from_ltp_result(mid_term, process, start_time, start_time + timedelta(hours=horizon_hours))
    return targets


@callback(
          Output("lots2-orders-backlog-init", "disabled"),
          Output("lots2-orders-backlog-init", "title"),
          Output("lots2-orders-init-submenu", "hidden"),
          # These are only visible for certain init methods
            Output("lots2-init-submenu-activelots-label", "hidden"),
            Output("lots2-init-submenu-activelots", "hidden"),
            Output("lots2-init-submenu-alllots-label", "hidden"),
            Output("lots2-init-submenu-alllots", "hidden"),

            Output("lots2-init-submenu-processedlots-value", "value"),
            #Output("lots2-init-submenu-processedorders-value", "value"),
            Output("lots2-init-submenu-alllots-value", "value"),
            Output("lots2-init-submenu-activelots-value", "value"),
          Input("lots2-orders-init-method", "value"),
        Input("lots2-init-submenu-processedlots-value", "value"),
        # Input("lots2-init-submenu-processedorders-value", "value"),
          Input("lots2-init-submenu-alllots-value", "value"),
          Input("lots2-init-submenu-activelots-value", "value"),
)
def init_method_changed(method: Literal["active_process", "active_plant", "inactive_lots", "active_lots", "current_planning"]|None,
                      processed_lots: list[Literal[""]], all_lots_value: list[Literal[""]], active_lots_value: list[Literal[""]]):
    if method is None or method == "":
        return True, "Select an initialization method first.", True, True, True, True, True, [], [], []
    hide_lots_submenu: bool = method != "active_process" and method != "active_plant"
    changed_ids = GuiUtils.changed_ids()
    method_changed = "lots2-orders-init-method" in changed_ids
    if method_changed:
        all_lots_value = []
        active_lots_value = [""] if method != "active_lots" else []
        processed_lots = [""]
        #processed_orders = [""]
    # TODO!

    return False, "Initialize orders using the " + str(method) + " method.", False, hide_lots_submenu, hide_lots_submenu, hide_lots_submenu, hide_lots_submenu, \
        processed_lots, all_lots_value, active_lots_value


@callback(
    Output("lots2-oders-lots-processes", "options"),
    Output("lots2-oders-lots-processes", "value"),
    Output("lots2-oders-lots-lots", "options"),
    Input("lots2-oders-lots-processes", "value"),
    Input("lots2-orders-data", "data"),
    Input("lots2-active-tab", "data"),
    # Input("create-details-trigger", "n_clicks"), # => TODO replace maybe by tab state?
    State("lots2-process-selector", "value"),
    State("selected-snapshot", "data")
)
def order_backlog_lots_operation(selected_processes, order_data: dict[str, str] | None, active_tab: Literal["targets", "orders", "settings"]|None, process: str, snapshot: str):
    snapshot = DatetimeUtils.parse_date(snapshot)
    if not dash_authenticated(config) or process is None or snapshot is None:
        return {}, None, {}  # must not return None for dropdown options
    snapshot_serialized: str = DatetimeUtils.format(snapshot)
    snapshot_obj = state.get_snapshot(snapshot)
    if snapshot_obj is None or len(snapshot_obj.orders) == 0:
        return {}, None, {}
    if active_tab != "orders":
        return no_update, no_update, no_update
    update_selection: bool = selected_processes is None or order_data is None or order_data.get("process") != process \
                             or order_data.get("snapshot") != snapshot_serialized
    if update_selection:
        selected_processes = [process]
    site = state.get_site()
    all_processes = site.processes
    predecessors = [site.get_process(process)]
    new_predecessors = list(predecessors)
    while len(new_predecessors) > 0:
        proc_names = [p.name_short for p in new_predecessors]
        new_predecessors = [proc for proc in all_processes if proc.next_steps is not None and
                            proc not in predecessors and
                            next((p for p in proc.next_steps if p in proc_names), None) is not None]
        predecessors.extend(new_predecessors)
    processes_options = [{"label": p.name_short, "value": p.name_short, "title": p.name} for p in predecessors]
    selected_plants = [plant.id for proc in selected_processes for plant in state.get_site().get_process_equipment(proc)]
    existing_lots = [lot for plant, lots in snapshot_obj.lots.items() if plant in selected_plants for lot in lots]
    lots_options = sorted([{"label": lot.id, "value": lot.id, "title": lot.id} for lot in existing_lots], key=lambda d: d["label"] )
    return processes_options, selected_processes, lots_options


@callback(
    Output("lots2-orders-backlog-add-logs", "disabled"),
    Output("lots2-orders-backlog-rm-logs", "disabled"),
    Output("lots2-orders-lots-order-selected", "children"),
    Output("lots2-orders-lots-order-total", "children"),
    Input("lots2-oders-lots-lots", "value"),
    Input("lots2-orders-table", "selectedRows"),
    State("lots2-process-selector", "value"),
    State("selected-snapshot", "data"),
    config_prevent_initial_callbacks=True
)
def lot_buttons_disabled_check(selected_lots: list[str]|None, selected_rows: list[dict[str, any]]|None, process: str|None, snapshot: str|None):
    if not dash_authenticated(config) or process is None or snapshot is None:
        return None, None, None, None
    snapshot = DatetimeUtils.parse_date(snapshot)
    snapshot_obj = state.get_snapshot(snapshot)
    disabled = selected_lots is None or len(selected_lots) == 0 or snapshot_obj is None
    if disabled:
        return disabled, disabled, 0, 0
    selected_orders: list[str] = [row["id"] if isinstance(row, dict) else row for row in selected_rows] if selected_rows is not None else []
    lots_affected: list[Lot] = [lot for lots in snapshot_obj.lots.values() for lot in lots if lot.id in selected_lots]
    orders_affected: list[str] = [order for lot in lots_affected for order in lot.orders]
    total_orders = len(orders_affected)
    selected_orders = len([o for o in orders_affected if o in selected_orders])
    return disabled, disabled, selected_orders, total_orders

@callback(
            Output("lots2-orders-table", "columnDefs"),
            Output("lots2-orders-table", "rowData"),
            Output("lots2-orders-table", "selectedRows"),
            Output("lots2-orders-data", "data"),
           # Output("lots2-orders-backlog-count", "children"),
           # Output("lots2-num-orders", "children"),
           # Output("lots2-orders-backlog-weight-acc", "children"),

            Input("selected-snapshot", "data"),
            Input("lots2-process-selector", "value"),
            Input("lots2-orders-backlog-init", "n_clicks"),
            Input("lots2-orders-backlog-clear", "n_clicks"),
            Input("lots2-orders-select-visible", "n_clicks"),
            Input("lots2-orders-deselect-visible", "n_clicks"),
            Input("lots2-orders-backlog-add-logs", "n_clicks"),
            Input("lots2-orders-backlog-rm-logs", "n_clicks"),
            Input("lots2-orders-backlog-update", "n_clicks"),  # the only purpose of this guy is to update the displayed number of selected orders and accumulated weight
            State("lots2-orders-data", "data"),
            State("lots2-oders-lots-lots", "value"),
            State("lots2-orders-table", "selectedRows"),
            State("lots2-orders-table", "virtualRowData"),
            State("lots2-horizon-hours", "value"),
            State("lots2-orders-init-method", "value"),
            State("lots2-init-submenu-processedlots-value", "value"),
            #State("lots2-init-submenu-processedorders-value", "value"),
            State("lots2-init-submenu-alllots-value", "value"),
            State("lots2-init-submenu-activelots-value", "value"),
)
def update_orders(snapshot: str, process: str, _1, _2, _3, _4, _5, _6, _7, orders_data: dict[str, str]|None, selected_lots: list[str],
                  selected_rows: list[dict[str, any]]|None, filtered_rows: list[dict[str, any]]|None, horizon_hours: int,
                  init_method: Literal["active_process", "active_plant", "inactive_lots", "active_lots", "current_planning"]|None,
                  processed_lots: list[Literal[""]], all_lots_value: list[Literal[""]], active_lots_value: list[Literal[""]]):
    if not dash_authenticated(config):
        return None, None, None, None
    snapshot = DatetimeUtils.parse_date(snapshot)
    if snapshot is None or process is None:
        return None, None, None, None
    snapshot_serialized: str = DatetimeUtils.format(snapshot)
    snapshot_obj = state.get_snapshot(snapshot)
    changed_ids: list[str] = GuiUtils.changed_ids()
    is_clear_command: bool = "lots2-orders-backlog-clear" in changed_ids
    is_init_command: bool = "lots2-orders-backlog-init" in changed_ids
    update_selection: bool = orders_data is None or orders_data.get("process") != process \
                             or orders_data.get("snapshot") != snapshot_serialized
    if update_selection:
        orders_data = {"process": process, "snapshot": snapshot_serialized}
    site = state.get_site()

    def column_def_for_field(field: str, info: FieldInfo):
        filter_id = "agNumberColumnFilter" if info.annotation == float or info.annotation == int else \
            "agDateColumnFilter" if info.annotation == datetime or info.annotation == date else \
                "agTextColumnFilter"
        col_def = {"field": field, "filter": filter_id, "filterParams": {"buttons": ["reset"]}}
        return col_def

    fields = [column_def_for_field(key, info) for key, info in snapshot_obj.orders[0].model_fields.items() if (key not in ["material", "lot", "lot_position" ])] + \
             ([column_def_for_field(key, info) for key, info in snapshot_obj.orders[0].material_properties.model_fields.items()] if isinstance(snapshot_obj.orders[0].material_properties, BaseModel) else [])

    value_formatter_object = {"function": "formatCell(params.value)"}
    for field in fields:
        if field["field"] == "id":
            field["pinned"] = True
            field["headerName"] = "Id"
            field["checkboxSelection"] = True
            field["headerCheckboxSelection"] = True
        if field["field"] in ["lots", "lot_positions", "active_processes", "coil_status", "follow_up_processes"]:
            field["valueFormatter"] = value_formatter_object

    def order_to_json(o: Order):
        as_dict = o.model_dump(exclude_none=True, exclude_unset=True)
        # for key in ["lots", "lot_positions"]:
        #    if key in as_dict:
        #        as_dict[key] = json.dumps(as_dict[key])
        if o.allowed_equipment is not None:
            as_dict["allowed_plants"] = [
                next((plant.name_short for plant in site.equipment if plant.id == p), str(p)) for p in
                o.allowed_equipment]
        if o.current_equipment is not None:
            as_dict["current_plants"] = [
                next((plant.name_short for plant in site.equipment if plant.id == p), str(p)) for p in
                o.current_equipment]
        if isinstance(o.material_properties, BaseModel):
            as_dict.update(o.material_properties.model_dump(exclude_none=True, exclude_unset=True))
        return as_dict

    new_selected_rows = {"ids": []}

    if is_init_command:  # TODO set appropriate method flags in eligibile_orders method
        if init_method is None:
            return no_update, no_update, no_update, no_update, no_update, no_update
        if init_method == "active_process":
            method = [OrderInitMethod.ACTIVE_PROCESS]
        elif init_method == "active_plant":
            method = [OrderInitMethod.ACTIVE_PLANT]
        elif init_method == "inactive_lots":
            method = [OrderInitMethod.INACTIVE_LOTS]
        elif init_method == "current_planning":
            method = [OrderInitMethod.CURRENT_PLANNING]
        elif init_method == "active_lots":
            method = [OrderInitMethod.CURRENT_PLANNING, OrderInitMethod.OMIT_INACTIVE_LOTS]
        if len(processed_lots) > 0:
            method.append(OrderInitMethod.OMIT_CURRENT_LOT)
        if init_method != "current_planning" and method != "inactive_lots" and method != "active_lots" and len(all_lots_value) > 0:
            method.append(OrderInitMethod.OMIT_ACTIVE_LOTS)
            method.append(OrderInitMethod.OMIT_INACTIVE_LOTS)
        if init_method != "current_planning" and method != "active_lots" and len(active_lots_value) > 0:
            method.append(OrderInitMethod.OMIT_ACTIVE_LOTS)

        eligible_orders: list[str] = state.get_snapshot_provider().eligible_orders(snapshot_obj, process, (snapshot, snapshot + timedelta(hours=horizon_hours)), method=method)
        # maintain old selection, if appropriate
        if not update_selection and selected_rows is not None:
            eligible_orders = eligible_orders + [row for row in  (row0["id"] if isinstance(row0, dict) else row0 for row0 in selected_rows) if row not in eligible_orders]
        new_selected_rows = {"ids": eligible_orders}
    elif not update_selection and not is_clear_command:
        new_selected_rows = {"ids": [row["id"] if isinstance(row, dict) else row for row in selected_rows] if selected_rows is not None else []}
        is_lot_based_update = ("lots2-orders-backlog-add-logs" in changed_ids or "lots2-orders-backlog-rm-logs" in changed_ids) and selected_lots is not None
        is_filtered_view_based_update = ("lots2-orders-select-visible" in changed_ids or "lots2-orders-deselect-visible" in changed_ids) and filtered_rows is not None
        if is_lot_based_update:
            lots_affected: list[Lot] = [lot for lots in snapshot_obj.lots.values() for lot in lots if lot.id in selected_lots]
            orders_affected: list[str] = [order for lot in lots_affected for order in lot.orders]
            is_removal: bool = "lots2-orders-backlog-rm-logs" in changed_ids
            if is_removal:
                new_selected_rows["ids"] = [order for order in new_selected_rows["ids"] if order not in orders_affected]
            else:
                new_selected_rows["ids"] = new_selected_rows["ids"] + [order for order in orders_affected if order not in new_selected_rows["ids"]]
        elif is_filtered_view_based_update:
            orders_affected: list[str] = [row["id"] if isinstance(row, dict) else row for row in filtered_rows]
            is_removal: bool = "lots2-orders-deselect-visible" in changed_ids
            if is_removal:
                new_selected_rows["ids"] = [order for order in new_selected_rows["ids"] if order not in orders_affected]
            else:
                new_selected_rows["ids"] = new_selected_rows["ids"] + [order for order in orders_affected if order not in new_selected_rows["ids"]]
    #if is_init_command:
    #    # TODO1
    processes: list[list[int]] = [p.process_ids for p in site.processes]
    num_processes = len(processes)
    current_process_index = processes.index(site.get_process(process, do_raise=True).process_ids)
    process_plants: list[list[int]] = [sorted([plant.id for plant in site.get_process_equipment(proc.name_short)]) for proc in site.processes]

    def process_index_for_proc_id(proc_id: int) -> int:
        return next((idx for idx, proc in enumerate(processes) if proc_id in proc), num_processes)

    def process_index_for_order(o: Order) -> int:
        process_indices: list[int] = [process_index_for_proc_id(p) for p in o.current_processes]
        if len(process_indices) == 0:  # Should not happen
            return 10_000
        min_idx = min(process_indices)
        max_idx = max(process_indices)
        if min_idx > current_process_index:
            return 5000 + min_idx
        if max_idx < current_process_index:
            return 1000 - max_idx
        if max_idx > current_process_index:
            return 500 + max_idx
        if min_idx < current_process_index:
            return 100 - min_idx
        plants: list[int] = process_plants[min_idx]
        plant_idx = plants.index(o.current_equipment[0]) if o.current_equipment is not None and o.current_equipment[0] in plants else len(plants)
        return plant_idx

    # && filter orders matching for selected process
    # current_process_index                                   # index of curr process 1,2,3
    current_process_plants = process_plants[current_process_index]  # list plant indices of curr process
    orders_filtered_idx = []
    print('loc 845 ', current_process_index, current_process_plants)
    for idx, order in enumerate(snapshot_obj.orders):
        print('loc 847 ', order.allowed_equipment)
        if any(order in current_process_plants for order in order.allowed_equipment):
            print('show_order ', idx)
            orders_filtered_idx.append(idx)
    print('loc 855 ', orders_filtered_idx)
    orders_filtered = [snapshot_obj.orders[idx] for idx in orders_filtered_idx]
    #print('loc 854 ', orders_filtered)
    orders_sorted = sorted(snapshot_obj.orders, key=process_index_for_order)
    selected_ids: list[str] = new_selected_rows["ids"]
    weight = sum(o.actual_weight for o in orders_sorted if o.id in selected_ids)
    orders_data["orders_selected_cnt"] = len(selected_ids)
    orders_data["orders_selected_weight"] = weight
    return fields, [order_to_json(order) for order in orders_sorted], new_selected_rows, orders_data


@callback(
    Output("lots2-orders-backlog-count", "children"),
    Output("lots2-num-orders", "children"),
    Output("lots2-orders-backlog-weight-acc", "children"),
    Input("lots2-orders-data", "data"),
)
def orders_updated(orders_data: dict[str, str]|None):
    if not dash_authenticated(config):
        return None, None, None
    if orders_data is None:
        return 0, 0, 0
    cnt = orders_data["orders_selected_cnt"]
    weight = orders_data["orders_selected_weight"]
    return cnt, cnt, f"{weight:.2f}"


clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="showModal"
    ),
    Output("lots2-ltp-dialog", "title"),
    Input("lots2-targets-init-ltp", "n_clicks"),
    State("lots2-ltp-dialog", "id"),
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="closeModal"
    ),
    Output("lots2-ltp-cancel", "title"),
    Input("lots2-ltp-cancel", "n_clicks"),
    State("lots2-ltp-dialog", "id")
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="closeModal"
    ),
    Output("lots2-ltp-table", "title"),
    Input("lots2-ltp-table", "selectedRows"),
    State("lots2-ltp-dialog", "id")
)

@callback(
    Output("lots2-objectives-history", "data"),
    Output("lots2-lots-data", "data"),
    Output("lots2-lotsview-header", "hidden"),
    State("selected-snapshot", "data"),
    State("lots2-process-selector", "value"),
    Input("lots2-interval", "n_intervals"),
    Input("lots2-init-selector", "value"),
    #Input("lots2-existing-sols", "value")
)
def update_solution_state(snapshot: str|datetime|None, process: str|None, _, selected_init_method: str|None):  # , selected_solution: str|None):
    global lot_creation_listener
    selected_solution = None
    changed_ids: list[str] = GuiUtils.changed_ids()
    solution_selected: bool = selected_init_method == "result" and "lots2-existing-sols" in changed_ids  # TODO this is not implemented here yet
    history: list[float] | None = None
    solution: ProductionPlanning | None = None
    if solution_selected and snapshot is not None and process is not None and selected_solution is not None:
        snapshot = DatetimeUtils.parse_date(snapshot)
        optimization_state: LotsOptimizationState|None = state.get_results_persistence().load(snapshot, process, selected_solution)
        history = [h.total_value for h in optimization_state.history]
        solution = optimization_state.current_solution
    elif lot_creation_listener is not None:
        history = lot_creation_listener.history()
        solution, _ = lot_creation_listener.solution()
    else:
        snapshot = DatetimeUtils.parse_date(snapshot)
        lots_hidden = snapshot is None or process is None  #  or selected_init_method is None or (selected_init_method == "result" and selected_solution is None)
        if lots_hidden:
            return None, None, True
        horizon = timedelta(days=1)  # ?
        #if selected_init_method == "duedate":
        #    solution, _ = state.get_due_date_solution(process, snapshot, horizon)
        #else:
        # Display the current snapshot solution
        solution, _ = state.get_snapshot_solution(process, snapshot, horizon)
        obj = state.get_cost_provider().process_objective_function(solution).total_value
        history = [obj]
    lots_data = prepare_lots_for_lot_view(snapshot, process, solution)
    return history, lots_data, False


@callback(
    Output("lots2-creation-objectives", "figure"),
    #Output("lots2-creation-graph", "hidden"),
    Input("lots2-objectives-history", "data")
)
def update_figure(history: list[float]|None):
    global lot_creation_listener
    if history is None and lot_creation_listener is None:
        return px.line() #, False
    history = history if history is not None else lot_creation_listener.history()
    df = pd.DataFrame({"iteration": range(len(history)), "objective": history})
    return px.line(df, markers=True, x="iteration", y="objective") #, False



# It would be nice to extract this from the huge function below, but it would inevitably lead to circular dependencies
#@callback(
#          Output("lots2-iterations-value", "children"),
#          Output("lots2-num-iterations", "value"),
#          Input("lots2-iterations", "data"),
#)
#def set_iterations(iterations: str):
#    try:
#        iterations_int = int(float(iterations))
#        if iterations_int <= 0:
#            raise Exception("Number iterations must not be negative")
#        return iterations_int, iterations_int
#    except:
#        return "", ""


@callback(Output("lots2-start", "disabled"),
          Output("lots2-stop", "disabled"),
          Output("lots2-process-selector", "value"),
          Output("lots2-process-selector", "disabled"),
          #Output("lots2-iterations-value", "children"),
          Output("lots2-num-iterations", "value"),
          Output("lots2-iterations", "data"),
          Output("lots2-iterations-value", "children"),

          Output("lots2-init-results-selector", "hidden"),
          Output("lots2-init-selector", "value"),
          Output("lots2-existing-sols", "options"),
          Output("lots2-existing-sols", "value"),

          Output("lots2-existing-sols", "disabled"),
          #Output("lots2-init-selector", "disabled"),   # unsupported option

          Output("lots2-control-btns", "title"),
          Output("lots2-interval", "interval"),
          Output("lots2-running-indicator", "hidden"),

          Output('lots2-confirm-error', 'displayed'),
          Output('lots2-confirm-error', 'message'),

          State("selected-snapshot", "data"),
          State("lots2-check-use-lot-range", "value"),
          State("lots2-details-plants", "children"),
          State("lots2-details-performance-models", "children"),
          #State("lots2-settings-popup-data", "data"),
          State("lots2-orders-table", "selectedRows"),
          State("lots2-comment", "value"),

          State("lots2-orders-data", "data"),  # we'd like to make this an Input, but it leads to circular dependencies with process_selector
          State("lots2-store-results", "value"),
          Input("lots2-active-tab", "data"),                               # as a workaround for the above problem we trigger on tab changes
          # Input instead of State because we validate the values and disable the start button if it is invalid
          Input("lots2-horizon-hours", "value"),
          Input("lots2-num-iterations", "value"),
          Input("lots2-iterations", "data"),
          Input("lots2-process-selector", "value"),
          Input("lots2-init-selector", "value"),
          Input("lots2-existing-sols", "value"),
          Input("lots2-start", "n_clicks"),
          Input("lots2-stop", "n_clicks"),
          Input("lots2-interval", "n_intervals"),

          )
def process_changed(snapshot: datetime|None,
                    use_lot_range0: list[Literal[""]],
                    target_elements: list[Component]|None,
                    perf_model_elements: list[Component]|None,
                    selected_order_rows: list[dict[str, any]] | None,
                    create_comment: str|None,
                    order_data: dict[str, Any] | None, # keys "snapshot", "process", "orders_selected_cnt", "orders_selected_weight"
                    store_results0: list[Literal[""]],
                    _tab,
                    horizon_hours: int,
                    iterations: float|str,
                    iterations_stored: int|None,
                    process: str,
                    selected_init_method: Literal["heuristic", "duedate", "snapshot", "result"]|None,
                    existing_solution: str|dash._callback.NoUpdate|None,
                    _, __, ___,
                    ):
    global lot_creation_listener
    flag_display_error = False
    error_message = ""
    use_lot_range: bool = len(use_lot_range0) > 0
    interval = 3_600_000
    if not dash_authenticated(config):
        return (True, True, process, True, iterations, iterations, iterations, True, selected_init_method, [],
                existing_solution, True, "Not authenticated", interval, True, flag_display_error, error_message)
    store_results: bool = len(store_results0) > 0
    changed_ids: list[str] = GuiUtils.changed_ids()
    # TODO if running, then use configured iterations from run
    used_iterations = iterations if "lots2-num-iterations" in changed_ids else iterations_stored
    iterations = int(float(used_iterations)) if used_iterations is not None else 10

    snapshot = DatetimeUtils.parse_date(snapshot)
    is_running, proc_running = check_running_optimization()
    if is_running:
        process = proc_running
    elif "process-selector" in changed_ids:  # ensure graph output is removed
        lot_creation_listener = None
        existing_solution = None
    selection_disabled: bool = False
    results = []
    existing_solutions: list[str]|dash._callback.NoUpdate = state.get_results_persistence().solutions(snapshot, process) if \
        (process is not None and snapshot is not None) and (selected_init_method is None or selected_init_method == "result") else dash.no_update
    if isinstance(existing_solutions, list) and len(existing_solutions) > 0:
        results = [{"label": sol, "value": sol, "title": sol} for sol in existing_solutions]
    result_selector_hidden: bool = selected_init_method != "result"
    stop_disabled = check_stop_optimization(changed_ids)
    if is_running and not stop_disabled:
        interval = 3000
        selection_disabled = True
        #for result in results:  # TODO not working
        #    result["disabled"] = True
        #settings_trigger_hidden = selected_init_method == "result"
        return (True, stop_disabled, process, True, iterations, iterations, iterations, result_selector_hidden, selected_init_method, results,
                existing_solution, selection_disabled, "Optimization running", interval, False, flag_display_error, error_message)
    if horizon_hours is None or iterations is None or process is None or snapshot is None:
        title = "Select a process first" if process is None else "Select a snapshot first" if snapshot is None else "Enter valid planning horizon"
        return (True, stop_disabled, process, False, iterations, iterations, iterations, True, selected_init_method, [], None,
                selection_disabled, title, interval, True, flag_display_error, error_message)
    if selected_init_method is None:
        if len(existing_solutions) > 0:
            selected_init_method = "result"
        else:
            selected_init_method = "heuristic"
    # TODO orders > 1 or orders > 0
    orders_unselected: bool = order_data is None or not order_data.get("orders_selected_cnt") > 0 or \
                              order_data.get("process") != process or order_data.get("snapshot") != DatetimeUtils.format(snapshot)
    plant_targets_unset: bool = target_elements is None and selected_init_method != "result"
    if orders_unselected or plant_targets_unset:
        title = "Select orders first" if orders_unselected else "Set plant targets first"
        return (True, stop_disabled, process, False, iterations, iterations, iterations, True, selected_init_method, [], None,
                selection_disabled, title, interval, True, flag_display_error, error_message)
    result_selector_hidden = selected_init_method != "result"
    # here start optimization
    start_disabled, error_msg, info_msg = check_start_optimization(changed_ids, process, snapshot, iterations, horizon_hours, selected_init_method,
                existing_solution if selected_init_method == "result" else None, use_lot_range, target_elements, perf_model_elements, selected_order_rows, create_comment, store_results)
    if error_msg is not None:  # TODO display message!
        print(error_msg)
        pass
    if selected_init_method == "result" and existing_solution is None:
        if start_disabled or len(existing_solutions) == 0 or "create-existing-sols" in changed_ids:  # trying to start the optimization, or explicitly deselected solution id
            title = "Select an existing result" if len(results) > 0 else \
                        "No previous results avaialable, select a different initialization method."
            return (True, stop_disabled, process, False, iterations, iterations, iterations, False, selected_init_method, results, existing_solution,
                    selection_disabled, title, interval, True, flag_display_error, error_message)
        existing_solution = existing_solutions[-1]  # ?
    existing_solution = existing_solution if selected_init_method == "result" else dash.no_update
    stop_disabled = not start_disabled
    if start_disabled:  # just started the optimization
        interval = 3000
        selection_disabled = True
        #for result in results:  # TODO not working
        #    result["disabled"] = True
    process_selection_disabled = not stop_disabled
    running_indicator_hidden = not start_disabled
    #settings_trigger_hidden = selected_init_method == "result"
    #settings_trigger_disabled = start_disabled

    if info_msg is not None:
        flag_display_error = True

    return (start_disabled, stop_disabled, process, process_selection_disabled, iterations, iterations, iterations, result_selector_hidden,
            selected_init_method, results, existing_solution, selection_disabled, "Start/stop planning optimization", interval, running_indicator_hidden,
            flag_display_error, info_msg)


def check_running_optimization() -> tuple[bool, str|None]:
    global lot_creation_thread
    if lot_creation_thread is not None:
        if not lot_creation_thread.is_alive():
            lot_creation_thread = None
            if lot_creation_listener is not None:
                lot_creation_listener.stop()
        if lot_creation_thread is not None:
            return True, lot_creation_thread.process()
    return False, None


def check_stop_optimization(changed_ids: list[str]) -> bool:
    global lot_creation_thread
    global lot_creation_listener
    if "lots2-stop" in changed_ids and lot_creation_thread is not None:
        lot_creation_thread.kill()
        lot_creation_thread = None
        if lot_creation_listener is not None:
            lot_creation_listener.stop()
    return lot_creation_thread is None


#TODO take into account planning horizon / horizon hours?
def check_start_optimization(changed_ids: list[str], process: str|None, snapshot: datetime|None, iterations: int|None,
                             horizon_hours: int, selected_init_method: Literal["heuristic", "duedate", "snapshot", "result"],
                             existing_solution: str|None,
                             use_lot_range: bool,
                             plant_target_components: list[Component]|None,
                             perf_model_components: list[Component]|None,
                             #order_data: dict[str, str] | None,
                             selected_order_rows: list[dict[str, any]]|None,
                             create_comment: str|None,
                             store_results: bool) -> tuple[bool, str, str | None]:
    """
    :return:
        - bool: whether the optimization is running
        - str: an error message
        - str: user info message GUI
    """
    global lot_creation_thread
    global lot_creation_listener
    if process is None or snapshot is None:
        return lot_creation_thread is not None, None, None
    error_msg: str|None = None
    info_msg: str | None = None
    if "lots2-start" in changed_ids and lot_creation_thread is None:
        try:
            snapshot_obj = state.get_snapshot(snapshot)
            horizon = timedelta(hours=horizon_hours)
            period: tuple[datetime, datetime] = (snapshot_obj.timestamp, snapshot_obj.timestamp + horizon)
            persistence = state.get_results_persistence()
            optimization_state: LotsOptimizationState | None = None
            initial_solution: ProductionPlanning|None = None
            best_solution: ProductionPlanning|None = None
            history: list[ObjectiveFunction]|None = None
            targets: ProductionTargets|None = None
            targets_customized: bool = False
            orders: list[str]|None = None
            optimization_algo: LotsOptimizationAlgo = state.get_lots_optimization()
            parameters: dict[str, any]|None = None
            perf_models: list[PlantPerformanceModel] = None
            if existing_solution is not None:
                optimization_state = persistence.load(snapshot, process, existing_solution)
                initial_solution = optimization_state.current_solution
                targets = initial_solution.get_targets()
                best_solution = optimization_state.best_solution
                history = optimization_state.history
                parameters = optimization_state.parameters
                perf_model_ids = parameters.get("performance_models", []) if parameters is not None else []
                if len(perf_model_ids) > 0:
                    perf_models = [model for model in state.get_plant_performance_models() if model.id() in perf_model_ids]
            else:
                plants = state.get_site().get_process_equipment(process)

                targets, targets_customized, info_msg = target_values_from_settings(process, period, [p.id for p in plants], use_lot_range, plant_target_components)
                if info_msg is not None:
                    return lot_creation_thread is not None, error_msg, info_msg
                perf_models = performance_models_from_elements(process, perf_model_components)
                snapshot_serialized: str = DatetimeUtils.format(snapshot)
                orders: list[str] = [row["id"] if isinstance(row, dict) else row for row in selected_order_rows]
                if selected_init_method == "duedate":
                    initial_solution, targets = optimization_algo.due_dates_solution(process, snapshot_obj, horizon, state.get_cost_provider(),
                                                    targets=targets, orders=orders)
                elif selected_init_method == "snapshot":
                    initial_solution, targets = optimization_algo.snapshot_solution(process, snapshot_obj, horizon, state.get_cost_provider(),
                                             targets=targets, orders=orders)
                else:  # init = heuristic
                    initial_solution, targets = optimization_algo.heuristic_solution(process, snapshot_obj, horizon, state.get_cost_provider(),
                                                     targets, orders, start_orders=None)  # TODO start orders
                parameters = {
                    "targets": "snapshot" if not targets_customized else "custom",
                    "horizon_hours": horizon_hours,
                    "target_production": sum(t.total_weight for t in targets.target_weight.values()),
                    "initialization": selected_init_method,
                    "performance_models": [model.id() for model in perf_models]
                }
            if len(targets.target_weight) == 0 or sum(t.total_weight for t in targets.target_weight.values()) <= 0:
                raise Exception("Nothing scheduled")  # TODO display it somewhere
            if len(initial_solution.order_assignments) == 0:
                raise Exception("No orders included")  # TODO
            if create_comment is not None and len(create_comment) > 0 and parameters is not None:
                parameters["comment"] = create_comment
            optimization: LotsOptimizer[any] = optimization_algo.create_instance(process,
                    snapshot_obj, state.get_cost_provider(), targets=targets, initial_solution=initial_solution, min_due_date=None,
                    best_solution=best_solution, history=history, parameters=parameters, orders=orders, performance_models=perf_models)  # TODO due date?
            if lot_creation_thread is not None:  # FIXME rather abort operation?
                lot_creation_thread.kill()
            if lot_creation_listener is not None:
                lot_creation_listener.stop()

            lot_creation_thread = KillableOptimizationThread(process, snapshot, optimization, num_iterations=iterations)
            time_id: str = DatetimeUtils.format(DatetimeUtils.now(), use_zone=False).replace("-", "").replace(":", "").replace("T", "")
            # millis_now = DatetimeUtils.to_millis(DatetimeUtils.now())
            lot_creation_listener = FrontendOptimizationListener(id=process + "_" + time_id if existing_solution is None else existing_solution,
                            persistence=persistence, store_results=store_results, initial_state=optimization_state, parameters=parameters)
            optimization.add_listener(lot_creation_listener)
            lot_creation_thread.start()
        except Exception as e:
            traceback.print_exc()
            error_msg = str(e)
    return lot_creation_thread is not None, error_msg, info_msg


# Swimlane related callbacks

clientside_callback(
    ClientsideFunction(
        namespace="createlots",
        function_name="showLotsSwimlane"
    ),
    Output("lots2-lots-swimlane", "title"),
    Input("lots2-lots-data", "data"),
    State("lots2-lots-swimlane", "id"),
    State("lots2-process-selector", "value"),
    State("lots2-swimlane-mode", "value")
)

# TODO move to components.py?
clientside_callback(
    ClientsideFunction(
        namespace="createlots",
        function_name="setLotsSwimlaneMode"
    ),
    Output("lots2-lotsview-header", "title"),
    Input("lots2-swimlane-mode", "value")
)


def target_values_from_settings(process: str, period: tuple[datetime, datetime], plants: list[int], use_lot_range: bool, components: list[Component]|None) -> tuple[ProductionTargets|None, bool, str|None]:
    """
    :return: targets, indicator if default values have been changed, message
    """
    message = None
    if components is None:
        return None, False, None

    #all components for this plant
    components_by_plant = {plant: [c for c in components if c.get("props").get("data-plant") == str(plant)] for plant in plants}
    component_by_plant = {plant: cmps[0] if len(cmps) > 0 else None for plant, cmps in components_by_plant.items()}
    if None in component_by_plant.values():  # Need a component for every process plant # why?
        return None, False, None

    def plant_included(plant0: int) -> bool:
        # the structure per plant is something like this: <checkbox/><div (plant_element)/><div data-plant=plant.id><input tons></div>,
        # therefore components[components.index(component_by_plant.get(plant0)) - 2] is the checkbox indicating if the plant is active
        return len(components[components.index(component_by_plant.get(plant0)) - 2].get("props").get("children").get("props").get("value")) > 0

    plant_active: dict[int, bool] = {plant: plant_included(plant) for plant in plants}

    def plant_get_lot_range(plant0: int) -> tuple[float|None, float|None]:
        plant_components = components_by_plant[plant0]
        min_component = next(c for c in plant_components if c.get("props").get("className") == "lot2-size-min")
        max_component = next(c for c in plant_components if c.get("props").get("className") == "lot2-size-max")
        min_val = None
        max_val = None
        try:
            min_val = float(min_component.get("props").get("children").get("props").get("value"))
        except TypeError:
            pass
        try:
            max_val = float(max_component.get("props").get("children").get("props").get("value"))
        except TypeError:
            pass
        if max_val == 0:
            return None, None
        return min_val, max_val

    try:
        try:
            target_values: dict[int, float] = {plant: float(c.get("props").get("children").get("props").get("value")) for plant, c in component_by_plant.items()
                                         if plant_active[plant]}
        except TypeError:
            message = "Target production: enter a value"
            return None, False, message
        #for target_value in target_values.values():
        #    if target_value == 0:
        #        message = "Target production has to be > 0"
        #        return None, False, message
        if use_lot_range:
            # first check and return onerror
            plant_lot_ranges: dict[int, tuple[float|None, float|None]] = {plant: plant_get_lot_range(plant) for plant in plants if plant_active[plant]}
            for_removal: list[int] = []
            for plant, lot_range in plant_lot_ranges.items():
                has_min = lot_range[0] is not None
                has_max = lot_range[1] is not None
                if has_min != has_max:
                    message = f"Lot range: only min or max has been set for plant {plant}"
                    break
                if lot_range[1] <= lot_range[0]:
                    message = f"Lot range: max has to be greater than min: min={lot_range[0]}, max={lot_range[1]}"
                    break
                if not has_min:
                    for_removal.append(plant)
            if message is not None:
                return None, False, message
            else:
                for plant in for_removal:
                    plant_lot_ranges.pop(plant)
                targets: dict[int, EquipmentProduction] = {plant: EquipmentProduction(equipment=plant, total_weight=value,
                                                        lot_weight_range=plant_lot_ranges[plant]) for plant, value in target_values.items()}
        else:
            targets: dict[int, EquipmentProduction] = {plant: EquipmentProduction(equipment=plant, total_weight=value,
                                                    lot_weight_range=None) for plant, value in target_values.items()}

        changed_plants = [plant for plant, c in component_by_plant.items() if
                          c.get("props").get("children").get("props").get("value") != c.get("props").get("data-default")
                          and plant_active[plant]]

        return ProductionTargets(process=process, target_weight=targets, period=period), len(changed_plants) > 0, message
    except ValueError as e:
        traceback.print_exc()
        return None, False, str(e)


def performance_models_from_elements(process: str, components: list[Component]|None) -> list[PlantPerformanceModel]:
    models = [model for model in state.get_plant_performance_models() if process in model.applicable_processes_and_plants()[0]]
    if components is None:
        return models
    model_components: dict[str, Component] = {comp.get("props").get("data-perfmod"): comp for comp in (c for c in components if c.get("props").get("data-perfmod") is not None) }

    def is_active(element: Component) -> bool:
        # components[components.index(component_by_plant.get(plant0)) + 1] is the checkbox indicating if the plant is active
        return len(element.get("props").get("children").get("props").get("value")) > 0

    active_model_ids: list[str] = [model for model, element in model_components.items() if is_active(element)]
    return [model for model in models if model.id() in active_model_ids]


class KillableOptimizationThread(threading.Thread):

    def __init__(self, process: str, snapshot: datetime, optimization: LotsOptimizer[any], num_iterations: int|None=None):
        super().__init__(name=lot_creation_thread_name)
        self._kill = threading.Event()
        self.daemon = True  # Allow main to exit even if still running.
        self._optimization = optimization
        self._process: str = process
        self._snapshot: datetime = snapshot
        self._iterations: int = num_iterations

    def kill(self):
        self._kill.set()

    def process(self):
        return self._process

    def snapshot(self):
        return self._snapshot

    def num_iterations(self):
        return self._iterations

    def run(self):
        return self._optimization.run(max_iterations=self._iterations)


