from itertools import groupby

import numpy as np

import threading
import traceback
from calendar import monthrange  # , Day  # Python 3.12
from datetime import datetime, timedelta, date, tzinfo, timezone
from typing import Any, Sequence, Literal, Mapping

import dash
from dash import html, dcc, callback, Output, Input, clientside_callback, ClientsideFunction, State, ALL
from dash.development.base_component import Component

from dynreact.auth.authentication import dash_authenticated
from dynreact.base.InterruptedException import InterruptedException
from dynreact.base.LongTermPlanning import LongTermPlanning
from dynreact.base.PlantAvailabilityPersistence import PlantAvailabilityPersistence
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.ModelUtils import ModelUtils
from dynreact.base.model import LongTermTargets, EquipmentAvailability, StorageLevel, Storage, Equipment, \
    PlannedWorkingShift, MidTermTargets, ProductionTargets, MaterialCategory, Lot
from pydantic import TypeAdapter

from dynreact.app import state, config
from dynreact.gui.gui_utils import GuiUtils
from dynreact.gui.pages.plants_graph import plants_graph, default_stylesheet
from dynreact.gui.pages.session_state import get_date_range

dash.register_page(__name__, path="/ltp")
translations_key = "ltp"


ltp_thread_name = "long-term-planning"
ltp_thread: threading.Thread|None = None

allowed_shift_durations: list[int] = [1, 2, 4, 8, 12, 24, 48, 72, 168]
solution_separator = "__x__"


# TODO storage initialization from snapshot
def layout(*args, **kwargs):
    horizon_weeks: int = int(kwargs.get("weeks", 4))    # planning horizon in weeks
    total_production: float = kwargs.get("total", 100_000)
    start_date0: datetime = DatetimeUtils.parse_date(kwargs.get("starttime"))
    if start_date0 is None:
        start_date0 = next_month()
    start_date = f"{start_date0.year:4d}-{start_date0.month:2d}-{start_date0.day:2d}".replace(" ", "0")
    num_processes = len(state.get_site().processes)
    return html.Div([
        html.H1("Long term planning", id="ltp-title"),
        # ======== Control panel ============
        html.Div([
            html.Div("Control Panel"),
            html.Div([
                # Start time block
                html.Div([
                    html.Div("Start time", title="Specify the planning start time"),
                    html.Div([
                        html.Div(dcc.RadioItems(id="ltp-start-time-selection", inline=True, value="now", className="lots2-checkbox",
                                    options=[{"value": "now", "label": "Now ", "title": "Last snapshot"}, {"value": "nextmonth", "label": "Next month "}, {"value": "other", "label": "Other "}])),
                        dcc.Input(type="date", id="ltp-start-time", value=start_date, disabled=True)
                    ])
                    #dcc.DatePickerSingle(id="ltp-start-time", date=start_date)
                ], className="ltp-starttime-block"),
                html.Div([
                    html.Div("Previous solution", title="Specify the previous solution for initialization"),
                    # XXX a select element with optgroups for the start dates would be preferable here,
                    # but does not work in dash: https://community.plotly.com/t/how-to-access-values-from-html-select/5089/12
                    dcc.Dropdown(id="ltp-prev-solution", options=[], style={"width": "18em"})
                ], className="ltp-prev-sol-block", id="ltp-prev-solution-container", hidden=True),
                ## Horizon (weeks) block
                #html.Div([
                #    html.Div("Time horizon (weeks)", title="Specify the planning horizon in weeks"),
                #    html.Div([
                #        dcc.Input(type="range", id="ltp-horizon-weeks", min=1, max=4, step=1, value=horizon_weeks),
                #        html.Div(horizon_weeks, id="ltp-horizon-weeks-value")
                #    ], className="ltp-horizon-widget", title="Specify the planning horizon in weeks")
                #], className="control-panel-entry"),
                html.Div([
                    html.Div("End time", title="Specify the planning interval end time"),
                    dcc.Input(type="date", id="ltp-end-time", disabled=True)
                ], className="control-panel-entry"),
                html.Div([
                    html.Div("Frozen lots", title="Respect lots already defined in the current snapshot?"),
                    html.Div(dcc.Checklist(options=[{"value": "", "label": "Respect lots"}], value=[""], id="ltp-frozen-lots"), title="Respect lots already defined in the current snapshot?"),
                ], id="ltp-frozen-lots-container", className="hidden"),  # toggle between hidden and  control-panel-entry
                html.Div([
                    html.Div("Shift duration (hours)", title="Specify the duration of a single shift. The planning algorithm will assign target production values per shift."),
                    html.Div([
                        dcc.Input(type="range", id="ltp-shift-hours", min=0, max=len(allowed_shift_durations)-1, step=1, value=3),
                        html.Div(8, id="ltp-shift-hours-value")
                    ], className="ltp-horizon-widget", title="Specify the duration of a single shift. The planning algorithm will assign target production values per shift.")
                ], className="control-panel-entry"),
                html.Div(html.Button("Structure Portfolio", className="dynreact-button", id="ltp-structure-btn")),
                html.Div(html.Button("Storages initialization", className="dynreact-button", id="ltp-storages-btn")),
                html.Div(dcc.Checklist(options=[{"value": "", "label": "Store results"}], value=[""], id="ltp-results-store"), title="Store result?"),
                html.Div([
                    html.Button("Start", className="dynreact-button", id="ltp-start", disabled=True),
                    html.Button("Stop", className="dynreact-button", id="ltp-stop", disabled=True)
                ], className="flex"),
                html.Div([
                    html.Progress(),
                    html.Div("Optimization running")
                ], id="ltp-running-indicator", hidden=True),
                #html.Div([
                #    html.Div("New result"),
                #    html.Div(id="ltp-result-id"),
                #], id="ltp-result-container", className="ltp-result-container", hidden=True),
                html.Div(id="ltp-result-alert")
            ]),
        ], className="control-panel"),
        # ======== Initial values panel ============
        html.Div([
            html.Div("Initialization"),
            html.Div([
                html.Div([  # this extra layer is only there to avoid applying the control panel styles for subelements to the div below
                    html.Div([
                        html.H3("Equipment availabilities"),
                        html.Div("To be defined", id="ltp-init-availabilities-result", className="ltp-init-processes",
                                title="Click equipment icons below to adapt the availabilities.")
                    ], className="ltp-settings-card"),
                    html.Div([
                        html.H3("Process capacities"),
                        html.Div("To be defined", id="ltp-init-process-capacities", className="ltp-init-processes"),
                        html.Div([
                            html.Div("Min: ", title="The minimum capacity process determines the target production. Some processes may be ignored in this consideration."),
                            html.Div(id="ltp-process-min-capacity", title="The minimum capacity process determines the target production. Some processes may be ignored in this consideration.")
                        ], className="ltp-process-min-capacity")
                    ], className="ltp-settings-card"),
                    html.Div([
                        html.H3("Material structure"),
                        html.Div([
                            html.Div("To be defined", id="ltp-init-structure-total"),
                            html.Div(id="ltp-init-structure-result")
                        ], className="ltp-init-structure-body")
                    ], id="ltp-init-structure", className="ltp-settings-card"),
                    html.Div([
                        html.H3("Initial storage content"),
                        html.Div([
                            html.Div("To be defined", id="ltp-init-storages-total"),
                            html.Div(id="ltp-init-storages-result", className="ltp-init-storages-result")
                        ], className="ltp-init-structure-body")
                    ], id="ltp-init-storages", className="ltp-settings-card")
                ], className="ltp-init-panel2")
            ])
        ], className="control-panel", id="ltp-initialization"),
        # ======== Historic production panel ============
        html.Div([
            html.Div("Past production"),
            html.Div([
                html.Div([
                    html.Div([
                        html.Span("Finished material in time interval "),
                        html.Span(id="ltp-history-start"),
                        html.Span(" - "),
                        html.Span(id="ltp-history-end"),
                        html.Span(": "),
                        html.Span(id="ltp-history-total"),
                        html.Span("t. Material structure: "),
                    ]),
                    html.Br(),
                    html.Div(id="ltp-material-history-widget")
                ])
            ], style={"display": "flex", "justify-content": "flex-start", "padding-top": "0.5em", "padding-bottom": "0.5em"})
        ], className="hidden", id="ltp-history-panel"),  # class toggles between hidden and control-panel
        # ======== Frozen lots panel ============
        html.Div([
            html.Div("Frozen lots"),
            html.Div([
                html.Div([
                    html.Div([
                        html.Span("Total material planned in frozen lots: "),
                        html.Span(id="ltp-frozen-lot-total"),
                        html.Span("t. Material structure: "),
                    ]),
                    html.Br(),
                    html.Div(id="ltp-frozen-lots-structure-widget")
                ])
            ], style={"display": "flex", "justify-content": "flex-start", "padding-top": "0.5em", "padding-bottom": "0.5em"})
        ], className="hidden", id="ltp-frozen-lots-panel"),  # class toggles between hidden and control-panel
        # ======== Process panel ============
        html.Div([
            html.Div("Process Panel"),
            html.Div([
                plants_graph("ltp-plants-graph", style={"width": str(num_processes * 10) + "em", "height": "500px"},
                             stylesheet=graph_stylesheets(start_date0.date(), (start_date0 + timedelta(days=30)).date()), *args, **kwargs)
            ], style={"display": "flex", "justify-content": "flex-start"})
        ], className="control-panel", id="ltp-process-panel"),
        # ======== Popups and hidden elements =========
        structure_portfolio_popup(total_production),
        plant_calendar_popup(),
        storage_init_popup(kwargs.get("snapshot")),   # TODO better selection of snapshot
        storage_structure_portfolio_popup(),
        ## stores information about the last start time and horizon for which material properties have been set,
        ## in the format {"startTime": startTime, "horizon": horizon}
        #dcc.Store(id="ltp-material-settings", storage_type="memory"),

        dcc.Store(id="ltp-material-setpoints-user", storage_type="memory"),      # material structure configured explicitly by user
        dcc.Store(id="ltp-material-setpoints-prev", storage_type="memory"),  # material structure from selected previous solution
        dcc.Store(id="ltp-material-setpoints", storage_type="memory"),       # consolidated material structure

        dcc.Store(id="ltp-prev-solution-store", storage_type="memory"),  # selected previous solution
        dcc.Store(id="ltp-historic-prod", storage_type="memory"),   #  Record<{name: string; classes: Record<{string: {name: string; weight: number;}}> }>
        dcc.Store(id="ltp-dummy-undefined", storage_type="memory"),
        dcc.Store(id="ltp-frozen-lot-structure", storage_type="memory"), #  Record<{name: string; classes: Record<{string: {name: string; weight: number;}}> }>
        # Set when the user clicks on a plant node in the graph
        dcc.Store(id="ltp-selected_plant", storage_type="memory"),
        # contains a list of json serialized PlantAvailability objects for the currently selected plant, or None,
        # as input for the calendar popup
        dcc.Store(id="ltp-plant-availability", storage_type="memory"),
        # dict[date as string, e.g. "2023-12-01" => hours]
        dcc.Store(id="ltp-plant-shifts", storage_type="memory"),
        # contains a json serialized PlantAvailability object for the currently selected plant, or None,
        # as output from the calendar popup
        dcc.Store(id="ltp-availability-buffer", storage_type="memory"),
        dcc.Store(id="ltp-storage-levels"),  # None or {storage id: StorageLevel}
        dcc.Store(id="ltp-stg-materials-selected", storage_type="memory"),  # storage selected for editing mateiral structure
        dcc.Store(id="ltp-stg-materials-update", storage_type="memory"),    # updated structure for selected storage
        dcc.Store(id="ltp-min-capacity", storage_type="memory", data=100_000),
        dcc.Store(id="ltp-result-message", storage_type="memory"),
        dcc.Store(id="ltp-start-end", storage_type="memory"),   # [start date, end date], e.g. ["2026-05-01", "2026-06-01"]
        dcc.Interval(id="ltp-interval", n_intervals=3_600_000),  # for polling when optimization is running
    ], id="ltp")


