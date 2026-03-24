from datetime import datetime, timedelta, date, time
from typing import Literal, Mapping

import dash
from dash import html, dcc, callback, Output, Input, clientside_callback, ClientsideFunction, State
import dash_ag_grid as dash_ag
from pydantic import TypeAdapter
from typing_extensions import Any

from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import LongTermTargets, EquipmentAvailability, StorageLevel, MidTermTargets

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.gui.gui_utils import GuiUtils

dash.register_page(__name__, path="/ltp/planned")
translations_key = "ltp_res"


def layout(*args, **kwargs):
    selected_start_date0: datetime|None = DatetimeUtils.parse_date(kwargs.get("start"))
    selected_start_date = selected_start_date0.date() if selected_start_date0 is not None else None
    start, end, start_time_options, selected = get_date_range(selected_start_date)
    site = state.get_site()
    num_processes = len(site.processes)
    materials = site.material_categories
    selected_material = kwargs.get("material") or kwargs.get("mat")
    selected_material = selected_material if selected_material is not None and next((m for m in materials if m.id == selected_material), None) is not None \
        else materials[0].id
    initial_solution_id = None if selected is None else kwargs.get("solution")
    materials = [{"value": mat.id, "label": mat.name if mat.name is not None else mat.id, "selected": mat.id == selected_material} for mat in materials]
    anim_tab_active: bool = kwargs.get("tab") is not None and kwargs.get("tab").lower() in ("anim", "animation")
    tabular_tab_active = not anim_tab_active
    tabular_tab_class = _tab_button_class(tabular_tab_active)
    anim_tab_class = _tab_button_class(anim_tab_active)
    return html.Div([
        html.H1("Long term planning results", id="ltp_res-title"),
        html.Div([
            html.Div([html.Div("Start date: "), dcc.Dropdown(id="ltp_res-starttime-selector",  className="ltp_res-startselect",
                                                             options=start_time_options, value=selected.strftime("%Y-%m-%d") if selected is not None else None)]),
            html.Div([html.Div("Selection range: ", id="ltp_res-selection-range"),
                   dcc.DatePickerRange(id="ltp-res-date-range", display_format="YYYY-MM-DD", start_date=start, end_date=end)])
        ], className="ltp_res-selector-row"),
        html.H2("Solutions"),
        html.Div(
            dash_ag.AgGrid(
                id="ltp_res-solutions-table",
                columnDefs=[{"field": "id", "pinned": True},
                            {"field": "time_horizon", "filter": "agDateColumnFilter", "headerName": "Time horizon / w"},
                            {"field": "shift_duration", "filter": "agNumberColumnFilter", "headerName": "Shift duration / h"},
                            {"field": "total_production", "filter": "agNumberColumnFilter", "headerName": "Total production / t" },
                            # {"field": "delete"} # not possible
                            ],
                defaultColDef={"filter": "agTextColumnFilter", "filterParams": {"buttons": ["reset"]}},
                rowData=[],
                getRowId="params.data.id",
                className="ag-theme-alpine",  # ag-theme-alpine-dark
                # style={"height": "70vh", "width": "100%", "margin-bottom": "5em"},
                columnSizeOptions={"defaultMinWidth": 125},
                columnSize="responsiveSizeToFit",
                dashGridOptions={"rowSelection": "single", "domLayout": "autoHeight"},
                style={"height": None},  # required with autoHeight
                ## tooltipField is not used, but it must match an existing field for the tooltip to be shown
                # defaultColDef={"tooltipComponent": "CoilsTooltip", "tooltipField": "id"},
                # dashGridOptions={"rowSelection": "multiple", "suppressRowClickSelection": True, "animateRows": False,
                #                 "tooltipShowDelay": 100, "tooltipInteraction": True,
                #                 "popupParent": {"function": "setCoilPopupParent()"}},
                ## "autoSize"  # "responsiveSizeToFit" => this leads to essentially vanishing column size
            )
        ),
        html.Div([
            html.Div([
                html.Button("Table", id="ltp_res-tabular-btn", className=tabular_tab_class, title="Tabular view of the long-term planning results"),
                html.Button("Animation", id="ltp_res-anim-btn", className=anim_tab_class, title="Animation of the long-term planning results"),
                html.Div()
            ], className="ltp_res-tabs", hidden=True),

            html.Div([
                _tabular_tab(not tabular_tab_active),
                _anim_tab(not anim_tab_active),
            ], className="ltp_res-tabs-container"),
        ], id="ltp_res-tabs-hider", hidden=True),
        dcc.Store(id="ltp_res-active-tab", data="tabular" if tabular_tab_active else "anim", storage_type="memory"),  # either tabular or anim
        dcc.Store(id="ltp_res-solutions"),              # array of json docs
        dcc.Store(id="ltp_res-selected-solution-id"),   # string
        dcc.Store(id="ltp_res-selected-solution"),      # json doc
        dcc.Store(id="initial_solution_id", data=initial_solution_id),
        dcc.Store(id="ltp_res-client-init", storage_type="memory"),  # to ensure the selected ltp solution is transferred to the client before running any script there
   ])

