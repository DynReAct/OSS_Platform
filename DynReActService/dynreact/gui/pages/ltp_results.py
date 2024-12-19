from datetime import datetime, timedelta, date

import dash
from dash import html, dcc, callback, Output, Input, clientside_callback, ClientsideFunction, State
import dash_ag_grid as dash_ag
from dynreact.base.LongTermPlanning import LongTermPlanning
from dynreact.base.PlantAvailabilityPersistence import PlantAvailabilityPersistence
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import LongTermTargets, EquipmentAvailability, StorageLevel, MidTermTargets

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.gui.gui_utils import GuiUtils
from dynreact.gui.pages.plants_graph import plants_graph, default_stylesheet

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
                dashGridOptions={"rowSelection": "single"}
                ## tooltipField is not used, but it must match an existing field for the tooltip to be shown
                # defaultColDef={"tooltipComponent": "CoilsTooltip", "tooltipField": "id"},
                # dashGridOptions={"rowSelection": "multiple", "suppressRowClickSelection": True, "animateRows": False,
                #                 "tooltipShowDelay": 100, "tooltipInteraction": True,
                #                 "popupParent": {"function": "setCoilPopupParent()"}},
                ## "autoSize"  # "responsiveSizeToFit" => this leads to essentially vanishing column size
            )
        ),

        html.Div([
            html.Div("Process Panel"),
            html.Div([
                html.Div([
                    html.Div([
                        html.Div("Product type:"),
                        dcc.Dropdown(options=materials, className="ltp_res-prodtype")
                    ], className="ltp_res-prodtype-selection"),
                    plants_graph("ltp_res-plants-graph", style={"width": str(num_processes * 10) + "em", "height": "500px"}, *args,  **kwargs)
                ]),
                # TODO indicate start, end and selected date below!
                dcc.Slider(id="ltp_res-date-ctrl", className="ltp_res-date-ctrl", min=0, max=1, step=1),  # max=4, step=1, value=horizon_days),  # date selector as a slider
                #dcc.Input(type="range", id="ltp_res-date-ctrl", className="ltp_res-date-ctrl", min=0, max=1, step=1, list="ltp_res_dateslist"),  # max=4, step=1, value=horizon_days),  # date selector as a slider
                #html.Datalist(id="ltp_res_dateslist")  # TODO ticks for the range input: https://developer.mozilla.org/en-US/docs/Web/HTML/Element/datalist
            ], className="ltp_res-panel-flex")
        ], className="control-panel ltp_res-panel", id="ltp_res-process-panel"),
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
        return []
    #parsed_date = parsed.date()
    persistence: ResultsPersistence = state.get_results_persistence()
    solutions: list[str] = persistence.solutions_ltp(parsed)  # TODO is this exact? Or could we specify a range?
    solutions2: list[MidTermTargets] = [persistence.load_ltp(parsed, s)[0] for s in solutions]  # TODO here we ignore storage levels for the time being
    columns = [{
            "id": solutions[idx],
            "time_horizon": (t.period[1] - t.period[0]) / timedelta(weeks=1),
            "shift_duration": (t.sub_periods[0][1] - t.sub_periods[0][0]) / timedelta(hours=1),
            "total_production": t.total_production,
            #"delete": ""   # not possible
        } for idx, t in enumerate(solutions2)]
    return columns, columns


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


@callback(
    Output("ltp_res-date-ctrl", "max"),
    Output("ltp_res-date-ctrl", "marks"),
    Input("ltp_res-selected-solution", "data"),
    State("ltp_res-starttime-selector", "value")

          )
def solution_changed(solution: dict[str, any]|None, starttime: str|None):
    parsed: datetime = DatetimeUtils.parse_date(starttime)
    if solution is None or parsed is None:
        return 1, None
    days = solution.get("time_horizon", 0) * 7
    marker_indices = range(days)
    if days > 8:
        num_marks = 8
        marker_indices = [round(0 + idx * (days-1)/(num_marks-1)) for idx in range(num_marks)]
        if (days-1) not in marker_indices:
            marker_indices.append(days-1)
    marks = {day: (parsed + timedelta(days=day)).strftime("%y-%m-%d") for day in marker_indices}
    return days, marks