def structure_portfolio_popup(initial_production: float):
    return html.Dialog(
        html.Div([
            html.H3("Structure Portfolio"),
            html.Div([
                html.Div("Total production / t:"),
                dcc.Input(type="number", id="ltp-production-total", min="0", step="1000", value=initial_production)
            ], className="ltp-production-total"),
            # materials_table()
            html.Div(id="ltp-materials-grid"),
            html.Div([
                html.Button("Accept", id="ltp-materials-accept", className="dynreact-button"),
                html.Button("Reset", id="ltp-materials-reset", className="dynreact-button"),
                html.Button("Cancel", id="ltp-materials-cancel", className="dynreact-button")
            ], className="ltp-materials-buttons")
        ], title=""),
        id="ltp-structure-dialog", className="dialog-filled", open=False)


# TODO need to remember for which storage the popup was opened
def storage_structure_portfolio_popup():
    return html.Dialog(
        html.Div([
            html.H3("Storage structure"),  # TODO show storage name
            # materials_table()
            html.Div(id="ltp-stg-materials-grid"),
            html.Div([
                html.Button("Accept", id="ltp-stg-materials-accept", className="dynreact-button"),
                html.Button("Reset", id="ltp-stg-materials-reset", className="dynreact-button"),
                html.Button("Cancel", id="ltp-stg-materials-cancel", className="dynreact-button")
            ], className="ltp-materials-buttons")
        ], title=""),
        id="ltp-stg-structure-dialog", className="dialog-filled", open=False)


def plant_calendar_popup():
    return html.Dialog(
        html.Div([
            html.H3("Plant availability"),
            html.Div([
                html.Div("Selected plant:"),
                html.Div(id="ltp-calendar-plant"),
                html.Div(" Start time:"),
                html.Div(id="ltp-calendar-start-time")
            ], className="ltp-calendar-plant-row"),
            # materials_table()
            html.Div(id="ltp-calendar-grid"),
            html.Div([
                html.Button("Save", id="ltp-calendar-accept", className="dynreact-button"),
                html.Button("Clear", id="ltp-calendar-clear", className="dynreact-button", title="Delete all entries for this plant and the selected period."),
                html.Button("Cancel", id="ltp-calendar-cancel", className="dynreact-button")
            ], className="ltp-materials-buttons")
        ], title=""),
        id="ltp-calendar-dialog", className="dialog-filled", open=False)


def storage_init_popup(snapshot: str|None):
    # TODO handle timezone
    start_date, end_date, snap_options, selected_snap = get_date_range(snapshot)  # : tuple[date, date, list[datetime], str]
    return html.Dialog(
        html.Div([
            html.H3("Storages status"),
            html.Div([
                html.Div([html.Div("Snapshot: ", id="ltp-storage-snapshot"),
                          dcc.Dropdown(id="ltp-storage-snapshots-selector", className="snap-select",
                                       options=snap_options, value=selected_snap)]),
                html.Div([html.Div("Selection range: ", id="ltp-storage-snapshot-selection_range"),
                          dcc.DatePickerRange(id="ltp-storage-snapshots-date-range", display_format="YYYY-MM-DD",
                                              start_date=start_date, end_date=end_date)])
            ], className="snapshots-selector-row"),
            html.Br(),
            html.Div([
                html.Button("Init from snapshot", id="ltp-storageinit-snap-trigger", className="dynreact-button",
                                title="Initialize storage levels according to selected snapshot. " + \
                                      "The individual storage levels can then be edited by clicking on the respective storage in the visualization below."),
                html.Button("Init half filled", id="ltp-storageinit-half-trigger", className="dynreact-button",
                                title="Initialize storages such that they are half-filled, with default shares for each material class. " + \
                                      "The individual storage levels can then be edited by clicking on the respective storage in the visualization below."),
                html.Button("Clear storages", id="ltp-storageinit-clear", className="dynreact-button",
                                title="Clear storage initial values."),
            ], className="ltp-materials-buttons"),
        ], title=""),
        id="ltp-storageinit-dialog", className="dialog-filled", open=False)


def graph_stylesheets(start_date: date, end_date: date):
    persistence = state.get_availability_persistence()
    available_plants: list[int] = persistence.plant_data(start_date, end_date)
    if len(available_plants) == 0:
        return default_stylesheet(background_color="darkorange")
    selector = ",".join(["node.plant-node[id = \"plant_" + str(p) + "\"]" for p in available_plants])
    additional_style = [{
        "selector": selector,
        "style": {
            "background-color": "green"
        }
    }]
    return default_stylesheet(background_color="darkorange") + additional_style


def next_month() -> datetime:
    try:
        start_date0 = next(state.get_snapshot_provider().snapshots(datetime(year=1900, month=1, day=1, tzinfo=timezone.utc),
                                                    datetime(year=3000, month=1, day=1, tzinfo=timezone.utc), order="desc"))
    except StopIteration:
        start_date0 = state.replace_timezone(DatetimeUtils.now())
    start_date0 = (start_date0.replace(day=1, minute=0, second=0, microsecond=0) + timedelta(days=32)).replace(day=1)
    return start_date0


# Moved to js
"""
def materials_table():
    materials = state.get_site().materials
    columns: int = len(materials)
    rows: int = max(len(cat.classes) for cat in materials)
    material_divs = []
    column: int = 0   # 1-based
    for material_category in materials:
        column = column + 1
        material_divs.append(
            html.Div(material_category.name if material_category.name is not None else material_category.id, className="ltp-material-category",
                     style={"grid-column-start": str(column), "grid-row-start": str(1)}))
        row: int = 1
        for material_class in material_category.classes:
            row = row + 1
            data_dict = {"data-category": material_category.id, "data-material": material_class.id}
            if material_class.is_default:
                data_dict["data-default"] = "true"
            if material_class.default_share is None:
                data_dict["data-defaultshare"] = str(material_class.default_share)
            material_name = html.Div(material_class.name if material_class.name is not None else material_class.id)
            # TODO handle stepMismatch (should be ignored) https://developer.mozilla.org/en-US/docs/Web/API/ValidityState/stepMismatch
            material_input = html.Div(dcc.Input(type="number", min="0", step="1000"))
            material_parent = html.Div([material_name, material_input], className="ltp-material-class",
                    style={"grid-column-start": str(column), "grid-row-start": str(row)},
                    *data_dict,)
            material_divs.append(material_parent)
    return html.Div(material_divs, className="ltp-materials-grid", style={"grid-template-columns": f"repeat({columns}, 1fr)"})
"""