def _tabular_tab(hidden: bool):
    return html.Div([
        html.H2("Equipment production"),
        html.Div(
            dash_ag.AgGrid(
                id="ltp_res-plants-table",
                columnDefs=[{"field": "day", "pinned": True}],
                defaultColDef={"filter": "agTextColumnFilter", "filterParams": {"buttons": ["reset"]}},
                rowData=[],
                getRowId="params.data.day",
                className="ag-theme-alpine",  # ag-theme-alpine-dark
                # columnSizeOptions={"defaultMinWidth": 125},
                columnSize="responsiveSizeToFit",
                dashGridOptions={"rowSelection": "single", "domLayout": "autoHeight"},
                style={"height": None}  # required with autoHeight
                ## tooltipField is not used, but it must match an existing field for the tooltip to be shown
                # defaultColDef={"tooltipComponent": "CoilsTooltip", "tooltipField": "id"},
                # dashGridOptions={"rowSelection": "multiple", "suppressRowClickSelection": True, "animateRows": False,
                #                 "tooltipShowDelay": 100, "tooltipInteraction": True,
                #                 "popupParent": {"function": "setCoilPopupParent()"}},
                ## "autoSize"  # "responsiveSizeToFit" => this leads to essentially vanishing column size
            )
        ),
        html.H2("Storage levels"),
        html.Div([html.Div("Storage level: ", id="ltp-storage-snapshot"),
                  dcc.Dropdown(id="ltp-res_storage-absrel", className="snap-select", value="relative",
                               options=[{"value": "relative", "label": "Relative", "title": "Show storage filling level in percentage."},
                                        {"value": "absolute", "label": "Absolute", "title": "Show storage filling level in tons."}])
                  ], className="ltp-res-absrel-flex"),
        html.Br(),
        html.Div(
            dash_ag.AgGrid(
                id="ltp_res-storages-table",
                columnDefs=[{"field": "day", "pinned": True}],
                defaultColDef={"filter": "agTextColumnFilter", "filterParams": {"buttons": ["reset"]}},
                rowData=[],
                getRowId="params.data.day",
                className="ag-theme-alpine",  # ag-theme-alpine-dark
                # columnSizeOptions={"defaultMinWidth": 125},
                columnSize="responsiveSizeToFit",
                dashGridOptions={"rowSelection": "single", "domLayout": "autoHeight"},
                style={"height": None}  # required with autoHeight
                ## tooltipField is not used, but it must match an existing field for the tooltip to be shown
                # defaultColDef={"tooltipComponent": "CoilsTooltip", "tooltipField": "id"},
                # dashGridOptions={"rowSelection": "multiple", "suppressRowClickSelection": True, "animateRows": False,
                #                 "tooltipShowDelay": 100, "tooltipInteraction": True,
                #                 "popupParent": {"function": "setCoilPopupParent()"}},
                ## "autoSize"  # "responsiveSizeToFit" => this leads to essentially vanishing column size
            )
        )
    ], id="ltp_res-tabular-tab", hidden=hidden)

def _anim_tab(hidden: bool):
    return html.Div([
        "Test!"
    ], id="ltp_res-anim-tab", hidden=hidden)


@callback(Output("ltp_res-active-tab", "data"),
          Input("ltp_res-tabular-btn", "n_clicks"),
          Input("ltp_res-anim-btn", "n_clicks"))
def set_active_tab(_, __) -> str|None:
    if not dash_authenticated(config):
        return None
    changed_ids = GuiUtils.changed_ids()
    return "tabular" if "ltp_res-tabular-btn" in changed_ids else "anim" if "ltp_res-anim-btn" in changed_ids else dash.no_update


@callback(Output("ltp_res-tabular-btn", "className"),
        Output("ltp_res-anim-btn", "className"),
        Input("ltp_res-active-tab", "data"))
def highlight_active_tab(active_tab: Literal["tabular", "anim"]|None):
    tab_selected: bool = active_tab == "tabular"
    anim_selected: bool = active_tab == "anim"
    return _tab_button_class(tab_selected), _tab_button_class(anim_selected)

def _tab_button_class(selected: bool) -> str:
    name = "ltp_res-tab-button"
    if selected:
        name += " ltp_res-tab-button-active"
    return name

