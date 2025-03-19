import threading
import traceback
from calendar import monthrange  # , Day  # Python 3.12
from datetime import datetime, timedelta, date
from typing import Any

import dash
from dash import html, dcc, callback, Output, Input, clientside_callback, ClientsideFunction, State

from dynreact.auth.authentication import dash_authenticated
from dynreact.base.LongTermPlanning import LongTermPlanning
from dynreact.base.PlantAvailabilityPersistence import PlantAvailabilityPersistence
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.ModelUtils import ModelUtils
from dynreact.base.model import LongTermTargets, EquipmentAvailability, StorageLevel, Storage, Equipment
from pydantic import TypeAdapter

from dynreact.app import state, config
from dynreact.gui.gui_utils import GuiUtils
from dynreact.gui.pages.plants_graph import plants_graph, default_stylesheet
from dynreact.gui.pages.session_state import selected_snapshot, get_date_range

dash.register_page(__name__, path="/ltp")
translations_key = "ltp"


ltp_thread_name = "long-term-planning"
ltp_thread: threading.Thread|None = None

allowed_shift_durations: list[int] = [1, 2, 4, 8, 12, 24, 48, 72, 168]


# TODO visualize structure and storage initialization state together
# TODO storage initialization from snapshot
# TODO pass plant availabilities to LTP
def layout(*args, **kwargs):
    horizon_weeks: int = int(kwargs.get("weeks", 4))    # planning horizon in weeks
    total_production: float = kwargs.get("total", 100_000)
    start_date0: datetime = DatetimeUtils.parse_date(kwargs.get("starttime"))
    if start_date0 is None:
        start_date0 = datetime.now()  # beginning of next month
        start_date0 = (start_date0.replace(day=1, minute=0, second=0, microsecond=0) + timedelta(days=32)).replace(day=1)
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
                    dcc.Input(type="date", id="ltp-start-time", value=start_date)
                    #dcc.DatePickerSingle(id="ltp-start-time", date=start_date)
                ], className="ltp-starttime-block"),
                # Horizon (weeks) block
                html.Div([
                    html.Div("Time horizon (weeks)", title="Specify the planning horizon in weeks"),
                    html.Div([
                        dcc.Input(type="range", id="ltp-horizon-weeks", min=1, max=4, step=1, value=horizon_weeks),
                        html.Div(horizon_weeks, id="ltp-horizon-weeks-value")
                    ], className="ltp-horizon-widget", title="Specify the planning horizon in weeks")
                ], className="control-panel-entry"),
                html.Div([
                    html.Div("Shift duration (hours)", title="Specify the duration of a single shift. The planning algorithm will assign target production values per shift."),
                    html.Div([
                        dcc.Input(type="range", id="ltp-shift-hours", min=0, max=len(allowed_shift_durations)-1, step=1, value=3),
                        html.Div(horizon_weeks, id="ltp-shift-hours-value")
                    ], className="ltp-horizon-widget", title="Specify the planning horizon in weeks")
                ], className="control-panel-entry"),
                html.Div(html.Button("Structure Portfolio", className="dynreact-button", id="ltp-structure-btn")),
                html.Div(id="ltp-amount-selected"),
                html.Div(html.Button("Storages initialization", className="dynreact-button", id="ltp-storages-btn")),
                html.Div([
                    html.Button("Start", className="dynreact-button", id="ltp-start", disabled=True),
                    html.Button("Stop", className="dynreact-button", id="ltp-stop", disabled=True)
                ], className="flex"),
                html.Div([
                    html.Progress(),
                    html.Div("Optimization running")
                ], id="ltp-running-indicator", hidden=True),
                html.Div([
                    html.Div("New result"),
                    html.Div(id="ltp-result-id"),
                ], id="ltp-result-container", className="ltp-result-container", hidden=True),
            ])
        ], className="control-panel"),
        # ======== Initial values panel ============
        html.Div([
            html.Div("Initialization"),
            html.Div([
                html.Div([
                    html.H3("Equipment availabilities"),
                    html.Div("To be defined", id="ltp-init-availabilities-result",
                            title="Click equipment icons below to adapt the availabilities.")  # TODO content
                ], id="ltp-init-availabilities"),
                html.Div([
                    html.H3("Material structure"),
                    html.Div("To be defined", id="ltp-init-structure-result",
                            title="Click the \"Structure Portfolie\" button above to define the target structure")  # TODO content
                ], id="ltp-init-structure"),
                html.Div([
                    html.H3("Initial storage content"),
                    html.Div("To be defined", id="ltp-init-storages-result",
                             title="Click the \"Storage initialization\" button above to define the initial storage content")  # TODO content
                ], id="ltp-init-storages")
            ], className="ltp-init-panel")
        ], className="control-panel", id="ltp-initialization"),
        # ======== Process panel ============
        html.Div([
            html.Div("Process Panel"),
            html.Div([
                plants_graph("ltp-plants-graph", style={"width": str(num_processes * 10) + "em", "height": "500px"},
                             stylesheet=graph_stylesheets(start_date0.date(), (start_date0 + timedelta(weeks=horizon_weeks)).date()), *args, **kwargs)
            ], style={"display": "flex", "justify-content": "flex-start"})
        ], className="control-panel", id="ltp-process-panel"),
        # ======== Popups and hidden elements =========
        structure_portfolio_popup(total_production),
        plant_calendar_popup(),
        storage_init_popup(),
        # stores information about the last start time and horizon for which material properties have been set,
        # in the format {"startTime": startTime, "horizon": horizon}
        dcc.Store(id="ltp-material-settings"),
        dcc.Store(id="ltp-material-setpoints"),
        # Set when the user clicks on a plant node in the graph
        dcc.Store(id="ltp-selected_plant", storage_type="memory"),
        # contains a list of json serialized PlantAvailability objects for the currently selected plant, or None,
        # as input for the calendar popup
        dcc.Store(id="ltp-plant-availability", storage_type="memory"),
        # contains a json serialized PlantAvailability object for the currently selected plant, or None,
        # as output from the calendar popup
        dcc.Store(id="ltp-availability-buffer", storage_type="memory"),
        dcc.Store(id="ltp-storage-levels"),  # None or {storage id: StorageLevel}
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