@callback(Output("ltp-horizon-weeks-value", "children"),
          Input("ltp-horizon-weeks", "value"))
def horizon_changed(horizon: int | str | None) -> str:
    try:
        return str(int(horizon))
    except:
        return None

@callback(Output("ltp-shift-hours-value", "children"),
          Input("ltp-shift-hours", "value"))
def shift_duration_changed(duration_idx: int | str | None) -> str:
    try:
        idx = int(duration_idx)
        return str(allowed_shift_durations[idx])
    except:
        return None

@callback(Output("ltp-start-time", "value"),
          Output("ltp-start-time", "disabled"),
          Output("ltp-end-time", "disabled"),
          Output("ltp-start-end", "data"),
          Output("ltp-end-time", "value"),
          Output("ltp-prev-solution", "options"),
          Output("ltp-prev-solution", "value"),
          Output("ltp-prev-solution-container", "hidden"),
          Input("ltp-start-time-selection", "value"),
          Input("ltp-start-time", "value"),
          Input("ltp-end-time", "value"),
          Input("ltp-prev-solution", "value"),
          State("selected-snapshot", "data"),)
def start_time_changed(start_time_type: Literal["now", "nextmonth", "other"]|None, start_time: datetime|str, end_time: datetime|str, previous_solution: str|None, snapshot: str|None):
    if not start_time_type or not dash_authenticated(config):
        return dash.no_update, True, True, [None, None], None, [], None, True
    if previous_solution == "":
        previous_solution = None
    changed = GuiUtils.changed_ids()
    start_disabled = start_time_type != "other"
    start_type_changed = "ltp-start-time-selection" in changed or (len(changed) <= 1 and all(c == "" for c in changed))
    results_persistence = state.get_results_persistence_aggregate()
    prev_options = dash.no_update
    prev_hidden = start_time_type != "now"
    if start_type_changed:
        if start_time_type == "now":
            start_time = DatetimeUtils.parse_date(snapshot)
            if start_time is None:
                start_time = state.as_timezone(DatetimeUtils.now())
            all_start_times = results_persistence.start_times_ltp(start=start_time-timedelta(weeks=8), end=start_time, sort="desc")
            solutions_by_start_times: dict[datetime, list[str]] = {s: results_persistence.solutions_ltp(s) for s in all_start_times}
            applicable_solutions: dict[datetime, list[str]] = {}
            for sol_start, sol_ids in solutions_by_start_times.items():
                if len(sol_ids) == 0:
                    continue
                sol_iter = reversed(sol_ids)
                while True:
                    try:
                        sol_id = next(sol_iter)
                        result = results_persistence.load_ltp(sol_start, sol_id)
                        if result is None:
                            continue
                        is_applicable = result[0].period[1] > start_time
                        if is_applicable:
                            applicable_solutions[sol_start] = sol_ids
                            break
                        month_start = start_time.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
                        if result[0].period[1] <= month_start:  #  if sol_start is in previous month break
                            break
                    except StopIteration:
                        break
            multiple_start_times = len(applicable_solutions) > 1
            all_solutions = ((sol_start, sol_id) for sol_start, sol_ids in applicable_solutions.items() for sol_id in sol_ids)
            prev_options = [{"value": "", "label":""}] + [{"value": f"{DatetimeUtils.format(sol_start)}{solution_separator}{sol_id}", "label": f"{state.as_timezone(sol_start).strftime('%Y-%m-%d')}: {sol_id}",
                                "title": f"Start time: {DatetimeUtils.format(state.as_timezone(sol_start), use_zone=False)}, solution id: {sol_id}"} for sol_start, sol_id in all_solutions]
            if previous_solution is None or not any(opt["value"] == previous_solution for opt in prev_options):
                previous_solution = None if len(prev_options) <= 1 else prev_options[1]["value"]
        elif start_time_type == "nextmonth":
            start_time = next_month()
        else:
            start_time = DatetimeUtils.parse_date(start_time)
    else:
        start_time = DatetimeUtils.parse_date(start_time)
    if "ltp-prev-solution" in changed or (start_type_changed and start_time_type == "now"):
        start_end = None
        if previous_solution is not None:
            separator_index = previous_solution.index(solution_separator)
            prev_start = DatetimeUtils.parse_date(previous_solution[:separator_index])
            prev_sol_id = previous_solution[separator_index + 5:]
            # determine time range from previous solution
            if prev_start is not None:
                try:
                    prev_result = state.get_results_persistence_aggregate().load_ltp(prev_start, prev_sol_id)
                    period = prev_result[0].period
                    end_time = period[1]
                    if end_time > start_time:
                        start_end = (start_time.date(), end_time.date())
                except:
                    pass
        if start_end is None:
            next_month_start = (start_time.replace(day=1, minute=0, second=0, microsecond=0) + timedelta(days=32)).replace(day=1)
            start_end = (start_time.date(), next_month_start.date())
        if "ltp_prev_solution" in changed:
            previous_solution = dash.no_update
    elif "ltp-end-time" in changed:
        end_time = DatetimeUtils.parse_date(end_time)
        if end_time is None or end_time <= start_time:
            start_end = [None, None]
        else:
            start_end = [start_time.date(), end_time.date()]
        end_time = dash.no_update
    elif start_time == "now":
        prev_options = dash.no_update
        start_end = dash.no_update
        prev_hidden = False
    else:
        if not isinstance(start_time, datetime):
            start_end = dash.no_update
        else:
            end_time = DatetimeUtils.parse_date(end_time)
            if end_time is None or end_time <= start_time:
                end_time = (start_time.replace(day=1, minute=0, second=0, microsecond=0) + timedelta(days=32)).replace(day=1)
            start_end = (start_time.date(), end_time.date())
    end_disabled = start_time_type == "now" and previous_solution is not None
    if start_end is None or (isinstance(start_end, Sequence) and any(e is None for e in start_end)):
        return dash.no_update, start_disabled, end_disabled, [None, None], None, [], None, True
    if isinstance(start_time, datetime):
        start_time = f"{start_time.year:4d}-{start_time.month:2d}-{start_time.day:2d}".replace(" ", "0")
    end_time = dash.no_update if start_end == dash.no_update or end_time == dash.no_update else start_end[1] if start_end is not None else None
    return start_time, start_disabled, end_disabled, start_end, end_time, prev_options, previous_solution, prev_hidden


# TODO
"""
@callback(Output("lots2-current_snapshot", "children"),
          Input("ltp-structure-btn", "n_clicks"))  # same button that opens the
def snapshot_changed(snapshot: datetime | None) -> str:
    if snapshot is None:
        return ""
    return str(snapshot)
"""

@callback(
    Output("ltp-production-total", "value"),
          Input("ltp-materials-cancel", "n_clicks"),
          Input("ltp-min-capacity", "data"),
          State("ltp-material-setpoints", "data"),
          config_prevent_initial_callbacks=True)
def material_menu_canceled(_, min_capacity: float, setpoints: dict[str, float]) -> float:
    if "ltp-min-capacity" in GuiUtils.changed_ids():
        return round(min_capacity) if min_capacity is not None and np.isfinite(min_capacity) else dash.no_update
    total_amount = _get_total_selected_amount(setpoints)
    if total_amount is None:
        return dash.no_update
    return total_amount


def _get_total_selected_amount(setpoints: dict[str, float]) -> float|None:
    if setpoints is None or len(setpoints) == 0:
        return None
    first_category = state.get_site().material_categories[0]
    total_amount = sum(setpoints.get(mat.id, 0) for mat in first_category.classes)
    return total_amount


@callback(
    Output("ltp-prev-solution-store", "data"),
          Input("ltp-prev-solution", "value"),
          Input("ltp-start-time-selection", "value"))
def prev_solution_changed(prev_solution: str|None, start_time_type: Literal["now", "nextmonth", "other"]|None) -> dict[str, Any]|None:
    if not dash_authenticated(config) or start_time_type != "now" or not prev_solution or solution_separator not in prev_solution:
        return None
    sep = prev_solution.index(solution_separator)
    start_time = DatetimeUtils.parse_date(prev_solution[:sep])
    if start_time is None:
        return None
    sol_id = prev_solution[sep + len(solution_separator):]
    result, _ = state.get_results_persistence_aggregate().load_ltp(start_time, sol_id)
    json = result.model_dump(exclude_unset=True, exclude_none=True)
    return json

@callback(
        Output("ltp-historic-prod", "data"),
        Output("ltp-material-setpoints-prev", "data"),
        Input("ltp-prev-solution-store", "data"),
        State("ltp-start-end", "data"))
