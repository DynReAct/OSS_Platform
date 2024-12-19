from datetime import timedelta, datetime, date
from typing import Literal

import dash
from dash import html, dcc, callback, Output, Input
import dash_ag_grid as dash_ag
from pydantic import BaseModel

from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Order
from pydantic.fields import FieldInfo

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.gui.pages.session_state import selected_snapshot

dash.register_page(__name__, path="/")
translations_key = "snapshot"


def layout(*args, **kwargs):
    start_date, end_date, snap_options, selected_snap = get_date_range(selected_snapshot.data)  # : tuple[date, date, list[datetime], str]
    return html.Div([
        #selected_snapshot,  # in dash_app layout
        html.H1("Snapshots"),
        html.H2("Snapshot selection", id="snapshot-select_header"),
        html.Div([
            html.Div([html.Div("Active snapshot: ", id="snapshot-active"), dcc.Dropdown(id="snapshots-selector", className="snap-select",
                                                                        options=snap_options, value=selected_snap)]),
            html.Div([html.Div("Selection range: ", id="snapshot-selection_range"),
            dcc.DatePickerRange(id="snapshots-date-range", display_format="YYYY-MM-DD", start_date=start_date, end_date=end_date)])
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
            style={"height": "90vh", "width": "100%", "margin-bottom": "25em"},
            columnSizeOptions={"defaultMinWidth": 125},
            columnSize="responsiveSizeToFit"  # "autoSize"  # "responsiveSizeToFit" => this leads to essentially vanishing column size
        ),
    ], id="snapshot")


# FIXME here the selection value modifies the selection range
#@callback(
#    Output("snapshots-date-range", "start_date"),
#    Output("snapshots-date-range", "end_date"),
#    Output("snapshots-selector", "options"),
#    Output("snapshots-selector", "value"),
#    Input("selected-snapshot", "data"),
#)
def get_date_range(current_snapshot: str|datetime|None) -> tuple[date, date, list[datetime], str]:  # list[options] not list[datetime]
    if not dash_authenticated(config):
        return None, None, [], None
    # 1) snapshot already selected
    current: datetime | None = DatetimeUtils.parse_date(current_snapshot)
    if current is None:
        # 3) use current snapshot
        current = state.get_snapshot_provider().current_snapshot_id()
    if current is None:  # should not really happen
        now = DatetimeUtils.now()
        return (now - timedelta(days=30)).date(), (now + timedelta(days=1)).date(), [], None
    dates = []
    cnt = 0
    iterator = state.get_snapshot_provider().snapshots(start_time=current - timedelta(days=90), end_time=current + timedelta(minutes=1), order="desc") #if current_snapshot is None \
        #else state.get_snapshot_provider().snapshots(start_time=current - timedelta(hours=2), end_time=current + timedelta(days=90), order="asc")
    for dt in iterator:
        dates.append(dt)
        if cnt > 100:  # ?
            break
        cnt += 1
    dates = sorted(dates, reverse=True)
    if len(dates) == 0:
        return None, None, [], None
    to_be_selected = dates[0]
    min_dist = abs(to_be_selected - current)
    for dt in dates:
        distance = abs(dt - current)
        if distance < min_dist:
            to_be_selected = dt
            min_dist = distance
    options = [{"label": snap_id, "value": snap_id, "selected": selected} for snap_id, selected in ((DatetimeUtils.format(d), d == to_be_selected) for d in dates)]
    if len(options) == 1:
        dt = dates[0].date()
        return dt - timedelta(days=1), dt + timedelta(days=1), options, DatetimeUtils.format(to_be_selected)
    return dates[-1].date(), dates[0].date(), options, DatetimeUtils.format(to_be_selected)


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
    fields = [column_def_for_field(key, info) for key, info in snapshot.orders[0].model_fields.items() if (key not in ["material", "lot", "lot_position" ])] + \
             ([column_def_for_field(key, info) for key, info in snapshot.orders[0].material_properties.model_fields.items()] if \
                  snapshot.orders[0].material_properties is not None and isinstance(snapshot.orders[0].material_properties, BaseModel) else [])
    # Note: format cell is defined in snapshot.js, it is actually in the namespace "dashAgGridFunctions",
    # see https://dash.plotly.com/dash-ag-grid/javascript-and-the-grid
    value_formatter_object = {"function": "formatCell(params.value)"}
    for field in fields:
        if field["field"] == "id":
            field["pinned"] = True
        if field["field"] in ["lots", "lot_positions", "active_processes", "coil_status", "follow_up_processes"]:
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