@callback(
    Output("ltp_res-tabular-tab", "hidden"),
    Output("ltp_res-anim-tab", "hidden"),
    Input("ltp_res-active-tab", "data"))
def apply_active_tab(active_tab: Literal["tabular", "anim"]|None):
    if not active_tab:
        return True, True
    return active_tab != "tabular", active_tab != "anim"


def get_date_range(start_date: date|None=None) -> tuple[date, date, list[date], date]:
    """
    :param start_date:
    :return: start, end, list of start times, selected start time
    """
    if not dash_authenticated(config):
        return None, None, [], None
    persistence: ResultsPersistence = state.get_results_persistence_aggregate()
    if start_date is not None:
        start_times: list[datetime] = persistence.start_times_ltp(start=DatetimeUtils.date_to_datetime(start_date - timedelta(days=65), utc=False),
                        end=DatetimeUtils.date_to_datetime(start_date + timedelta(days=65), utc=False))
    else:
        start_times = persistence.start_times_ltp(sort="desc", limit=50)
    start_dates: list[date] = _start_times_to_dates(start_times)
    start_date = start_date if start_date is not None and start_date in start_dates else start_dates[0] if len(start_dates) > 0 else None
    if start_date is None:
        return None, None, [], None
    options = [{"label": snap_id, "value": snap_id, "selected": selected} for snap_id, selected in ((d.strftime("%Y-%m-%d"), d == start_date) for d in start_dates)]
    if len(options) == 1:
        dt = start_dates[0]
        return dt - timedelta(days=1), dt + timedelta(days=1), options, dt
    return start_date - timedelta(days=150), start_date + timedelta(days=1), options, start_date


def _start_times_to_dates(lst: list[datetime]) -> list[date]:
    result = list(set(state.as_timezone(l).date() for l in lst))
    result.sort(reverse=True)
    return result


@callback(Output("ltp_res-solutions", "data"),
          Output("ltp_res-solutions-table", "rowData"),
          Output("ltp_res-solutions-table", "selectedRows"),
          Input("ltp_res-starttime-selector", "value"),
          State("ltp_res-solutions-table", "selectedRows"),
          State("initial_solution_id", "data"))
def find_solutions(starttime: str|None, selected_rows: list[dict[str, any]|str]|None, initial_solution_id: str|None):
    parsed = DatetimeUtils.parse_date(starttime)
    if parsed is None or not dash_authenticated(config):
        return [], [], []
    parsed = state.replace_timezone(parsed)
    #parsed_date = parsed.date()
    persistence: ResultsPersistence = state.get_results_persistence_aggregate()
    solutions: list[str] = sorted(persistence.solutions_ltp(parsed), reverse=True)
    solutions2: list[tuple[MidTermTargets, list[dict[str, StorageLevel]]|None]] = [persistence.load_ltp(parsed, s) for s in solutions]
    rows = [{
            "id": solutions[idx],
            "time_horizon": round((t[0].period[1] - t[0].period[0]) / timedelta(days=1)),
            "shift_duration": round((t[0].sub_periods[0][1] - t[0].sub_periods[0][0]) / timedelta(hours=1)),
            "total_production": t[0].total_production,
            "targets": t[0].model_dump(exclude_unset=True, exclude_none=True),
            "storage_levels": TypeAdapter(list[dict[str, StorageLevel]]).dump_python(t[1])
        } for idx, t in enumerate(solutions2)]
    table_rows = [{k: v if k != "time_horizon" else round(v/7) for k, v in r.items()} for r in rows]
    if len(rows) > 0 and initial_solution_id is not None and (selected_rows is None or (isinstance(selected_rows, dict) and len(selected_rows["ids"]) == 0) or len(selected_rows) == 0):
        selected_rows = {"ids": [initial_solution_id]}
    return rows, table_rows, selected_rows


# on table row selection change the selected solution
@callback(Output("ltp_res-selected-solution-id", "data"),
        Output("ltp_res-selected-solution", "data"),
        Output("ltp_res-tabs-hider", "hidden"),
        Input("ltp_res-solutions-table", "selectedRows"),
        Input("ltp_res-solutions", "data"))
def solution_selected(selected_rows: list[dict[str, any]|str]|None, solutions: list[dict[str, any]]|None):
    if isinstance(selected_rows, dict):
        selected_rows = selected_rows["ids"]
    if solutions is None or len(solutions) == 0 or selected_rows is None or len(selected_rows) == 0:
        return None, None, True
    sol_id = selected_rows[0].get("id", None) if isinstance(selected_rows[0], Mapping) else selected_rows[0]
    if sol_id is None:
        return None, None, True
    try:
        sol = next(s for s in solutions if s.get("id", None) == sol_id) if solutions is not None else None
        return sol_id, sol, False
    except StopIteration:
        return None, None, True