def prev_solution_changed(prev_solution: dict[str, Any]|None, start_end: tuple[str, str]|None):
    if not prev_solution or not start_end:
        return None, None
    targets = MidTermTargets.model_validate(prev_solution)
    previous_start = targets.period[0]
    new_start = DatetimeUtils.parse_date(start_end[0])
    material_targets: dict[str, float] = targets.production_targets
    history_reader = state.get_history_reader()
    final_processes = [proc for proc in state.get_site().processes if proc.next_steps is None or len(proc.next_steps) == 0]
    final_process_ids = [p.name_short for p in final_processes]
    finished_materials: list[ProductionTargets] = [history_reader.production_aggregate(
            proc, previous_start, new_start, equipment=[e.id for e in state.get_site().get_process_equipment(proc, do_raise=True)]) for proc in final_process_ids]

    conditional_final_equipment = [e for e in state.get_site().equipment if e.process not in final_process_ids and any(isinstance(stg, Mapping) and "DONE" in stg for stg in e.storages_out)]
    # group conditional equipments first by process then by material classes
    cond_eq_by_proc: dict[str, Sequence[Equipment]] = {proc: tuple(proc_eq) for proc, proc_eq in groupby(conditional_final_equipment, lambda e: e.process)}
    group_by_out_mat = lambda e: next(stg for stg in e.storages_out if isinstance(stg, Mapping) and "DONE" in stg)["DONE"]
    for proc, proc_eq in cond_eq_by_proc.items():
        eq_by_mat: dict[tuple[str], list[Equipment]] = {mat: list(mat_eq) for mat, mat_eq in groupby(proc_eq, group_by_out_mat)}
        for mat_group, mat_eq in eq_by_mat.items():
            cond_prod = history_reader.production_aggregate(proc, previous_start, new_start, equipment=[e.id for e in mat_eq], material_filter=mat_group)
            finished_materials.append(cond_prod)
    finished_material = ModelUtils.merge_targets(finished_materials, require_same_process=False, require_same_period=False)

    target_structure: dict[str, float] = dict(material_targets)
    historic_prod = None
    mat_cats = state.get_site().material_categories
    if finished_material.material_weights and len(mat_cats) > 0:
        mat_done = finished_material.material_weights
        first_cat_sum_done = sum(mat_done.get(cl.id, 0) for cl in mat_cats[0].classes)
        first_cat_sum_planned = sum(target_structure.get(cl.id, 0) for cl in mat_cats[0].classes)
        mat_missing = first_cat_sum_done < first_cat_sum_planned
        if not mat_missing:
            target_structure = {mat: 0 for mat in target_structure.keys()}
        else:
            # step 1: find individual classes where more has been produced than required already
            surpassed_mat: list[str] = [mat for mat, value_done in mat_done.items() if value_done > target_structure.get(mat, 0)]
            surpassed_cats: list[MaterialCategory] = [cat for cat in mat_cats if any(cl.id in surpassed_mat for cl in cat.classes)]
            surplus_by_cat: dict[str, float] = {cat.id: sum(mat_done[cl.id] - target_structure.get(cl.id) for cl in cat.classes if cl.id in surpassed_mat) for cat in surpassed_cats}
            for mat, weight in mat_done.items():
                if mat in target_structure:
                    target_structure[mat] = max(target_structure[mat] - weight, 0.)
            # step 2: reduce target amount for remaining material classes of the category by existing surplus
            for cat, surplus in surplus_by_cat.items():
                remaining_mat: list[str] = [cl.id for cl in next(ct for ct in mat_cats if ct.id == cat).classes if cl.id not in surpassed_mat]
                sum_remaining = sum(target_structure.get(mat, 0.) for mat in remaining_mat)
                for mat in remaining_mat:
                    share = target_structure.get(mat, 0.) / sum_remaining
                    reduction = surplus * share
                    target_structure[mat] = target_structure[mat] - reduction
        historic_prod = {}
        for cat in state.get_site().material_categories:
            classes = {cl.id: {"name": cl.name or cl.id, "weight": mat_done[cl.id]} for cl in cat.classes if cl.id in mat_done}
            if len(classes) == 0:
                continue
            cat_entry = {"name": cat.name or cat.id, "classes": classes}
            historic_prod[cat.id] = cat_entry
    return historic_prod, target_structure

@callback(
        Output("ltp-history-panel", "className"),
        Output("ltp-history-start", "children"),
        Output("ltp-history-end", "children"),
        Output("ltp-history-total", "children"),
        Input("ltp-historic-prod", "data"),
        State("ltp-prev-solution", "value"),
        State("ltp-start-end", "data"))
def historic_production_changed(production: dict[str, Any]|None, prev_solution: str|None, start_end: tuple[str, str]|None):
    prev_start_time = None
    if prev_solution is not None:
        sep = prev_solution.index(solution_separator)
        prev_start_time = state.as_timezone(DatetimeUtils.parse_date(prev_solution[:sep]))
    if production is None or len(production) == 0 or prev_solution is None or prev_start_time is None:
        return "hidden", None, None, None
    start = DatetimeUtils.parse_date(start_end[0])
    first_cat = next(iter(production.keys()))
    total_production = sum(cl["weight"] for cl in production[first_cat]["classes"].values())
    total_format = f"{total_production:.2f}" if total_production is not None else ""
    return "control-panel", DatetimeUtils.format(prev_start_time, use_zone=False), DatetimeUtils.format(start, use_zone=False), total_format

clientside_callback(
    ClientsideFunction(
        namespace="lots2",
        function_name="setBacklogStructureOverview"
    ),
    Output("ltp-material-history-widget", "title"),
    Input("ltp-historic-prod", "data"),   # dict[str, dict[str, float]]
    Input("ltp-dummy-undefined", "data"),
    State("ltp-material-history-widget", "id"),
)

@callback(
        Output("ltp-frozen-lots-container", "className"),
        Output("ltp-frozen-lots-panel", "className"),
        Input("ltp-start-time-selection", "value"))
def toggle_frozen_lots(start_time_type: Literal["now", "nextmonth", "other"]|None):
    if start_time_type == "now":
        return "control-panel-entry", "control-panel"
    return "hidden", "hidden"


"""
@callback(Output("ltp-material-settings", "data"),
          Input("ltp-materials-accept", "n_clicks"),
          State("ltp-start-end", "data"),
          config_prevent_initial_callbacks=True)
def material_settings_accepted(_, start_time: [str, str]) -> str:
    if start_time is None or DatetimeUtils.parse_date(start_time[0]) is None:
        return {}
    return {"start_time": start_time[0], "end_time": start_time[1]}
"""

clientside_callback(
    ClientsideFunction(
        namespace="ltp",
        function_name="initMaterialGrid"
    ),
    Output("ltp-materials-grid", "title"),
    Input("ltp-structure-btn", "n_clicks"),    # open structure popup
    Input("ltp-materials-reset", "n_clicks"),  # reset structure popup
    Input("ltp-production-total", "value"),
    State("ltp-material-setpoints", "data"),   # active setpoints
    State("ltp-materials-grid", "id"),
)

@callback(
        Output("ltp-material-setpoints", "data"),
        Input("ltp-material-setpoints-user", "data"),
        Input("ltp-material-setpoints-prev", "data"))
def material_setpoints_changed(setpoints_user: dict[str, float]|None, setpoints_prev: dict[str, float]|None):
    prev_changed = "ltp-material-setpoints-prev" in GuiUtils.changed_ids()
    if prev_changed:
        if not setpoints_prev:
            return dash.no_update
        return setpoints_prev
    return setpoints_user


clientside_callback(
    ClientsideFunction(
        namespace="ltp",
        function_name="getMaterialSetpoints"
    ),
    Output("ltp-material-setpoints-user", "data"),
    Input("ltp-materials-accept", "n_clicks"),
    State("ltp-materials-grid", "id"),
    #config_prevent_initial_callbacks=True
)

clientside_callback(
    ClientsideFunction(
        namespace="ltp",
        function_name="getMaterialSetpoints"
    ),
    Output("ltp-stg-materials-update", "data"),
    Input("ltp-stg-materials-accept", "n_clicks"),
    State("ltp-stg-materials-grid", "id"),
    #config_prevent_initial_callbacks=True
)

clientside_callback(
    ClientsideFunction(
        namespace="ltp",
        function_name="initStorageMaterialGrid"
    ),
    Output("ltp-stg-materials-selected", "data"),  # the currently selected storage for structure editing
    Input({"role": "ltp-stg-structure-btn", "id": ALL}, "n_clicks"),
    State("ltp-storage-levels", "data"),   # {stg id: StorageLevel}
    State("ltp-stg-materials-grid", "id"),
    #config_prevent_initial_callbacks=True
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="showModal"
    ),
    Output("ltp-structure-dialog", "title"),
    Input("ltp-structure-btn", "n_clicks"),
    State("ltp-structure-dialog", "id"),
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="closeModal"
    ),
    Output("ltp-materials-cancel", "title"),
    Input("ltp-materials-cancel", "n_clicks"),
    State("ltp-structure-dialog", "id"),
    State("ltp-materials-cancel", "title"),
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="closeModal"
    ),
    Output("ltp-stg-materials-cancel", "title"),
    Input("ltp-stg-materials-cancel", "n_clicks"),
    State("ltp-stg-structure-dialog", "id"),
    State("ltp-stg-materials-cancel", "title"),
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="closeModal"
    ),
    Output("ltp-materials-accept", "title"),
    Input("ltp-materials-accept", "n_clicks"),
    State("ltp-structure-dialog", "id"),
    State("ltp-materials-accept", "title"),
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="closeModal"
    ),
    Output("ltp-stg-materials-accept", "title"),
    Input("ltp-stg-materials-accept", "n_clicks"),
    State("ltp-stg-structure-dialog", "id"),
    State("ltp-stg-materials-accept", "title"),
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="showModal"
    ),
    Output("ltp-calendar-dialog", "title"),
    Input("ltp-selected_plant", "data"),
    State("ltp-calendar-dialog", "id"),
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="closeModal"
    ),
    Output("ltp-calendar-cancel", "title"),
    Input("ltp-calendar-cancel", "n_clicks"),
    State("ltp-calendar-dialog", "id"),
    State("ltp-calendar-cancel", "title"),
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="closeModal"
    ),
    Output("ltp-calendar-accept", "title"),
    Input("ltp-calendar-accept", "n_clicks"),
    State("ltp-calendar-dialog", "id"),
    State("ltp-calendar-accept", "title"),
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="showModal"
    ),
    Output("ltp-storageinit-dialog", "title"),
    Input("ltp-storages-btn", "n_clicks"),
    State("ltp-storageinit-dialog", "id"),
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="closeModal"
    ),
    Output("ltp-storageinit-clear", "title"),
    Input("ltp-storageinit-clear", "n_clicks"),
    State("ltp-storageinit-dialog", "id"),
    State("ltp-storageinit-clear", "title"),
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="closeModal"
    ),
    Output("ltp-storageinit-half-trigger", "title"),
    Input("ltp-storageinit-half-trigger", "n_clicks"),
    State("ltp-storageinit-dialog", "id"),
    State("ltp-storageinit-half-trigger", "title"),
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="closeModal"
    ),
    Output("ltp-storageinit-snap-trigger", "title"),
    Input("ltp-storageinit-snap-trigger", "n_clicks"),
    State("ltp-storageinit-dialog", "id"),
    State("ltp-storageinit-snap-trigger", "title"),
)


