from datetime import timedelta, datetime, date
from typing import Literal
from zoneinfo import ZoneInfo

import dash
from dash import html, dcc, callback, Output, Input
import dash_ag_grid as dash_ag
from pydantic import BaseModel

from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.MaterialAggregation import MaterialAggregation
from dynreact.base.model import Order, MaterialCategory
from pydantic.fields import FieldInfo

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.gui.pages.session_state import selected_snapshot, get_date_range, init_stores

dash.register_page(__name__, path="/")
translations_key = "snapshot"


def layout(*args, **kwargs):
    init_stores(*args, **kwargs)
    categories = state.get_site().material_categories
    return html.Div([
        #selected_snapshot,  # in dash_app layout
        html.H1("Snapshots"),
        html.H2("Snapshot selection", id="snapshot-select_header"),
        html.Div([
            html.Div([html.Div("Active snapshot: ", id="snapshot-active"), dcc.Dropdown(id="snapshots-selector", className="snap-select")]),
            html.Div([html.Div("Selection range: ", id="snapshot-selection_range"),
            dcc.DatePickerRange(id="snapshots-date-range", display_format="YYYY-MM-DD")])
        ], className="snapshots-selector-row"),
        html.H2("Snapshot details", id="snapshot-details_header"),
        html.Div([html.Div("Display: ", id="snapshot-display_label"), dcc.Dropdown(id="order-coil-selector", className="snap-select", options=[
            # TODO localization of options?
            {"label": "Coils", "value": "coils", "id": "opt1"}, {"label": "Orders", "value": "orders"}], value="orders")], className="coil-order-row"),
        html.Br(),
        dash_ag.AgGrid(
            id="snapshot-table",
            columnDefs=[{"field": "id", "pinned": True}],
            rowData=[],
            className="ag-theme-alpine",  # ag-theme-alpine-dark
            style={"height": "90vh", "width": "100%"},
            columnSizeOptions={"defaultMinWidth": 125},
            columnSize="responsiveSizeToFit"  # "autoSize"  # "responsiveSizeToFit" => this leads to essentially vanishing column size
        ),
        html.H2("Material aggregation", id="snapshot-materials_header"),
        html.Div([
            html.Div("Material category: ", id="snapshot-matcat_label"), dcc.Dropdown(id="snapshot_matcat-selector", className="snap-select",
                    options=[{"label": cat.name or cat.id, "value": cat.id} for cat in categories], value=next((c.id for c in categories), None)),
            html.Div("Aggregation level: ", id="snapshot-matlevel_label"),
            dcc.Dropdown(id="snapshot_mat_level-selector", className="snap-select",
                         options=[
                             {"label": "Storage", "value": "storage"},
                             {"label": "Equipment", "value": "equipment"},
                             {"label": "Process", "value": "process"}
                         ], value="process")
        ], className="snap-matselect-grid"),
        html.Br(),
        dash_ag.AgGrid(
            id="snapshot-mat-table",
            # columns depend on selected category
            columnDefs=[{"field": "id", "pinned": True}],
            rowData=[],
            className="ag-theme-alpine",  # ag-theme-alpine-dark
            style={"height": "90vh", "width": "100%", "margin-bottom": "25em"},
            columnSizeOptions={"defaultMinWidth": 125},
            columnSize="responsiveSizeToFit"
            # "autoSize"  # "responsiveSizeToFit" => this leads to essentially vanishing column size
        ),
    ], id="snapshot")

def _material_overview(categories: list[MaterialCategory]):
    if categories is None or len(categories) == 0:
        return html.Div()
    return html.Div([html.H2("Material aggregation", id="snapshot-materials_header"),
    html.Div([
        html.Div("Material category: ", id="snapshot-matcat_label"),
        dcc.Dropdown(id="snapshot_matcat-selector", className="snap-select",
                     options=[{"label": cat.name or cat.id, "value": cat.id} for cat in categories],
                     value=next((c.id for c in categories), None)),
        html.Div("Aggregation level: ", id="snapshot-matlevel_label"),
        dcc.Dropdown(id="snapshot_mat_level-selector", className="snap-select",
                     options=[
                         {"label": "Storage", "value": "storage"},
                         {"label": "Equipment", "value": "equipment"},
                         {"label": "Process", "value": "process"}
                     ], value="process")
    ], className="snap-matselect-grid"),
    html.Br(),
    dash_ag.AgGrid(
        id="snapshot--mat-table",
        # columns depend on selected category
        columnDefs=[{"field": "id", "pinned": True}],
        rowData=[],
        className="ag-theme-alpine",  # ag-theme-alpine-dark
        style={"height": "92vh", "width": "100%", "margin-bottom": "25em"},
        columnSizeOptions={"defaultMinWidth": 125},
        columnSize="responsiveSizeToFit"
        # "autoSize"  # "responsiveSizeToFit" => this leads to essentially vanishing column size
    )])


@callback(
    Output("snapshots-selector", "options"),
    Output("snapshots-selector", "value"),
    Output("snapshots-date-range", "start_date"),
    Output("snapshots-date-range", "end_date"),
    Input("client-tz", "data")  # client timezone, defined in dash_app
)
def set_snapshot_options(tz: str|None):
    zi = None
    try:
        zi = ZoneInfo(tz)
    except:
        pass
    start_date, end_date, snap_options, selected_snap = get_date_range(selected_snapshot.data, zi=zi)
    return snap_options, selected_snap, start_date, end_date



@callback(
    Output("selected-snapshot", "data"),
    Output("selected-snapshot-obj", "data"),
    Input("snapshots-selector", "value")
)
def set_snapshot(snapshot_id: str):
    timestamp = DatetimeUtils.parse_date(snapshot_id)
    snap = state.get_snapshot(timestamp)
    if snap is None:
        return None, None
    return timestamp, snap.model_dump(exclude_unset=True, exclude_none=True)


