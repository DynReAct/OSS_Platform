from datetime import datetime, timedelta, date, time
from typing import Literal

import dash
from dash import html, dcc, callback, Output, Input, clientside_callback, ClientsideFunction, State
import dash_ag_grid as dash_ag
from pydantic import TypeAdapter
from typing_extensions import Any

from dynreact.base.LongTermPlanning import LongTermPlanning
from dynreact.base.PlantAvailabilityPersistence import PlantAvailabilityPersistence
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import LongTermTargets, EquipmentAvailability, StorageLevel, MidTermTargets

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
# from dynreact.gui.gui_utils import GuiUtils
# from dynreact.gui.pages.plants_graph import plants_graph, default_stylesheet

dash.register_page(__name__, path="/ltp/planned")
translations_key = "ltp_res"


def layout(*args, **kwargs):
    selected_start_date: date|None = DatetimeUtils.parse_date(kwargs.get("start"))
    selected_start_date = selected_start_date.date() if selected_start_date is not None else None
    start, end, start_time_options, selected = get_date_range(selected_start_date)
    site = state.get_site()
    num_processes = len(site.processes)
    materials = site.material_categories
    selected_material = kwargs.get("material") or kwargs.get("mat")
    selected_material = selected_material if selected_material is not None and next((m for m in materials if m.id == selected_material), None) is not None \
        else materials[0].id
    materials = [{"value": mat.id, "label": mat.name if mat.name is not None else mat.id, "selected": mat.id == selected_material} for mat in materials]
    return html.Div([
        html.H1("Long term planning results", id="ltp_res-title"),
        html.Div([
            html.Div([html.Div("Start date: "), dcc.Dropdown(id="ltp_res-starttime-selector",  className="ltp_res-startselect",
                                                             options=start_time_options, value=selected.strftime("%Y-%m-%d") if selected is not None else None)]),
            html.Div([html.Div("Selection range: ", id="ltp_res-selection-range"),
                   dcc.DatePickerRange(id="snapshots-date-range", display_format="YYYY-MM-DD", start_date=start, end_date=end)])
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
                style={"height": None}  # required with autoHeight
                ## tooltipField is not used, but it must match an existing field for the tooltip to be shown
                # defaultColDef={"tooltipComponent": "CoilsTooltip", "tooltipField": "id"},
                # dashGridOptions={"rowSelection": "multiple", "suppressRowClickSelection": True, "animateRows": False,
                #                 "tooltipShowDelay": 100, "tooltipInteraction": True,
                #                 "popupParent": {"function": "setCoilPopupParent()"}},
                ## "autoSize"  # "responsiveSizeToFit" => this leads to essentially vanishing column size
            )
        ),


        #html.Div([
        #    html.Div("Process Panel"),
        #    html.Div([
        #        html.Div([
        #            html.Div([
        #                html.Div("Product type:"),
        #                dcc.Dropdown(options=materials, className="ltp_res-prodtype")
        #            ], className="ltp_res-prodtype-selection"),
        #            plants_graph("ltp_res-plants-graph", style={"width": str(num_processes * 10) + "em", "height": "500px"}, *args,  **kwargs)
        #        ]),
        #        # TODO indicate start, end and selected date below!
        #        dcc.Slider(id="ltp_res-date-ctrl", className="ltp_res-date-ctrl", min=0, max=1, step=1),  # max=4, step=1, value=horizon_days),  # date selector as a slider
        #        #dcc.Input(type="range", id="ltp_res-date-ctrl", className="ltp_res-date-ctrl", min=0, max=1, step=1, list="ltp_res_dateslist"),  # max=4, step=1, value=horizon_days),  # date selector as a slider
        #        #html.Datalist(id="ltp_res_dateslist")  # TODO ticks for the range input: https://developer.mozilla.org/en-US/docs/Web/HTML/Element/datalist
        #    ], className="ltp_res-panel-flex")
        #], className="control-panel ltp_res-panel", id="ltp_res-process-panel"),

        html.H2("Equipment production"),
        html.Div(
            dash_ag.AgGrid(
                id="ltp_res-plants-table",
                columnDefs=[{"field": "day", "pinned": True}],
                defaultColDef={"filter": "agTextColumnFilter", "filterParams": {"buttons": ["reset"]}},
                rowData=[],
                getRowId="params.data.day",
                className="ag-theme-alpine",  # ag-theme-alpine-dark
                #columnSizeOptions={"defaultMinWidth": 125},
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
        ),


        dcc.Store(id="ltp_res-solutions"),              # array of json docs
        dcc.Store(id="ltp_res-selected-solution-id"),   # string
        dcc.Store(id="ltp_res-selected-solution"),      # json doc
   ])


def get_date_range(start_date: date|None=None) -> tuple[date, date, list[date], date]:
    """
    :param start_date:
    :return: start, end, list of start times, selected start time
    """
    if not dash_authenticated(config):
        return None, None, [], None
    persistence: ResultsPersistence = state.get_results_persistence()
    if start_date is None:
        start_date = datetime.now()  # beginning of next month
        start_date = (start_date.replace(day=1, minute=0, second=0, microsecond=0) + timedelta(days=32)).replace(day=1).date()
    start_times: list[datetime] = persistence.start_times_ltp(DatetimeUtils.date_to_datetime(start_date - timedelta(days=150)),
                                                                DatetimeUtils.date_to_datetime(start_date + timedelta(days=1)))
    start_dates: list[date] = _start_times_to_dates(start_times)
    start_date = start_date if start_date is not None and start_date in start_dates else None  # ?
    if start_date is None:
        return None, None, [], None
    options = [{"label": snap_id, "value": snap_id, "selected": selected} for snap_id, selected in ((d.strftime("%Y-%m-%d"), d == start_date) for d in start_dates)]
    if len(options) == 1:
        dt = start_dates[0]
        return dt - timedelta(days=1), dt + timedelta(days=1), options, dt
    return start_date - timedelta(days=150), start_date + timedelta(days=1), options, start_date


def _start_times_to_dates(lst: list[datetime]) -> list[date]:
    result = list(set(l.date() for l in lst))
    result.sort()
    return result


@callback(Output("ltp_res-solutions", "data"),
          Output("ltp_res-solutions-table", "rowData"),
          Input("ltp_res-starttime-selector", "value"))
def find_solutions(starttime: str|None):
    parsed = DatetimeUtils.parse_date(starttime)
    if parsed is None:
        return [], []
    #parsed_date = parsed.date()
    persistence: ResultsPersistence = state.get_results_persistence()
    solutions: list[str] = persistence.solutions_ltp(parsed)  # TODO is this exact? Or could we specify a range?
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
    return rows, table_rows


# on table row selection change the selected solution
@callback(Output("ltp_res-selected-solution-id", "data"),
        Output("ltp_res-selected-solution", "data"),
        Input("ltp_res-solutions-table", "selectedRows"),
        State("ltp_res-solutions", "data"))
def solution_selected(selected_rows: list[dict[str, any]]|None, solutions: list[dict[str, any]]|None):
    if selected_rows is None or len(selected_rows) == 0:
        return None, None
    sol_id = selected_rows[0].get("id", None)
    if sol_id is None:
        return None, None
    sol = next(s for s in solutions if s.get("id", None) == sol_id) if solutions is not None else None
    return sol_id, sol


#@callback(
#    Output("ltp_res-date-ctrl", "max"),
#    Output("ltp_res-date-ctrl", "marks"),
#    Input("ltp_res-selected-solution", "data"),
#    State("ltp_res-starttime-selector", "value")
#)
#def solution_changed(solution: dict[str, any]|None, starttime: str|None):
#    parsed: datetime = DatetimeUtils.parse_date(starttime)
#    if solution is None or parsed is None:
#        return 1, None
#    days = solution.get("time_horizon", 0)
#    marker_indices = range(days)
#    if days > 8:
#        num_marks = 8
#        marker_indices = [round(0 + idx * (days-1)/(num_marks-1)) for idx in range(num_marks)]
#        if (days-1) not in marker_indices:
#            marker_indices.append(days-1)
#    marks = {day: (parsed + timedelta(days=day)).strftime("%y-%m-%d") for day in marker_indices}
#    return days, marks


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
    current_day: date = sub_periods[0][0].date()
    current_data: dict[int|str, Any] = {"day": current_day.strftime("%Y-%m-%d")}
    for idx, period in enumerate(sub_periods):
        day = period[0].date()
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
    sub_periods: list[tuple[datetime, datetime]] = [(DatetimeUtils.parse_date(period[0]), DatetimeUtils.parse_date(period[1])) for period in solution.get("targets").get("sub_periods")]
    site = state.get_site()
    value_formatter_object = {"function": "formatCell(params.value, 4)"}
    column_defs = [{"field": storage.name_short, "headerName": str(storage.name or storage.name_short), "valueFormatter": value_formatter_object}
                        for storage in site.storages]
    column_defs = [{"field": "day", "pinned": True, "headerTooltip": "Storage level at 6 am"}] + column_defs
    row_data = []
    is_absolute = rel_abs == "absolute"
    storage_capacities = {s.name_short: s.capacity_weight for s in site.storages}
    for idx, period in enumerate(sub_periods):
        if period[0].time().hour != 8:  # 6:  # FIXME hardcoded
            continue
        current_levels = levels[idx]
        current_data = {"day": period[0].date().strftime("%Y-%m-%d")}
        for stg, stg_level in current_levels.items():
            value = stg_level.get("filling_level", 0)
            current_data[stg] = f"{round(value*100)}%" if not is_absolute else value * storage_capacities.get(stg, 1)
        row_data.append(current_data)
    # TODO final level
    return column_defs, row_data