@callback(Output("ltp-calendar-plant", "children"),
          Output("ltp-calendar-start-time", "children"),
          Output("ltp-selected_plant", "data"),
          Input("ltp-plants-graph", "tapNode"),
          State("ltp-start-time", "value"))
def tap_graph_node(tapNode: dict[str, any]|None, start_time: datetime|str):
    if tapNode is None or "data" not in tapNode or not isinstance(tapNode.get("data"), dict) or not dash_authenticated(config):
        return "", "",None
    node_data: dict[str, any] = tapNode.get("data")
    node_id: str = node_data.get("id", "")
    plant_id: int = -1
    try:
        plant_id = int(node_id.replace("plant_", ""))
    except ValueError:
        return "", "",None
    plant = state.get_site().get_equipment(plant_id, do_raise=False)
    if plant is None:
        return "", "",None
    dt = DatetimeUtils.parse_date(start_time)
    dt_formatted = "" if dt is None else dt.strftime("%Y-%m-%d")
    return plant.name_short if plant.name_short is not None else str(plant.id), dt_formatted, plant.id


"""
def _get_start_end_time(start_time: datetime|str, horizon: str|int) -> tuple[date|None, date|None]:
    start_time = DatetimeUtils.parse_date(start_time)
    horizon = int(horizon)
    if start_time is None or horizon <= 0:
        return None, None
    start: date = start_time.date()
    month_info: tuple[int, int] = monthrange(start.year, start.month)  # tuple[calendar.Day, int] from Python 3.12
    end_time = start_time + (timedelta(days=month_info[1]) if horizon == 4 and start.day == 1 else timedelta(weeks=horizon))
    return start, end_time.date()
"""


def _date_range_to_datetime(start: date, end: date) -> tuple[datetime, datetime]:
    return state.replace_timezone(datetime.combine(start, datetime.min.time())), state.replace_timezone(datetime.combine(end, datetime.min.time()))


@callback(Output("ltp-plant-availability", "data"),
        Output("ltp-plant-shifts", "data"),
        Input("ltp-selected_plant", "data"),           # user clicked on a plant node in the graph
        Input("ltp-calendar-clear", "n_clicks"),
        State("ltp-start-end", "data"),
        config_prevent_initial_callbacks=True)
def init_calendar(selected_plant: int|None, _, start_time: [datetime|str|None, datetime|str, None]):
    if selected_plant is None or start_time is None or start_time[0] is None or not dash_authenticated(config):
        return None, None
    selected_plant = int(selected_plant)
    start, end =  [DatetimeUtils.parse_date(start_time[0]), DatetimeUtils.parse_date(start_time[1])]
    if start is None or end is None:
        return None, None
    start, end = (start.date(), end.date())
    availabilities: PlantAvailabilityPersistence = state.get_availability_persistence()
    changed = GuiUtils.changed_ids()
    if "ltp-calendar-clear" in changed:
        availabilities.delete(selected_plant, start, end)
        #return None, None
    av: list[EquipmentAvailability] = availabilities.load(selected_plant, start, end)
    av_json = TypeAdapter(list[EquipmentAvailability]).dump_json(av).decode("utf-8")
    start_dt, end_dt = _date_range_to_datetime(start, end)
    shifts = state.get_shifts_provider().load(selected_plant, start_dt, end_dt)
    shifts_by_days = {}
    for shift in shifts:
        day_start = shift.period[0].replace(hour=0, minute=0, second=0, microsecond=0)
        if day_start not in shifts_by_days:
            shifts_by_days[day_start] = 0
        shifts_by_days[day_start] += shift.worktime.total_seconds()/3600
    shifts_by_days = {day.strftime("%Y-%m-%d"): hours for day, hours in shifts_by_days.items()}
    return av_json, shifts_by_days


clientside_callback(
    ClientsideFunction(
        namespace="ltp",
        function_name="initCalendar"
    ),
    Output("ltp-start-time", "title"),   # dummy
    Input("ltp-plant-availability", "data"),
    Input("ltp-plant-shifts", "data"),
    State("ltp-selected_plant", "data"),
    State("ltp-start-end", "data"),
    State("ltp-calendar-grid", "id")
)

clientside_callback(
    ClientsideFunction(
        namespace="ltp",
        function_name="getAvailabilities"
    ),
    Output("ltp-availability-buffer", "data"),   #  availabilities to Store => then to persistence
    Input("ltp-calendar-accept", "n_clicks"),
    State("ltp-calendar-grid", "id")
)

# TODO update stylesheet also on starttime change => need to check which one changed
@callback(Output("ltp-plants-graph", "stylesheet"),
          Input("ltp-availability-buffer", "data"),
          config_prevent_initial_callbacks=True)
def availabilities_changed(availabilities_json: dict[str, any]|None):   # user clicked the Save button in the calendar popup
    if availabilities_json is None:
        return dash.no_update
    av = EquipmentAvailability.model_validate(availabilities_json)
    persistence = state.get_availability_persistence()
    persistence.store(av)
    return graph_stylesheets(av.period[0], av.period[1])


# TODO consider selected snapshot for init_from_snap
@callback(Output("ltp-storage-levels", "data"),
          Input("ltp-storageinit-snap-trigger", "n_clicks"),
          Input("ltp-storageinit-half-trigger", "n_clicks"),
          Input("ltp-storageinit-clear", "n_clicks"),
          Input("ltp-start-time", "value"),
          Input("ltp-stg-materials-update", "data"),
          State("ltp-storage-levels", "data"),
          State("ltp-stg-materials-selected", "data"),)
          #config_prevent_initial_callbacks=True)
def set_storage_levels(_, __, ___, start_time: datetime|str, storage_update: dict[str, float]|None, levels: str|None, storage_for_update: str|None):
    if not dash_authenticated(config):
        return None
    start_time = DatetimeUtils.parse_date(start_time)
    if start_time is None:
        return dash.no_update
    changed_ids: list[str] = GuiUtils.changed_ids(excluded_ids=[""])
    if "ltp-storageinit-clear" in changed_ids:
        return None
    site = state.get_site()
    storages: dict[str, StorageLevel] = {}
    user_material_update: bool = "ltp-stg-materials-update" in changed_ids and storage_update is not None and levels is not None and storage_for_update is not None
    init_half = "ltp-storageinit-half-trigger" in changed_ids
    init_from_snap = not init_half and "ltp-storageinit-snap-trigger" in changed_ids
    best_match = start_time
    if not init_half and not init_from_snap and not user_material_update:
        if "ltp-start-time" in changed_ids:
            # check first if a suitable snapshot is available
            sp = state.get_snapshot_provider()
            last_snap = sp.previous(time=start_time)
            next_snap = sp.next(time=start_time)
            best_match = last_snap if next_snap is None else next_snap if last_snap is None else \
                last_snap if abs((start_time-last_snap).total_seconds()) <= abs((next_snap-start_time).total_seconds()) else next_snap
            if best_match is not None and abs(best_match - start_time).total_seconds() <= timedelta(hours=24).total_seconds():
                init_from_snap = True
        if not init_from_snap:
            init_half = True
    if init_from_snap:
        snap = state.get_snapshot(time=best_match)
        if snap is None and levels is None:
            init_half = True
        elif snap is not None:
            storages = ModelUtils.storage_content_from_snapshot(snap, state.get_site())
    if init_half:
        for storage in site.storages:
            material_levels = {cl.id: 0.5 * (cl.default_share if cl.default_share is not None else 1 if cl.is_default else 0)  \
                                                                    for cat in site.material_categories for cl in cat.classes}
            if storage.material_constraints is not None:
                exclusions = storage.material_constraints.excluded
                for cl in exclusions:
                    material_levels.pop(cl)
                affected_categories = [cat for cat in site.material_categories if any(cl.id in exclusions for cl in cat.classes)]
                for cat in affected_categories:
                    remaining_classes = [cl for cl in cat.classes if cl.id not in exclusions]
                    total_share = sum(cl.default_share if cl.default_share is not None else 1 if cl.is_default else 0 for cl in remaining_classes)
                    if 0 < total_share < 1:
                        for cl in remaining_classes:
                            material_levels[cl.id] = min(1., material_levels[cl.id] / total_share)
            level = StorageLevel(storage=storage.name_short, filling_level=0.5, timestamp=start_time, material_levels=material_levels)
            storages[storage.name_short] = level
    if not init_half and not init_from_snap and levels is not None:
        storages = TypeAdapter(dict[str, StorageLevel]).validate_json(levels)
        for level in storages.values():
            level.timestamp = start_time
        if user_material_update and storage_for_update in storages:
            stg_obj = site.get_storage(storage_for_update, do_raise=True)
            capacity = stg_obj.capacity_weight
            storages[storage_for_update].material_levels = {mat: value/capacity for mat, value in storage_update.items()}
    if len(storages) == 0:
        return dash.no_update
    return TypeAdapter(dict[str, StorageLevel]).dump_json(storages).decode("utf-8")