@callback(
    Output("snapshot-table", "columnDefs"),
    Output("snapshot-table", "rowData"),
    Input("selected-snapshot", "data"),
    Input("order-coil-selector", "value")
)
def snapshot_selected(snapshot_id: datetime|str|None, order_coil: Literal["orders", "coils"]):
    if not dash_authenticated(config):
        return [{"field": "id", "pinned": True}], []
    snapshot_id = DatetimeUtils.parse_date(snapshot_id)
    snapshot = state.get_snapshot(snapshot_id) if snapshot_id is not None else None
    if snapshot is None or len(snapshot.material) == 0:
        return [{"field": "id", "pinned": True}], []
    site = state.get_site()

    def column_def_for_field(field: str, info: FieldInfo):
        filter_id = "agNumberColumnFilter" if info.annotation == float or info.annotation == int else \
            "agDateColumnFilter" if info.annotation == datetime or info.annotation == date else \
                "agTextColumnFilter"
        col_def = {"field": field, "filter": filter_id}
        return col_def
    if order_coil == "coils":
        fields = [column_def_for_field(key, info) for key, info in snapshot.material[0].model_fields.items()]  # TODO how to sort?
        return fields, [coil.model_dump(exclude_none=True, exclude_unset=True) for coil in snapshot.material]
    # TODO how to sort?
    fields = [column_def_for_field(key, info) for key, info in snapshot.orders[0].model_fields.items() if (key not in ["material_properties", "material_status", "lot", "lot_position" ])] + \
             ([column_def_for_field(key, info) for key, info in snapshot.orders[0].material_properties.model_fields.items()] if \
                  snapshot.orders[0].material_properties is not None and isinstance(snapshot.orders[0].material_properties, BaseModel) else [])
    # Note: format cell is defined in snapshot.js, it is actually in the namespace "dashAgGridFunctions",
    # see https://dash.plotly.com/dash-ag-grid/javascript-and-the-grid
    value_formatter_object = {"function": "formatCell(params.value)"}
    for field in fields:
        if field["field"] == "id":
            field["pinned"] = True
        if field["field"] in ["lots", "lot_positions", "active_processes", "coil_status", "follow_up_processes", "target_weight", "actual_weight", "material_classes"]:
            field["valueFormatter"] = value_formatter_object

    def order_to_json(o: Order):
        as_dict = o.model_dump(exclude_none=True, exclude_unset=True)
        #for key in ["lots", "lot_positions"]:
        #    if key in as_dict:
        #        as_dict[key] = json.dumps(as_dict[key])
        if o.allowed_equipment is not None:
            as_dict["allowed_plants"] = [next((plant.name_short for plant in site.equipment if plant.id == p), str(p)) for p in o.allowed_equipment]
        if o.current_equipment is not None:
            as_dict["current_plants"] = [next((plant.name_short for plant in site.equipment if plant.id == p), str(p)) for p in o.current_equipment]
        if isinstance(o.material_properties, BaseModel):
            as_dict.update(o.material_properties.model_dump(exclude_none=True, exclude_unset=True))
        return as_dict
    return fields, [order_to_json(order) for order in snapshot.orders]


@callback(
    Output("snapshot-mat-table", "columnDefs"),
    Output("snapshot-mat-table", "rowData"),
    Input("selected-snapshot", "data"),
    Input("snapshot_matcat-selector", "value"),  #
    Input("snapshot_mat_level-selector", "value"),  # storage, equipment or process
)
def fill_material_table(snapshot_id: str, category: str|None, aggregation_level: Literal["storage", "equipment", "process"]|None):
    if not dash_authenticated(config) or not snapshot_id or not category or not aggregation_level:
        return [{"field": "id", "pinned": True}], []
    timestamp = DatetimeUtils.parse_date(snapshot_id)
    snap = state.get_snapshot(timestamp)
    cat = next((cat for cat in state.get_site().material_categories if cat.id == category), None)
    if not snap or not cat:
        return [{"field": "id", "pinned": True}], []
    value_formatter_object = {"function": "formatCell(params.value, 5)"}
    column_defs = [{"field": "id", "pinned": True, "headerName": aggregation_level.capitalize()}] + \
            [{"field": clz.id, "headerName": clz.name or clz.id, "valueFormatter": value_formatter_object} for clz in cat.classes]
    aggr = MaterialAggregation(state.get_site(), state.get_snapshot_provider())
    result_by_plant = aggr.aggregate_categories_by_plant(snap)
    result = result_by_plant
    if aggregation_level == "storage":
        result = aggr.aggregate_by_storage(result_by_plant)
    elif aggregation_level == "process":
        result = aggr.aggregate_by_process(result_by_plant)
    keys = result.keys()
    clz_results: dict[str|int, dict[str, float]] = {key: result[key].get(category) for key in keys if category in result[key]}
    if aggregation_level == "equipment":
        plants = {plant.id: plant.name_short or str(plant.id) for plant in state.get_site().equipment}
        clz_results = {plants.get(key) + " (" + str(key) + ")" if key in plants else str(key): value for key, value in clz_results.items()}

    def total_value(clz_id: str) -> float:
        return sum(plant_results.get(clz_id, 0) for plant_results in clz_results.values())

    total_values = {clz.id: total_value(clz.id) for clz in cat.classes}
    total_values["id"] = "Total"

    def merge_dicts(d1: dict, d2: dict):
        d1.update(d2)
        return d1

    row_data = [total_values] + [merge_dicts(weight_per_class, {"id": key}) for key, weight_per_class in clz_results.items()]
    return column_defs, row_data