@callback(
    Output("ltp_res-plants-table", "columnDefs"),
    Output("ltp_res-plants-table", "rowData"),
    Input("ltp_res-selected-solution", "data")
)
def update_plants_table(solution: dict[str, Any]):
    if solution is None or not dash_authenticated(config):
        return [{"field": "day", "pinned": True}], None
    targets = solution.get("targets")  # serialized MidTermTargets
    sub_periods: list[tuple[datetime, datetime]] = [(DatetimeUtils.parse_date(period[0]), DatetimeUtils.parse_date(period[1])) for period in targets.get("sub_periods")]
    sub_targets = targets.get("production_sub_targets")  # serialized  dict[str, list[ProductionTargets]], keys = process ids
    site = state.get_site()
    procs = [p for p in site.processes if p.name_short in sub_targets]
    value_formatter_object = {"function": "formatCell(params.value, 4)"}
    column_defs = [{"field": str(plant.id), "headerName": str(plant.name_short or plant.name or plant.id), "valueFormatter": value_formatter_object,
                    "headerTooltip": f"{plant.name_short or plant.name} ({plant.id})" } for proc in procs for plant in site.get_process_equipment(proc.name_short)]
    column_defs = [{"field": "day", "pinned": True}] + column_defs
    row_data = []
    current_day: date = sub_periods[0][0].astimezone().date()
    current_data: dict[int|str, Any] = {"day": current_day.strftime("%Y-%m-%d")}
    for idx, period in enumerate(sub_periods):
        day = period[0].astimezone().date()
        if day != current_day:
            row_data.append(current_data)
            current_data = {"day": day.strftime("%Y-%m-%d")}
            current_day = day
        for proc in procs:
            period_targets = sub_targets.get(proc.name_short)[idx]
            for plant, plant_targets in period_targets.get("target_weight").items():
                if plant not in current_data:
                    current_data[plant] = 0
                current_data[plant] += plant_targets.get("total_weight")
    row_data.append(current_data)
    row_data = [{k: v if not isinstance(v, float|int) or v > 0.01 else 0 for k, v in row.items()} for row in row_data]
    return column_defs, row_data  # FIXME row_data looks ok, but the first day is missing in GUI


@callback(
    Output("ltp_res-storages-table", "columnDefs"),
    Output("ltp_res-storages-table", "rowData"),
    Input("ltp_res-selected-solution", "data"),
    Input("ltp-res_storage-absrel", "value"),
)
def update_storages_table(solution: dict[str, Any], rel_abs: Literal["relative", "absolute"]|None):
    if solution is None or rel_abs is None or not dash_authenticated(config):
        return [{"field": "day", "pinned": True}], None
    levels = solution.get("storage_levels")  # serialized list[dict[str, StorageLevel]]
    sub_periods: list[tuple[datetime, datetime]] = [(state.replace_timezone(DatetimeUtils.parse_date(period[0])),
                                                     state.replace_timezone(DatetimeUtils.parse_date(period[1]))) for period in solution.get("targets").get("sub_periods")]
    site = state.get_site()
    value_formatter_object = {"function": "formatCell(params.value, 4)"}
    column_defs = [{"field": storage.name_short, "headerName": str(storage.name or storage.name_short), "valueFormatter": value_formatter_object}
                        for storage in site.storages]
    column_defs = [{"field": "day", "pinned": True, "headerTooltip": "Storage level at 6 am"}] + column_defs
    row_data = []
    is_absolute = rel_abs == "absolute"
    storage_capacities = {s.name_short: s.capacity_weight for s in site.storages}
    for idx, period in enumerate(sub_periods):
        # display a single value per day, not all shifts XXX
        if period[0].time().hour not in (6,7,8,9,10):
            continue
        current_levels = levels[idx]
        current_data = {"day": period[0].date().strftime("%Y-%m-%d")}
        for stg, stg_level in current_levels.items():
            value = stg_level.get("filling_level", 0)
            current_data[stg] = f"{round(value*100)}%" if not is_absolute else value * storage_capacities.get(stg, 1)
        row_data.append(current_data)
    # TODO final level
    return column_defs, row_data

clientside_callback(
    ClientsideFunction(
        namespace="dynreact",
        function_name="setLtp"
    ),
    Output("ltp_res-client-init", "data"),
    Input("ltp_res-selected-solution", "data")
)

clientside_callback(
    ClientsideFunction(
        namespace="ltp",
        function_name="create_ltp_animation",
    ),
    Output("ltp_res-anim-tab", "title"),
    Input("ltp_res-client-init", "data"),
    State("ltp_res-anim-tab", "id")
)