@callback(Output("ltp-init-availabilities-result", "children"),
            Output("ltp-init-process-capacities", "children"),
            Output("ltp-process-min-capacity", "children"),
            Output("ltp-min-capacity", "data"),
            Input("ltp-plants-graph", "stylesheet"),  # this is triggered by a change in ltp-availability-buffer.data
            Input("ltp-plant-availability", "data"),  # triggered by calendar-clear => update upon clearing the calendar
            Input("ltp-start-end", "data")
            # TODO add information about exact start time in case of snapshot usage
)
# TODO currently returns a flat structure, i.e. one div per plant. Better: make it a grid, with 2 divs per plant, also divide between 3 or so columns
def set_initial_availabilities(_: Any, __: Any, start_end: tuple[str|None, str|None]|None):
    persistence = state.get_availability_persistence()
    if start_end is None or any(e is None for e in start_end):
        return "Not available", [], [], 100_000
    start, end = [DatetimeUtils.parse_date(e).date() for e in start_end]
    plants: dict[int, Equipment] = {p.id: p for p in state.get_site().equipment}
    plant_data: dict[int, list[EquipmentAvailability]] = {eq: results for eq, results in persistence.load_all(start, end).items() if eq in plants}
    start_dt, end_dt = _date_range_to_datetime(start, end)
    shifts = state.get_shifts_provider().load_all(start_dt, end_dt)
    hours_per_plant: dict[int, timedelta] = {pid: sum((s.worktime for s in shifts.get(pid)), start=timedelta()) if pid in shifts else timedelta() for pid in plants.keys() if pid not in plant_data}
    for eq, delta in dict(hours_per_plant).items():  # correction for shifts that only partially belong to the month (night shifts)
        if eq not in shifts or len(shifts[eq]) == 0:
            continue
        eq_shifts = shifts[eq]
        first = eq_shifts[0]
        last = eq_shifts[-1]
        surplus = timedelta()
        if first.period[0] < start_dt:
            share_in_month = (first.period[1] - start_dt).total_seconds()/(first.period[1] - first.period[0]).total_seconds()
            if 0 < share_in_month < 1:
                surplus += (1-share_in_month) * first.worktime
        if last.period[1] > end_dt:
            share_in_month = (end_dt - last.period[0])/(last.period[1] - last.period[0])
            if 0 < share_in_month < 1:
                surplus += (1-share_in_month) * last.worktime
        hours_per_plant[eq] = hours_per_plant[eq] - surplus
    hours_per_plant.update({pid: ModelUtils.aggregate_availabilities(avail, start, end) for pid, avail in plant_data.items()})
    # sort according to plants array
    hours_per_plant = dict(sorted(hours_per_plant.items(), key=lambda key_val: next(idx for idx, pid in enumerate(plants.keys()) if pid == key_val[0])))
    processes = state.get_site().processes
    capacity_by_process = {proc.name_short: 0. for proc in processes}  # in t
    for p, hours in hours_per_plant.items():
        if p not in plants:
            continue
        plant_obj = plants[p]
        if plant_obj.throughput_capacity is None:   # maybe we should rather hide the element then?
            continue
        capacity_by_process[plant_obj.process] += plant_obj.throughput_capacity * hours.total_seconds() / 3600
    min_cap_by_proc = capacity_by_process
    ltp_settings = state.get_site().long_term_planning
    if ltp_settings is not None:
        procs_to_ignore = [p for p, settings in ltp_settings.processes.items() if settings.ignore_capacity]
        if len(procs_to_ignore) > 0:
            min_cap_by_proc = {p: c for p,c in min_cap_by_proc.items() if p not in procs_to_ignore}
    min_capacity_proc = min(min_cap_by_proc, key=min_cap_by_proc.get)
    min_capacity = capacity_by_process.get(min_capacity_proc)
    min_capacity_in_unit = min_capacity
    average_capacity = np.mean(list(capacity_by_process.values()))
    capacity_unit = "t"
    decimals = 0
    if average_capacity > 1_000_000:
        capacity_unit = "Mt"
        capacity_by_process = {p: c/1e6 for p,c in capacity_by_process.items()}
        decimals = 0 if average_capacity >= 100_000_000 else 1 if average_capacity >= 10_000_000 else 2
        min_capacity_in_unit = min_capacity_in_unit / 1e6
    if average_capacity > 1_000:
        capacity_unit = "kt"
        capacity_by_process = {p: c / 1e3 for p, c in capacity_by_process.items()}
        decimals = 0 if average_capacity >= 100_000 else 1 if average_capacity >= 10_000 else 2
        min_capacity_in_unit = min_capacity_in_unit / 1e3
    min_cap_string = f"{min_capacity_in_unit:.{decimals}f} {capacity_unit} ({min_capacity_proc})"
    return [div for divs in ((html.Div(f"{plants[pid].name_short}:"), html.Div(f"{round(period.total_seconds()/3_600)}h", className="ltp-processes-cap"), html.Div()) for pid, period in hours_per_plant.items()) for div in divs], \
        [div for divs in ((html.Div(f"{proc}:"), html.Div(f"{capacity:.{decimals}f} {capacity_unit}", className="ltp-processes-cap"), html.Div()) for proc, capacity in capacity_by_process.items()) for div in divs], \
        min_cap_string, min_capacity


@callback(
            Output("ltp-init-structure-total", "children"),
            Output("ltp-init-structure-total", "title"),
            Output("ltp-init-structure-result", "style"),
            Output("ltp-init-structure-result", "children"),
            Input("ltp-material-setpoints", "data")
)
# TODO currently returns a flat structure, i.e. one div per plant. Better: make it a grid, with 2 divs per plant, also divide between 3 or so columns
def set_structure_targets_overview(structure: dict[str, float]|None):
    title = "Click the \"Structure Portfolie\" button above to define the target structure"
    if not structure or not dash_authenticated(config):
        return "To be defined", title, None, None
    categories = state.get_site().material_categories
    structure_by_category: dict[str, dict[str, float]] =  {c.id: {cl.id: structure[cl.id] for cl in c.classes if cl.id in structure} for c in categories}
    total_value_by_cat: dict[str, float] = {cat: sum(dct.values()) for cat, dct in structure_by_category.items()}
    epsilon = 1e-5
    total_value_by_cat = {cat: val for cat, val in total_value_by_cat.items() if val > epsilon}
    if len(total_value_by_cat) == 0:
        return "To be defined", title, None, None
    first_total = next(v for v in total_value_by_cat.values())
    if any(abs(v - first_total) / abs(v + first_total) > epsilon for v in total_value_by_cat.values()):
        return "Inconsistent state", title, None, None,
    #structure_by_category = {cat: strct for cat, strct in structure_by_category.items() if cat in total_value_by_cat}
    applicable_cats = [cat for cat in categories if cat.id in total_value_by_cat]
    divs = [html.Div(cat.name or cat.id, style={"grid-column-start": str(idx+1), "grid-row-start": "1"}, className="ltp-overview-grid-header") for idx, cat in enumerate(applicable_cats)]
    for col_idx, cat in enumerate(applicable_cats):
        divs = divs + [html.Div(f"{cl.name or cl.id}: {round(structure.get(cl.id, 0)/1000)}",
                                style={"grid-column-start": str(col_idx+1), "grid-row-start": str(2 + row_idx)}) for row_idx, cl in enumerate(cat.classes)]
    grid_style = {"display": "grid", "grid-template-columns": f"repeat({len(applicable_cats)}, auto)", "column-gap": "1em", "row-gap": "0.3em" }
    return "Total production target: " + str(round(first_total/1000)) + "kt", None, grid_style, divs