def storage_init_popup():
    start_date, end_date, snap_options, selected_snap = get_date_range(selected_snapshot.data)  # : tuple[date, date, list[datetime], str]
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
          State("ltp-material-setpoints", "data"),
          config_prevent_initial_callbacks=True)
def material_menu_canceled(_, setpoints: dict[str, float]) -> float:
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


@callback(Output("ltp-material-settings", "data"),
          Input("ltp-materials-accept", "n_clicks"),
          State("ltp-start-time", "value"),
          State("ltp-horizon-weeks", "value"),
          config_prevent_initial_callbacks=True)
def material_settings_accepted(_, start_time: str, horizon: str) -> str:
    if start_time is None or horizon is None or start_time == "" or horizon == "":
        return
    try:
        horizon = int(horizon)
        if DatetimeUtils.parse_date(start_time) is None:
            raise ValueError("Invalid start time", start_time)
        return {"start_time": start_time, "horizon": horizon}
    except:
        traceback.print_exc()

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

clientside_callback(
    ClientsideFunction(
        namespace="ltp",
        function_name="getMaterialSetpoints"
    ),
    Output("ltp-material-setpoints", "data"),
    Input("ltp-materials-accept", "n_clicks"),
    State("ltp-materials-grid", "id"),
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
    Output("ltp-materials-accept", "title"),
    Input("ltp-materials-accept", "n_clicks"),
    State("ltp-structure-dialog", "id"),
    State("ltp-materials-accept", "title"),
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


def _get_start_end_time(start_time: datetime|str, horizon: str|int) -> tuple[date|None, date|None]:
    start_time = DatetimeUtils.parse_date(start_time)
    horizon = int(horizon)
    if start_time is None or horizon <= 0:
        return None, None
    start: date = start_time.date()
    month_info: tuple[int, int] = monthrange(start.year, start.month)  # tuple[calendar.Day, int] from Python 3.12
    end_time = start_time + (timedelta(days=month_info[1]) if horizon == 4 else timedelta(weeks=horizon))
    return start, end_time.date()


@callback(Output("ltp-plant-availability", "data"),
        Input("ltp-selected_plant", "data"),           # user clicked on a plant node in the graph
        Input("ltp-calendar-clear", "n_clicks"),
        State("ltp-start-time", "value"),
        State("ltp-horizon-weeks", "value"),
        config_prevent_initial_callbacks=True)
def init_calendar(selected_plant: int|None, _, start_time: datetime|str, horizon: str|int):
    if selected_plant is None or start_time is None or horizon is None or not dash_authenticated(config):
        return None
    selected_plant = int(selected_plant)
    start, end = _get_start_end_time(start_time, horizon)
    if start is None or end is None:
        return None
    availabilities: PlantAvailabilityPersistence = state.get_availability_persistence()
    changed = GuiUtils.changed_ids()
    if "ltp-calendar-clear" in changed:
        availabilities.delete(selected_plant, start, end)
        return None
    av: list[EquipmentAvailability] = availabilities.load(selected_plant, start, end)
    av_json = TypeAdapter(list[EquipmentAvailability]).dump_json(av).decode("utf-8")
    return av_json


clientside_callback(
    ClientsideFunction(
        namespace="ltp",
        function_name="initCalendar"
    ),
    Output("ltp-start-time", "title"),   # dummy
    Input("ltp-plant-availability", "data"),
    State("ltp-selected_plant", "data"),
    State("ltp-start-time", "value"),
    State("ltp-horizon-weeks", "value"),
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


@callback(Output("ltp-storage-levels", "data"),
          Input("ltp-storageinit-snap-trigger", "n_clicks"),
          Input("ltp-storageinit-half-trigger", "n_clicks"),
          Input("ltp-storageinit-clear", "n_clicks"),
          Input("ltp-start-time", "value"),
          State("ltp-storage-levels", "data"),
          config_prevent_initial_callbacks=True)
def set_storage_levels(_, __, ___, start_time: datetime|str, levels: str|None):
    if not dash_authenticated(config):
        return None
    start_time = DatetimeUtils.parse_date(start_time)
    if start_time is None:
        return dash.no_update
    changed_ids: list[str] = GuiUtils.changed_ids(excluded_ids=[""])
    if "ltp-storageinit-clear-trigger" in changed_ids:
        return None
    site = state.get_site()
    storages: dict[str, StorageLevel] = {}
    if "ltp-storageinit-half-trigger" in changed_ids:
        for storage in site.storages:
            material_levels = {cl.id: 0.5 * (cl.default_share if cl.default_share is not None else 1 if cl.is_default else 0) \
                                                                    for cat in site.material_categories for cl in cat.classes}
            level = StorageLevel(storage=storage.name_short, filling_level=0.5, timestamp=start_time, material_levels=material_levels)
            storages[storage.name_short] = level
    if "ltp-storageinit-snap-trigger" in changed_ids:
        # TODO
        raise Exception("not implemented yet")
    if "ltp-start-time" in changed_ids:
        if levels is None:
            return dash.no_update
        storages = TypeAdapter(dict[str, StorageLevel]).validate_json(levels)
        for level in storages.values():
            level.timestamp = start_time
    return TypeAdapter(dict[str, StorageLevel]).dump_json(storages).decode("utf-8")


@callback(Output("ltp-init-availabilities-result", "children"),
            Input("ltp-availability-buffer", "data"),  # FIXME are we sure the persistence method is triggered first?
            State("ltp-start-time", "value"),
            State("ltp-horizon-weeks", "value")
)
def set_initial_availabilities(_: Any, start_time: datetime|str, horizon: str|int):
    persistence = state.get_availability_persistence()
    start, end = _get_start_end_time(start_time, horizon)
    if start is None or end is None:
        return "Not available"
    plants: dict[int, Equipment] = {p.id: p for p in state.get_site().equipment}
    plant_data: dict[int, list[EquipmentAvailability]] = persistence.load_all(start, end)
    days = end - start
    hours_per_plant: dict[int, timedelta] = {pid: days for pid in plants.keys() if pid not in plant_data}
    hours_per_plant.update({pid: ModelUtils.aggregate_availabilities(avail, start, end) for pid, avail in plant_data.items()})
    # sort according to plants array
    hours_per_plant = dict(sorted(hours_per_plant.items(), key=lambda key_val: next(idx for idx, pid in enumerate(plants.keys()) if pid == key_val[0])))
    return [html.Div(f"{plants[pid].name_short}: {round(period.total_seconds()/3_600)}h") for pid, period in hours_per_plant.items()]


@callback(Output("ltp-start", "disabled"),
          Output("ltp-start", "title"),
          Output("ltp-stop", "disabled"),
          Output("ltp-stop", "title"),
          Output("ltp-amount-selected", "children"),
          Output("ltp-interval", "interval"),
          Output("ltp-running-indicator", "hidden"),
          Output("ltp-result-container", "hidden"),
          Output("ltp-result-id", "children"),
          Input("ltp-start", "n_clicks"),
          Input("ltp-stop", "n_clicks"),
          Input("ltp-interval", "n_intervals"),
          Input("ltp-material-setpoints", "data"),  # keys: material class id, values: production / t
          Input("ltp-storage-levels", "data"),
          State("ltp-start-time", "value"),
          State("ltp-horizon-weeks", "value"),
          State("ltp-shift-hours", "value"),
          State("ltp-production-total", "value"),
          config_prevent_initial_callbacks=True)
def check_start_stop(_, __, ___, setpoints: dict[str, float], storage_levels: str|None, start_time: datetime|str, horizon_weeks: str|int, shift_duration_hours: str|int,
                     total_production: float|str|None):
    if not dash_authenticated(config):
        return None
    is_running, new_solution_id = check_running_optimization()
    total_amount = _get_total_selected_amount(setpoints)
    changed_ids = GuiUtils.changed_ids()
    if not is_running and "ltp-start" in changed_ids:
        try:
            start_time = DatetimeUtils.parse_date(start_time)
            if start_time is None:
                raise Exception("Start time is None")
            horizon_weeks = int(horizon_weeks)
            if horizon_weeks <= 0:
                raise Exception("Horizon must be positive, got " + str(horizon_weeks))
            shift_duration_hours = allowed_shift_durations[int(shift_duration_hours)]
            if total_production is None:
                raise Exception("Total production not set")
            else:
                total_production = float(total_production)
            if total_production <= 0:
                raise ValueError("Total production must be positive, got " + str(total_production))
            if storage_levels is None:
                raise Exception("Storage levels not defined yet")
        except:  # TODO display error
            raise
        if ltp_thread is None and total_amount is not None:
            levels = TypeAdapter(dict[str, StorageLevel]).validate_json(storage_levels)
            start(start_time, horizon_weeks, shift_duration_hours, setpoints, total_production, levels)
    if "ltp-stop" in changed_ids and ltp_thread is not None:
        stop()
    is_running = ltp_thread is not None
    itv = 3_000 if is_running else 3_600_000
    if not is_running:
        result_container_hidden = new_solution_id is None
        new_solution_id = new_solution_id if new_solution_id is not None else ""
        amount_msg = "Total production target: " + str(total_amount) + " t" if total_amount is not None else ""
        if total_amount is None or storage_levels is None:
            return (True,  # start disabled
                    "Material structure or storage levels not defined, yet. Please open the structure portfolio menu and select the material to produce.", # start title
                    True,  # end disabled
                    "Not running.",  # end title
                    amount_msg,  # selected amount
                    itv,  # polling interval,
                    True,   # running indicator hidden
                    result_container_hidden,   # result container hidden
                    new_solution_id      # result id
                    )
        return (False,  # start disabled
                "Run long-term planning.", # start title
                True,  # end disabled
                "Not running.",  # end title
                amount_msg,  # selected amount
                itv,  # polling interval
                True,  # running indicator hidden
                result_container_hidden,  # result container hidden
                new_solution_id # result id
                )
    return (True,  # start disabled
            "Already running.", # start title
            False,  # end disabled
            "Stop optimization.",  # end title
            "Total production target: " + str(total_amount) + " t",   # selected amount  # TODO retrieve from running optimization
            itv,  # polling interval
            False,  # running indicator hidden
            True,  # result container hidden
            ""  # result id
            )


def check_running_optimization() -> tuple[bool, str|None]:
    global ltp_thread
    solution_id = None
    if ltp_thread is not None:
        if not ltp_thread.is_alive():
            solution_id = ltp_thread.id()
            ltp_thread = None
    return ltp_thread is not None, solution_id


def start(start_time: datetime, horizon_weeks: int, shift_duration_hours: int, setpoints: dict[str, float], total_production: float, storage_levels: dict[str, StorageLevel]):
    global ltp_thread
    shift_duration = timedelta(hours=shift_duration_hours)
    end_time = start_time + timedelta(weeks=horizon_weeks)
    shifts: list[tuple[datetime, datetime]] = []
    start_shift = start_time
    end_shift = start_shift + shift_duration
    while end_shift <= end_time:
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
    # TODO option not to store results?
    persistence = state.get_results_persistence()
    new_id = "ltp_" + DatetimeUtils.format(DatetimeUtils.now(), use_zone=False)
    actual_id = new_id
    cnt: int = 0
    while persistence.has_solution_ltp(start_time, actual_id):
        cnt += 1
        actual_id = new_id + "_" + str(cnt)
    ltp_thread = LTPKillableOptimizationThread(actual_id, ltp, ltp_targets, initial_storage_levels=storage_levels, shifts=shifts, persistence=persistence)
    ltp_thread.start()


def stop() -> bool:
    global ltp_thread
    if ltp_thread is not None:
        ltp_thread.kill()
        ltp_thread = None
    return ltp_thread is None



class LTPKillableOptimizationThread(threading.Thread):

    def __init__(self,
                 id: str,
                 optimization: LongTermPlanning,
                 structure: LongTermTargets,
                 initial_storage_levels: dict[str, StorageLevel]|None=None,
                 shifts: list[tuple[datetime, datetime]]|None=None,
                 persistence: ResultsPersistence|None = None):
        super().__init__(name=ltp_thread_name)
        self._id = id
        self._kill = threading.Event()
        self.daemon = True  # Allow main to exit even if still running.
        self._optimization = optimization
        self._structure = structure
        self._initial_storage_levels = initial_storage_levels
        self._shifts = shifts
        self._persistence = persistence

    def id(self):
        return self._id

    def kill(self):
        self._kill.set()

    def run(self):
        solution_id = self._id
        results, storage_levels = self._optimization.run(solution_id, self._structure, initial_storage_levels=self._initial_storage_levels,
                                      shifts=self._shifts)  # TODO pass plant_availabilities (last argument)
        if self._persistence:
            self._persistence.store_ltp(solution_id, results, storage_levels=storage_levels)
        return results

