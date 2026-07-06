from datetime import timedelta, datetime
import dash_ag_grid as dash_ag

import dash
from dash import html, clientside_callback, ClientsideFunction, Output, Input, State, dcc, callback

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.gui.pages.components import lots_view, lots_view_options

dash.register_page(__name__, path="/lots-gantt")
translations_key = "lots-gantt"
cnt = 0


def layout(*args, **kwargs):
    value_formatter_object = {"function": "formatCell(params.value, 4, 4)"}
    return html.Div([
        html.H1("Lots", id="lots-gantt-title"),
        lots_view("lots-gantt", initial_hidden=False, ids_toggle=True),
        dcc.Store(id="lots-gantt-undefined", storage_type="memory"),
        dcc.Store(id="lots-gantt-undefined2", storage_type="memory"),
        dcc.Store(id="lots-gantt-shifts", storage_type="memory"),
        html.Br(),html.Br(),html.Br(),
        html.H2("Table view", id="lots-gantt-table-header"),
        html.Div([
            html.Span("Select equipment: ", id="lots-gantt-equipment-label"),
            dcc.Dropdown(id="lots-gantt-equipment-select",
                         options=[{"value": e.id, "label": e.name_short or str(e.id), "title": e.name or e.name_short or str(e.id)} for e in state.get_site().equipment],
                         multi=True),
            html.Span(),
            html.Span("Select material type: ", id="lots-gantt-mat-label"),
            dcc.Dropdown(id="lots-gantt-material-select",
                         options=[{"value": cat.id, "label": cat.name or str(cat.id),
                                   "title": cat.description or cat.name or str(cat.id)} for cat in state.get_site().material_categories],
                         value=next((cat.id for cat in state.get_site().material_categories), None)),
            html.Span()
        ], className="lots-gantt-equipment"),
        html.Div([
            dash_ag.AgGrid(
                id="lots-gantt-lots-table",
                columnDefs=[{"field": "lot", "pinned": True},
                            {"field": "equipment", "headerTooltip": "Equipment this lot applies to."},
                            {"field": "priority", "headerTooltip": "Lot priority"},
                            {"field": "start", "filter": "agDateColumnFilter", "headerTooltip": "Lot start time"},
                            {"field": "end", "filter": "agDateColumnFilter", "headerTooltip": "Lot end time"},
                            {"field": "status", "filter": "agNumberColumnFilter", "headerTooltip": "Lot status", },
                            {"field": "active", "headerTooltip": "Lot active?"},
                            {"field": "weight", "filter": "agNumberColumnFilter", "headerTooltip": "Total lot weight in tons", "headerName": "Weight / t" , "valueFormatter": value_formatter_object},
                            {"field": "orders_cnt", "headerTooltip": "Number of orders included in the lot", "headerName": "Orders"},
                            {"field": "material", "headerTooltip": "Number of material units included in the lot", "headerName": "Material",
                                    "cellDataType": False, "cellRenderer": "RenderMaterialClasses" },
                            {"field": "comment", "headerTooltip": "Lot comment"},
                            {"field": "orders", "headerTooltip": "Order ids included in the lot", "headerName": "Order ids"},],
                defaultColDef={"filter": "agTextColumnFilter", "filterParams": {"buttons": ["reset"]}},
                rowData=[],
                getRowId="params.data.lot",
                className="ag-theme-alpine",  # ag-theme-alpine-dark
                # style={"height": "70vh", "width": "100%", "margin-bottom": "5em"},
                columnSizeOptions={"defaultMinWidth": 125},
                columnSize="responsiveSizeToFit",
                dashGridOptions={"rowSelection": "single", "domLayout": "autoHeight", "rowHeight": 60},
                style={"height": None},
        )], className="lots-gantt-table-parent"),  # relative positioning
        html.Br(),html.Br(),
    ], id="lots-gantt")

@callback(
    Output("lots-gantt-swimlane-mode", "options"),
    Input("lang", "data"),
)
def lang_changed(lang: str|None):
    return lots_view_options(lang)


@callback(
    Output("lots-gantt-undefined", "data"),
    Output("lots-gantt-undefined2", "data"),
    Output("lots-gantt-shifts", "data"),
    Input("selected-snapshot", "data"),
)
def _snapshot_updated(snap: str|None):
    global cnt
    snap = DatetimeUtils.parse_date(snap)
    if snap is None or not dash_authenticated(config):
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
    Input("lots-gantt-lotid-toggle", "value"),
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

clientside_callback(
    ClientsideFunction(
        namespace="createlots",
        function_name="showLotsSwimlaneIds"
    ),
    Output("lots-gantt-lotid-toggle", "title"),
    Input("lots-gantt-lotid-toggle", "value"),
    State("lots-gantt-lots-swimlane", "id")
)

@callback(
    Output("lots-gantt-lots-table", "rowData"),
    Input("lots-gantt-equipment-select", "value"),
    Input("lots-gantt-material-select", "value"),
    State("selected-snapshot", "data"),
)
def show_lots(equipments, material_cat: str|None, snapshot: str|datetime|None):
    snapshot = DatetimeUtils.parse_date(snapshot)
    if not snapshot or not equipments or not dash_authenticated(config):
        return None
    snap_obj = state.get_snapshot(time=snapshot)
    rows = []
    empty = tuple()
    mat_cat = None
    mat_classes = None
    mat_labels = None
    if material_cat is not None and material_cat != "":
        mat_cat = next(cat for cat in state.get_site().material_categories if cat.id == material_cat)
        mat_classes = [cl.id for cl in mat_cat.classes]
        mat_labels = {cl.id: cl.name or cl.id for cl in mat_cat.classes}
    all_colors = ["red", "green", "blue", "yellow"]  # TODO
    num_colors = len(all_colors)
    colors = {mat: all_colors[idx % num_colors] for idx, mat in enumerate(mat_classes)}
    for eq in equipments:
        eq_obj = state.get_site().get_equipment(eq, do_raise=True)
        for lot in snap_obj.lots.get(eq, empty):
            classes = {"material": {mat: weight for mat, weight in lot.material_weights.items() if mat in mat_classes}, "colors": colors,
                       "labels": mat_labels } if mat_classes is not None and lot.material_weights is not None else None
            row = {
                "lot": lot.id,
                "equipment": eq_obj.name_short or str(eq_obj.id),
                "priority": getattr(lot, "priority", None),
                "start": DatetimeUtils.format(state.as_timezone(lot.start_time), use_zone=False).replace("T", " ") if lot.start_time else None,
                "end": DatetimeUtils.format(state.as_timezone(lot.end_time), use_zone=False).replace("T", " ") if lot.end_time else None,
                "status": lot.status,
                "active": lot.active,
                "orders_cnt": len(lot.orders),
                "weight": lot.weight,
                "material": classes,
                "comment": lot.comment,
                "orders": ", ".join(lot.orders)
            }
            rows.append(row)
    return rows

clientside_callback(
    ClientsideFunction(
        namespace="createlots",
        function_name="attachPieChartEventListener"
    ),
    Output("lots-gantt-lots-table", "title"),
    Input("lots-gantt-lots-table", "rowData"),
    State("lots-gantt-lots-table", "id")
)