@callback(
        Output("ltp-init-storages-total", "children"),
        Output("ltp-init-storages-total", "title"),
        #Output("ltp-init-storages-result", "style"),
        Output("ltp-init-storages-result", "children"),
        Input("ltp-storage-levels", "data")
)
def set_storage_targets_overview(levels: str|None):  # {storage id: StorageLevel}
    title="Click the \"Storage initialization\" button above to define the initial storage content"
    if not levels or not dash_authenticated(config):
        return "To be defined", title, None
    storage_levels = TypeAdapter(dict[str, StorageLevel]).validate_json(levels)
    storages = [s for s in state.get_site().storages if s.name_short in storage_levels]
    divs = [html.Div("Storage id", className="ltp-overview-grid-header"), html.Div("Content", className="ltp-overview-grid-header"),
            html.Div("Filling level", className="ltp-overview-grid-header"), html.Div("Material structure", className="ltp-overview-grid-header")]
    for storage in storages:
        lv: StorageLevel|None = storage_levels.get(storage.name_short)
        level: float = lv.filling_level if lv is not None else 0
        capacity = storage.capacity_weight or 0
        title = f"Capacity: {capacity/1000:.3}kt"
        name = html.Div(storage.name_short, title=title)
        #value_abs = html.Div(f"{(level * capacity)/1000} kt")
        #value_rel = html.Div(f"{round(level * 100)}%")
        value_abs = html.Div([
            dcc.Input(value=f"{level * capacity / 1000:.3}", min=0, max=capacity/1000, type="number", className="ltp-stg-level-abs"),
            html.Span("kt")
        ], title=title, **{"data-capacity": str(capacity)})
        value_rel = html.Div([
            dcc.Input(value=round(level * 100), min=0, max=100, type="number", className="ltp-stg-level-abs"),
            html.Span("%")
        ], **{"data-storage": storage.name_short})
        # XXX here we assume mat does not contain "-", since this is converted to camelCase in dataset!
        mat_dict: dict[str, float|str] = ({f"data-mat_{mat}": level for mat, level in lv.material_levels.items()} if lv is not None and lv.material_levels is not None else None) or {}
        mat_dict["data-storage"] = storage.name_short
        if storage.material_constraints is not None and len(storage.material_constraints.excluded) > 0:
            mat_dict["data-excluded"] = ",".join(storage.material_constraints.excluded)
        structure = html.Div([
            html.Button("Edit structure", id={"role": "ltp-stg-structure-btn", "id": storage.name_short}, className="dynreact-button-small", **mat_dict)
        ])
        divs.extend((name, value_abs, value_rel, structure))
    return None, None, divs


"""
@callback(
        Output("ltp-stg-structure-dialog", "title"),
        Input({"role": "ltp-stg-structure-btn", "id": ALL}, "n_clicks"),
)
def test_l_(clicks):
    return f"--{clicks}--"
"""

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="showModal"
    ),
    Output("ltp-stg-structure-dialog", "title"),
    Input({"role": "ltp-stg-structure-btn", "id": ALL}, "n_clicks"),
    State("ltp-stg-structure-dialog", "id"),
)


clientside_callback(
    ClientsideFunction(
        namespace="ltp",
        function_name="setStorageListeners"
    ),
    Output("ltp-init-storages-result", "title"),
    Input("ltp-init-storages-total", "title"),
    State("ltp-init-storages-result", "id"),
)


@callback(
          Output("ltp-frozen-lot-total", "children"),
          Output("ltp-frozen-lot-structure", "data"),
          #Input("ltp-start-time-selection", "value"),
          Input("selected-snapshot", "data"),
          Input("ltp-start-time-selection", "value"),
          Input("ltp-start-end", "data"))  # State or Input?
def frozen_lot_structure(snapshot: str|None, start_time_type: Literal["now", "nextmonth", "other"]|None, start_end: tuple[str|None, str|None]|None):
    if not dash_authenticated(config) or start_time_type != "now" or not start_end:
        return None, None
    start = state.as_timezone(DatetimeUtils.parse_date(start_end[0]))
    end = state.as_timezone(DatetimeUtils.parse_date(start_end[1]))
    snapshot = DatetimeUtils.parse_date(snapshot)
    snap_obj = state.get_snapshot(time=snapshot)
    if snap_obj is None:
        return None, None
    snap_provider = state.get_snapshot_provider()
    # TODO missing lots from earlier process stages with shortcuts
    frozen_lots = {eq: [lot for lot in lots if snap_provider.is_lot_complete(lot) and
                        lot.start_time is not None and lot.end_time is not None and lot.start_time < end and lot.end_time > start] for eq, lots in snap_obj.lots.items()}
    final_processes = [proc for proc in state.get_site().processes if proc.next_steps is None or len(proc.next_steps) == 0]
    final_process_ids = [p.name_short for p in final_processes]
    equipments = [eq.id for eq in state.get_site().equipment if eq.process in final_process_ids]
    final_lots: list[Lot] = [lot for eq, lots in frozen_lots.items() if eq in equipments for lot in lots]
    total_weight = sum(lot.weight or 0. for lot in final_lots)
    material_weights = {}
    for lot in (lt for lt in final_lots if lt.material_weights is not None):
        share = 1 if lot.end_time <= end and lot.start_time >= start else 0 if lot.end_time <= lot.start_time else (min(lot.end_time, end) - max(lot.start_time, start))/(lot.end_time - lot.start_time)
        for mat, weight in lot.material_weights.items():
            material_weights[mat] = material_weights.get(mat, 0.) + weight*share
    final_mat_structure = {}
    for cat in state.get_site().material_categories:
        classes = {cl.id: {"name": cl.name or cl.id, "weight": material_weights.get(cl.id, 0)} for cl in cat.classes}
        final_mat_structure[cat.id] = {"name": cat.name or cat.id, "classes": classes}
    return f"{total_weight:.2f}", final_mat_structure

clientside_callback(
    ClientsideFunction(
        namespace="lots2",
        function_name="setBacklogStructureOverview"
    ),
    Output("ltp-frozen-lots-structure-widget", "title"),
    Input("ltp-frozen-lot-structure", "data"),   # dict[str, dict[str, float]]
    Input("ltp-dummy-undefined", "data"),
    State("ltp-frozen-lots-structure-widget", "id"),
)


@callback(Output("ltp-start", "disabled"),
          Output("ltp-start", "title"),
          Output("ltp-stop", "disabled"),
          Output("ltp-stop", "title"),
          #Output("ltp-amount-selected", "children"),
          Output("ltp-interval", "interval"),
          Output("ltp-running-indicator", "hidden"),
          #Output("ltp-result-container", "hidden"),
          #Output("ltp-result-id", "children"),
          Output("ltp-result-message", "data"),
          Input("ltp-start", "n_clicks"),
          Input("ltp-stop", "n_clicks"),
          Input("ltp-interval", "n_intervals"),
          Input("ltp-material-setpoints", "data"),  # keys: material class id, values: production / t
          Input("ltp-storage-levels", "data"),
          State("ltp-init-storages-result", "children"),
          State("ltp-start-end", "data"),
          # TODO pass information about exact start time in case of snapshot init
          State("ltp-shift-hours", "value"),
          State("ltp-production-total", "value"),
          State("ltp-results-store", "value"),
          State("ltp-start-time-selection", "value"),
          State("selected-snapshot", "data"),
          State("ltp-frozen-lots", "value"),
          config_prevent_initial_callbacks=True)
def check_start_stop(_, __, ___, setpoints: dict[str, float], storage_levels: str|None, storage_children, start_end: tuple[str|None, str|None]|None, shift_duration_hours: str|int,
                     total_production: float|str|None, do_store0: Sequence[Literal[""]], start_time_type: Literal["now", "nextmonth", "other"]|None, snapshot: str|None, frozen_lots0: Sequence[Literal[""]]):
    if not dash_authenticated(config):
        return None, None, None, None, None, None, None, None
    do_store: bool = do_store0 is not None and len(do_store0) > 0
    is_running, new_solution_id, new_sol_start_date, new_error = check_running_optimization()
    total_amount = _get_total_selected_amount(setpoints)
    changed_ids = GuiUtils.changed_ids()
    new_sol_start = DatetimeUtils.format(new_sol_start_date) if new_sol_start_date is not None else None
    message = dash.no_update if new_solution_id is None or isinstance(new_error, InterruptedException) \
        else {"msg": f"An error occurred: {new_error}", "type": "error"} if new_error is not None \
        else {"msg": f"New solution: {new_solution_id}", "type": "success",
              "options": {"href": f"/dash/ltp/planned?start={new_sol_start}&solution={new_solution_id}", "title": "Open solutions page in new tab"}}
    starting = not is_running and "ltp-start" in changed_ids
    if starting:
        try:
            if start_end is None or any(e is None for e in start_end):
                raise Exception(f"Invalid start/end time: {start_end}")
            start, end = [DatetimeUtils.parse_date(e).date() for e in start_end]
            start_dt, end_dt = _date_range_to_datetime(start, end)
            shift_duration_hours = allowed_shift_durations[int(shift_duration_hours)]
            if total_production is None:
                raise Exception("Total production not set")
            else:
                total_production = float(total_production)
            if total_production <= 0:
                raise ValueError("Total production must be positive, got " + str(total_production))
            adapted_storage_levels: dict[str, StorageLevel] = _get_storage_levels(storage_children, start_dt)
            if adapted_storage_levels is None:
                raise Exception("Storage levels not defined yet")
        except Exception as e:
            return (False,  # start disabled
                    dash.no_update,
                    True,  # end disabled
                    "Not running.",  # end title
                    dash.no_update,
                    True,   # running indicator hidden
                    {"msg": f"An error occurred: {e}", "type": "error"}
                    )
        if ltp_thread is None and total_amount is not None:
            # FIXME these may have changed due to user interaction
            #levels = TypeAdapter(dict[str, StorageLevel]).validate_json(storage_levels)
            try:
                availabilities: dict[int, list[EquipmentAvailability]] = state.get_availability_persistence().load_all(start, end)
                shifts: dict[int, Sequence[PlannedWorkingShift]] = state.get_shifts_provider().load_all(start_dt, end_dt)
                for eq, eq_shifts in dict(shifts).items():  # correction for shifts that only partially belong to the month (night shifts)
                    if len(shifts[eq]) == 0:
                        continue
                    first = eq_shifts[0]
                    last = eq_shifts[-1]
                    start_correction = first.period[0] < start_dt < first.period[1]
                    end_correction = last.period[0] < end_dt < last.period[1]
                    if start_correction or end_correction:
                        new_first = PlannedWorkingShift(equipment=eq, period=(start_dt, first.period[1]), worktime=((first.period[1]-start_dt).total_seconds()/(first.period[1]-first.period[0]).total_seconds())*first.worktime) \
                                if start_correction else first
                        new_last = PlannedWorkingShift(equipment=eq, period=(last.period[0], end_dt), worktime=((end_dt - last.period[0]).total_seconds()/(last.period[1]-last.period[0]).total_seconds())*last.worktime) \
                            if end_correction else last
                        new_shifts = [new_first] + list(eq_shifts)[1:-1] + [new_last]
                        shifts[eq] = new_shifts
                availabilities_aggregated = PlantAvailabilityPersistence.aggregate([p.id for p in state.get_site().equipment], start, end, availabilities, shifts=shifts)
                frozen_lots = None
                if start_time_type == "now" and snapshot is not None and len(frozen_lots0) > 0:
                    snapshot_dt = DatetimeUtils.parse_date(snapshot)
                    snap_obj = state.get_snapshot(time=snapshot_dt)
                    snap_provider = state.get_snapshot_provider()
                    frozen_lots = {eq: sorted([lot for lot in lots if snap_provider.is_lot_complete(lot) and lot.start_time is not None and lot.end_time is not None],
                                              key=lambda l: l.end_time) for eq, lots in snap_obj.lots.items()}
                    frozen_lots = {eq: lots for eq, lots in frozen_lots.items() if len(lots) > 0}
                run(start_dt, end_dt, shift_duration_hours, setpoints, total_production, adapted_storage_levels, availabilities_aggregated, frozen_lots, do_store)
                message = {"msg": "Long term planning started", "type": "info", "options": {"timeout": 4_000}}
            except Exception as e:
                traceback.print_exc()
                return (False,  # start disabled
                    dash.no_update,
                    True,  # end disabled
                    "Not running.",  # end title
                    dash.no_update,
                    True,   # running indicator hidden
                    {"msg": f"An error occurred: {e}", "type": "error"}
                    )
    if "ltp-stop" in changed_ids and ltp_thread is not None:
        stop()
        message = {"msg": "Long term planning stopped", "type": "info", "options": {"timeout": 4_000}}
    is_running = ltp_thread is not None
    itv = 3_000 if is_running else 3_600_000
    if not is_running:
        if total_amount is None or storage_levels is None:
            return (True,  # start disabled
                    "Material structure or storage levels not defined, yet. Please open the structure portfolio menu and select the material to produce.", # start title
                    True,  # end disabled
                    "Not running.",  # end title
                    itv,  # polling interval,
                    True,   # running indicator hidden
                    message
                    )
        return (False,  # start disabled
                "Run long-term planning.", # start title
                True,  # end disabled
                "Not running.",  # end title
                itv,  # polling interval
                True,  # running indicator hidden
                message
                )
    return (True,  # start disabled
            "Already running.", # start title
            False,  # end disabled
            "Stop optimization.",  # end title
            itv,  # polling interval
            False,  # running indicator hidden
            message
            )


def check_running_optimization() -> tuple[bool, str|None, date|None, Exception|None]:
    global ltp_thread
    solution_id = None
    error = None
    start_date = None
    if ltp_thread is not None:
        if not ltp_thread.is_alive():
            solution_id = ltp_thread.id()
            start_date = ltp_thread.start_date()
            error = ltp_thread.error()
            ltp_thread = None
    return ltp_thread is not None, solution_id, start_date, error

def _get_storage_levels(children: list[Component]|None, start_date: datetime) -> dict[str, StorageLevel]|None:
    if not children:
        return None
    site = state.get_site()
    storages = {stg.name_short: stg for stg in site.storages}
    levels = {}
    for child in children:
        stg = child.get("props").get("data-storage")
        if not stg:
            continue
        level = next(c for c in child.get("props").get("children") if c.get("type") == "Input").get("props").get("value")/100

        material_levels = {cl.id: level * (cl.default_share if cl.default_share is not None else 1 if cl.is_default else 0) \
                                for cat in site.material_categories for cl in cat.classes}
        storage = storages[stg]
        if storage.material_constraints is not None:
            exclusions = storage.material_constraints.excluded
            for cl in exclusions:
                material_levels.pop(cl)
            affected_categories = [cat for cat in site.material_categories if any(cl.id in exclusions for cl in cat.classes)]
            for cat in affected_categories:
                remaining_classes = [cl for cl in cat.classes if cl.id not in exclusions]
                total_share = sum(
                    cl.default_share if cl.default_share is not None else 1 if cl.is_default else 0 for cl in
                    remaining_classes)
                if 0 < total_share < 1:
                    for cl in remaining_classes:
                        material_levels[cl.id] = min(1., material_levels[cl.id] / total_share)
        levels[stg] = StorageLevel(storage=stg, filling_level=level, timestamp=start_date, material_levels=material_levels)
    return levels


def run(start_time: datetime, end_time: datetime, shift_duration_hours: int, setpoints: dict[str, float],
          total_production: float, storage_levels: dict[str, StorageLevel], availabilities: dict[int, EquipmentAvailability],
          frozen_lots: dict[int, Sequence[Lot]]|None, do_store: bool):
    global ltp_thread
    shift_duration = timedelta(hours=shift_duration_hours)
    shifts: list[tuple[datetime, datetime]] = []
    start_shift = start_time
    end_shift = start_shift + shift_duration
    end_boundary = end_time if start_time.tzinfo == end_time.tzinfo else end_time.replace(tzinfo=start_time.tzinfo)
    while end_shift <= end_boundary:
        shifts.append((start_shift, end_shift))
        start_shift = end_shift
        end_shift = end_shift + shift_duration
    ltp_targets: LongTermTargets = LongTermTargets(
        source="user_selected",
        comment="TODO",
        period=[start_time, end_time],
        total_production=total_production,
        production_targets=setpoints
    )
    ltp: LongTermPlanning = state.get_long_term_planning()
    persistence = state.get_results_persistence() if do_store else state.get_results_persistence_memory()
    prefix = "ltp_" if do_store else "ltp_memory_"
    new_id = prefix + DatetimeUtils.format(DatetimeUtils.now().astimezone(), use_zone=False).replace("-", "_").replace(":", "_")
    actual_id = new_id
    cnt: int = 0
    while persistence.has_solution_ltp(start_time, actual_id):
        cnt += 1
        actual_id = new_id + "_" + str(cnt)
    ltp_thread = LTPKillableOptimizationThread(actual_id, ltp, ltp_targets, availabilities, storage_levels, shifts, persistence=persistence)
    ltp_thread.start()


def stop() -> bool:
    global ltp_thread
    if ltp_thread is not None:
        ltp_thread.kill()
        ltp_thread = None
    return ltp_thread is None

# clientside arguments: msg, type, siblingId, dummyReturnValue
clientside_callback(
    ClientsideFunction(
        namespace="alert",
        function_name="showAlertObj"
    ),
    Output("ltp-result-alert", "title"),
    Input("ltp-result-message", "data"),
    State("ltp-result-alert", "id"),
)




class LTPKillableOptimizationThread(threading.Thread):

    def __init__(self,
                 id: str,
                 optimization: LongTermPlanning,
                 structure: LongTermTargets,
                 availabilities: dict[int, EquipmentAvailability],
                 initial_storage_levels: dict[str, StorageLevel],
                 shifts: list[tuple[datetime, datetime]],
                 frozen_lots: dict[int, Sequence[Lot]]|None=None,
                 persistence: ResultsPersistence|None = None,
                 ):
        super().__init__(name=ltp_thread_name)
        self._id = id
        self._kill = threading.Event()
        self.daemon = True  # Allow main to exit even if still running.
        self._optimization = optimization
        self._availabilities = availabilities
        self._structure = structure
        self._initial_storage_levels = initial_storage_levels
        self._shifts = shifts
        self._persistence = persistence
        self._start_date: date|None = None
        self._frozen_lots = frozen_lots
        self._error = None

    def id(self):
        return self._id

    def kill(self):
        self._kill.set()
        self._optimization.interrupt(self._id)

    def error(self):
        return self._error

    def start_date(self) -> date|None:
        return self._start_date

    def run(self):
        solution_id = self._id
        try:
            results, storage_levels = self._optimization.run(solution_id, self._structure, initial_storage_levels=self._initial_storage_levels,
                                          shifts=self._shifts, plant_availabilities=self._availabilities, frozen_lots=self._frozen_lots)
            if self._kill.is_set():
                raise InterruptedException()
            self._start_date = results.period[0].date()
            if self._persistence:
                self._persistence.store_ltp(solution_id, results, storage_levels=storage_levels)
            return results
        except Exception as e:
            self._error = e
            raise

