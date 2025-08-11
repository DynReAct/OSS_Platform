import threading
import traceback
from datetime import datetime, date
from typing import Iterable, Any
import uuid

import dash
from dash import html, callback, Input, Output, dcc, State, clientside_callback, ClientsideFunction
import dash_ag_grid as dash_ag
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from dynreact.base.LotSink import LotSink
from dynreact.base.LotsOptimizer import LotsOptimizationState
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.ModelUtils import ModelUtils
from dynreact.base.model import ProductionPlanning, EquipmentStatus, Lot, Order, Material, Snapshot, Equipment, \
    ObjectiveFunction, MaterialCategory

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.gui.gui_utils import GuiUtils
from dynreact.gui.pages.components import lots_view

dash.register_page(__name__, path="/lots/planned")
translations_key = "lotsplanning"

lottransfer_thread_name = "lottransfer"
lottransfer_thread: threading.Thread|None = None
# key: opaque lot identifier used to differentiate user sessions
lottransfer_results: dict[str, any] = {}


# TODO display "proprietary" columns in table (in PlantStatus#planning) => they need to be marked somehow, or we simply include all additional ones
# TODO display also the snapshot solution and/or due dates solution?
# FIXME the number of orders shown in the table seems lower than in the lot creation settings?
def layout(*args, **kwargs):
    process: str | None = kwargs.get("process")  # TODO use store from main layout instead
    lot_size: str|None = kwargs.get("lotsize", "weight")   # constant, weight, orders, coils are allowed values
    site = state.get_site()
    return html.Div([
        html.H1("Lots planning", id="lotsplanning-title"),
        html.Div([
            html.Div([html.Div("Snapshot: "), html.Div(id="current_snapshot_lotplanning")]),
            html.Div([html.Div("Process: "), dcc.Dropdown(id="process-selector-lotplanning",
                                                          options=[{"value": p.name_short, "label": p.name_short,
                                                                    "title": p.name if p.name is not None else p.name_short}
                                                                   for p in site.processes],
                                                          value=process, className="process-selector", persistence=True)]),
            html.Div([
                dcc.Link(html.Button("Open lot creation", className="dynreact-button"), id="plan-link-create",
                         href="/dash/lots/create2", target="_blank")
            ]),
        ], className="create-selector-flex"),
        html.H2("Solutions"),
        html.Div(
            dash_ag.AgGrid(
                id="plan-solutions-table",
                columnDefs=[],
                defaultColDef={"filter": "agTextColumnFilter", "filterParams": {"buttons": ["reset"]}},
                rowData=[],
                getRowId="params.data.id",
                className="ag-theme-alpine",  # ag-theme-alpine-dark
                # style={"height": "70vh", "width": "100%", "margin-bottom": "5em"},
                columnSizeOptions={"defaultMinWidth": 125},
                columnSize="responsiveSizeToFit",
                dashGridOptions={"rowSelection": "single", "domLayout": "autoHeight"},
                style={"height": None}
                ## tooltipField is not used, but it must match an existing field for the tooltip to be shown
                #defaultColDef={"tooltipComponent": "CoilsTooltip", "tooltipField": "id"},
                #dashGridOptions={"rowSelection": "multiple", "suppressRowClickSelection": True, "animateRows": False,
                #                 "tooltipShowDelay": 100, "tooltipInteraction": True,
                #                 "popupParent": {"function": "setCoilPopupParent()"}},
                ## "autoSize"  # "responsiveSizeToFit" => this leads to essentially vanishing column size
            )
        ),
        lots_view("planning", *args, **kwargs),
        html.Div([
            html.H2("Structure"),
            html.Div(id="lotplanning-structure-view", className="lotplanning-structure-container")
        ], id="lotplanning-structure-container", hidden=True),
        html.Div([
            html.H2("Lots"),
            html.Button("Download lots csv", id="download-csv", className="dynreact-button"),
            html.Br(),html.Br(),
            html.Div(
                dash_ag.AgGrid(
                    id="planning-lots-table",
                    columnDefs=[{"field": "id", "pinned": True},
                                {"field": "plant"},
                                {"field": "num_orders", "filter": "agNumberColumnFilter", "headerName": "Orders"},
                                {"field": "num_coils", "filter": "agNumberColumnFilter", "headerName": "Coils"},
                                {"field": "total_weight", "filter": "agNumberColumnFilter", "headerName": "Weight / t"},
                                {"field": "order_ids", "headerName": "Order ids", "tooltipField": "order_ids"},
                                {"field": "first_due_date", "headerName": "Due", "filter": "agDateColumnFilter",
                                    "headerTooltip": "The earliest due date of the orders included", "tooltipField": "all_due_dates"},
                                {"field": "active"},
                                ],
                    defaultColDef={"filter": "agTextColumnFilter", "filterParams": {"buttons": ["reset"]}},
                    dashGridOptions={"tooltipShowDelay": 250, "rowSelection": "single", "domLayout": "autoHeight"},
                    rowData=[],
                    getRowId="params.data.id",
                    className="ag-theme-alpine",  # ag-theme-alpine-dark
                    # style={"height": None, "width": "100%", "margin-bottom": "5em"},
                    style={"height": None},   # required with autoHeight
                    columnSizeOptions={"defaultMinWidth": 125},
                    columnSize="responsiveSizeToFit",
                )
            ),
            html.H2("Orders"),
            html.Button("Download orders csv", id="download-orders-csv", className="dynreact-button"),
            html.Br(), html.Br(),
            html.Div(
                dash_ag.AgGrid(
                    id="planning-lots-order-table",
                    columnDefs=[{"field": "order", "pinned": True},
                                {"field": "lot"}],
                    # defaultColDef={"filter": "agTextColumnFilter", "filterParams": {"buttons": ["reset"]}},
                    dashGridOptions={"tooltipShowDelay": 250, "rowSelection": "single"},
                    rowData=[],
                    getRowId="params.data.order",
                    className="ag-theme-alpine",  # ag-theme-alpine-dark
                    # style={"height": "70vh", "width": "100%", "margin-bottom": "5em"},
                    style={"margin-bottom": "10em"},
                    columnSizeOptions={"defaultMinWidth": 125},
                    columnSize="responsiveSizeToFit",
                )
            )
        ], id="planning-lots-table-wrapper", hidden=True),
        transfer_popup(),
        dcc.Store(id="planning-selected-solution"),  # str
        dcc.Store(id="planning-solution-data"),      # rowData, list of dicts, one row per lot
        dcc.Store(id="planning-selected-lot"),       # lot id; selected by clicking a row in the lots table
        # opaque lot identifier
        dcc.Store(id="lotplanning-transferred-lot"),
        dcc.Store(id="lotplanning-transfer-message"),
        dcc.Store(id="lotplanning-transfer-type"),
        dcc.Store(id="lotplanning-material-structure"),   # { mat category id: { name: str, classes: { mat class id: {name: cl name, weight: aggregated weight} } } }
        dcc.Store(id="lotplanning-material-targets"),     # dict[str, float]

        dcc.Interval(id="planning-interval", n_intervals=3_600_000),  # for polling when lot transfer is running
    ], id="lotsplanned")


def transfer_popup():
    sinks = state.get_lot_sinks()
    #if len(sinks) == 0:   # TODO then we'd miss the callback targets
    #    return html.Div()
    return html.Dialog(
        html.Div([
            html.H3("Lot transfer"),
            html.Div([
                html.Div("Selected lot: "),
                html.Div(id="lotplanning-transfer-selectedlot"),
                html.Div("New lot name", title="Name of the lot to be transferred"),
                dcc.Input(id="lotplanning-transfer-lotname"),
                html.Div("Orders:"),
                dcc.Dropdown(id="lotplanning-transfer-oders", className="lotplanning-transfer-orders", multi=True),
                html.Div("Transfer to", title="Target system the lot will be transferred to"),
                dcc.Dropdown(id="lotplanning-transfer-target", className="lotplanning-transfer-target",
                             options=[{"value": sink_id, "label": sink.label(), "title": sink.description()} for sink_id, sink in sinks.items()],
                             value=next((sink_id for sink_id in sinks.keys()), None)),
            ], className="lotplanning-transfer-grid", id="lotplanning-transfer-grid"),

            html.Div([
                html.Button("Transfer", id="lotplanning-transfer-start", className="dynreact-button"),
                html.Button("Cancel", id="lotplanning-transfer-cancel", className="dynreact-button")
            ], className="lotplanning-transfer-buttons")
        ]),
        id="lotplanning-transfer-dialog", className="dialog-filled lotplanning-transfer-dialog", open=False)


@callback(Output("current_snapshot_lotplanning", "children"),
          Input("selected-snapshot", "data"),
          Input("client-tz", "data")  # client timezone, global store
)
def snapshot_changed(snapshot: datetime|str|None, tz: str|None) -> str:
    return GuiUtils.format_snapshot(snapshot, tz)

@callback(
    Output("plan-link-create", "href"),
    State("selected-snapshot", "data"),
    Input("process-selector-lotplanning", "value"),
    #Input("create-existing-sols", "value"),
)
def update_link(snapshot: str|datetime|None, process: str|None) -> str:
    url = "/dash/lots/create2"
    if not dash_authenticated(config):
        return url
    snapshot = DatetimeUtils.parse_date(snapshot)
    if snapshot is None or process is None:
        return url
    url += "?process=" + process + "&snapshot=" + DatetimeUtils.format(snapshot)
    return url


@callback(
    Output("plan-solutions-table", "columnDefs"),
    Output("plan-solutions-table", "rowData"),
    State("selected-snapshot", "data"),
    Input("process-selector-lotplanning", "value"),
    #Input("create-existing-sols", "value"),
)
def solutions_table(snapshot: str|datetime|None, process: str|None):
    if not dash_authenticated(config):
        return []
    snapshot = DatetimeUtils.parse_date(snapshot)
    value_formatter_object = {"function": "formatCell(params.value, 4)"}
    col_defs: list[dict[str, Any]] = [{"field": "id", "pinned": True},
         {"field": "target_production", "filter": "agNumberColumnFilter", "headerName": "Target Production / t", "valueFormatter": value_formatter_object},
         {"field": "initialization"},
         {"field": "target_fct", "filter": "agNumberColumnFilter", "headerName": "Target function", "valueFormatter": value_formatter_object,
          "headerTooltip": "Value of the objective function. The lower the better, but results are only comparable for the same target weights and init settings."},
         {"field": "iterations", "filter": "agNumberColumnFilter"},
         {"field": "orders_considered", "filter": "agNumberColumnFilter", "headerName": "Orders",
          "headerTooltip": "Number of orders considered in the lot creation, including those not assigned to a lot."},
         {"field": "lots", "filter": "agNumberColumnFilter"},
         {"field": "plants"},
         {"field": "comment"},
         #{"field": "transition_costs", "filter": "agNumberColumnFilter", "headerName": "Transition costs"},
         {"field": "performance_models", "headerName": "Performance models",
          "headerTooltip": "Plant performance models considered"},
    ]
    if snapshot is None or process is None:
        return col_defs, []
    persistence = state.get_results_persistence()
    solutions: list[str] = persistence.solutions(snapshot, process)
    sol_objects: dict[str, LotsOptimizationState] = {sol: persistence.load(snapshot, process, sol) for sol in solutions}
    snap_planning, snap_targets = state.get_snapshot_solution(process, snapshot)
    snap_objective: ObjectiveFunction = state.get_cost_provider().process_objective_function(snap_planning)
    total_production = sum(t.total_weight for t in snap_targets.target_weight.values())
    sol_objects["_SNAPSHOT_"] = LotsOptimizationState(best_solution=snap_planning, current_solution=snap_planning,
                        best_objective_value=snap_objective, current_objective_value=snap_objective,
                        parameters={"targets": "snapshot", "initialization": "planning", "target_production": total_production})
    # dd_planning, dd_targets = state.get_due_date_solution(process, snapshot)
    # dd_objective = state.get_cost_provider().process_objective_function(dd_planning)
    #
    #sol_objects["_DUE_DATE_"] = LotsOptimizationState(best_solution=dd_planning, current_solution=dd_planning,
    #                      best_objective_value=dd_objective, current_objective_value=dd_objective,
    #                      parameters={"targets": "snapshot", "initialization": "duedate", "target_production": sum(dd_targets.target_weight.values())})
    #
    params: dict[str, dict[str, any]] = {sol: state.parameters if state.parameters is not None else {} for sol, state in sol_objects.items()}
    best_planning: dict[str, ProductionPlanning] = {sol: state.best_solution for sol, state in sol_objects.items()}
    plant_statuses: dict[str, list[EquipmentStatus]] = {sol: list(planning.equipment_status.values()) for sol, planning in best_planning.items()}
    site = state.get_site()

    random_sol = next(value for key, value in sol_objects.items() if key != "_SNAPSHOT_" or len(sol_objects) <= 1)
    objective_keys = [f for f in random_sol.current_object_value.model_dump().keys() if f != "total_value"]
    col_defs.extend([{"field": f, "filter": "agNumberColumnFilter", "valueFormatter": value_formatter_object} for f in objective_keys])

    def merge_dicts(d1: dict, d2: dict) -> dict:
        d1.update(d2)
        return d1
    row_data = [merge_dicts({
        "id": sol_id,
        "comment": params[sol_id].get("comment"),
        "target_production": params[sol_id].get("target_production"),
        "initialization": params[sol_id].get("initialization"),
        "target_fct": solution.best_objective_value.total_value,
        "iterations": len(solution.history),
        "orders_considered": len(best_planning[sol_id].order_assignments),
        "lots": sum(status.planning.lots_count if status.planning is not None else 0 for status in plant_statuses[sol_id]),
        "plants": [site.get_equipment(status.targets.equipment).name_short for status in plant_statuses[sol_id]],
        #"transition_costs": sum(status.planning.transition_costs if status.planning is not None else 0 for status in plant_statuses[sol_id]),
        #"weight_costs": sum(status.planning.delta_weight * delta_weight_costs if status.planning is not None else 0 for status in plant_statuses[sol_id]),
        "performance_models": params[sol_id].get("performance_models")
    },
       {key: (getattr(solution.best_objective_value, key) if hasattr(solution.best_objective_value, key) else 0) or 0 for key in objective_keys })
                for sol_id, solution in sol_objects.items()]
    return col_defs, row_data


@callback(
    Output("planning-selected-solution", "data"),
    Input("plan-solutions-table", "selectedRows"),
)
def solution_selected(selected_rows: list[dict[str, any]]|None) -> str|None:
    if selected_rows is None or len(selected_rows) == 0:
        return None
    row = selected_rows[0]
    return row["id"] if isinstance(row, dict) else row

@callback(
    Output("planning-lots-table-wrapper", "hidden"),
    Output("planning-lots-table", "rowData"),
    Output("planning-solution-data", "data"),
    Output("planning-lotsview-header", "hidden"),
    Output("planning-lots-order-table", "columnDefs"),
    Output("planning-lots-order-table", "rowData"),
    Output("lotplanning-material-structure", "data"),
    Output("lotplanning-material-targets", "data"),
    Output("lotplanning-structure-container", "hidden"),
    State("selected-snapshot", "data"),
    State("process-selector-lotplanning", "value"),
    Input("planning-selected-solution", "data"),
)
def solution_changed(snapshot: str|datetime|None, process: str|None, solution: str|None):
    snapshot = DatetimeUtils.parse_date(snapshot)
    if not dash_authenticated(config) or process is None or snapshot is None or solution is None:
        return True, None, None, True, None, None, None, None, True
    best_result: ProductionPlanning
    if solution == "_SNAPSHOT_":
        best_result = state.get_snapshot_solution(process, snapshot)[0]
    elif solution == "_DUE_DATE_":
        best_result = state.get_due_date_solution(process, snapshot)[0]
    else:
        result: LotsOptimizationState = state.get_results_persistence().load(snapshot, process, solution)
        if result is None or result.best_solution is None:
            return True, None, None, True, None, None, None, None, True
        best_result = result.best_solution
    lots: list[Lot] = [lot for plant_lots in best_result.get_lots().values() for lot in plant_lots]
    unassigned_order_ids: list[str] = [ass.order for ass in best_result.order_assignments.values() if ass.lot == ""]
    site = state.get_site()
    plants = {p.id: p for p in site.equipment}
    snap_obj = state.get_snapshot(snapshot)
    orders_by_lot: dict[str, list[Order|None]] = {}
    for lot in lots:
        lot_orders = [None for order in lot.orders]
        for order in snap_obj.orders:
            try:
                idx = lot.orders.index(order.id)
                lot_orders[idx] = order
                try:
                    lot_orders.index(None)
                except ValueError:
                    break
            except ValueError:
                continue
        orders_by_lot[lot.id] = lot_orders
    unassigned_orders: dict[str, Order] = {}
    for order in snap_obj.orders:
        if order.id in unassigned_order_ids:
            unassigned_orders[order.id] = order
            if len(unassigned_orders) == len(unassigned_order_ids):
                break
    all_due_dates = {lot: [o.due_date for o in orders if o is not None] for lot, orders in orders_by_lot.items()}
    first_due_dates = {lot: min((o.due_date for o in orders if o is not None and o.due_date is not None), default=DatetimeUtils.to_datetime(0)) for lot, orders in orders_by_lot.items()}
    total_weights = {lot: sum(o.actual_weight if o.actual_weight is not None else (o.target_weight if o.target_weight is not None else 0)
                for o in orders if o is not None) for lot, orders in orders_by_lot.items()}
    all_coils_by_orders: dict[str, list[Material]] = state.get_coils_by_order(snapshot)
    num_coils = {lot: sum(len(all_coils_by_orders[o.id]) if o.id in all_coils_by_orders else 0 for o in orders if o is not None) for lot, orders in orders_by_lot.items()}

    def row_for_lot(lot: Lot) -> dict[str, any]:
        return {
            "id": lot.id,
            "plant_id": lot.equipment,
            "plant": plants[lot.equipment].name_short if lot.equipment in plants and plants[lot.equipment].name_short is not None else str(lot.equipment),
            "active": lot.active,
            "num_orders": len(lot.orders),
            "num_coils": num_coils[lot.id],
            "order_ids": lot.orders, #", ".join(lot.orders),
            "first_due_date": first_due_dates[lot.id],
            "all_due_dates": all_due_dates[lot.id],
            "total_weight": total_weights[lot.id]
        }
    data = sorted([row_for_lot(lot) for lot in lots], key=lambda lot: lot["id"])

    def column_def_for_field(field: str, info: FieldInfo):
        if isinstance(info, FieldInfo):
            filter_id = "agNumberColumnFilter" if info.annotation == float or info.annotation == int else \
                "agDateColumnFilter" if info.annotation == datetime or info.annotation == date else "agTextColumnFilter"
        else:
            filter_id = "agNumberColumnFilter" if isinstance(info, float) else \
                "agDateColumnFilter" if isinstance(info, datetime) or isinstance(info, date) else "agTextColumnFilter"
        col_def = {"field": field, "filter": filter_id}
        return col_def

    props = snap_obj.orders[0].material_properties
    if props is None:
        return False, data, data, False, None, None, None, None, True

    costs = state.get_cost_provider()
    relevant_fields = costs.relevant_fields(plants[lots[0].equipment]) if len(lots) > 0 else None
    if relevant_fields is not None:
        l = len("material_properties.")
        relevant_fields = [f[l:] if f.startswith("material_properties.") else f for f in relevant_fields]
    if isinstance(props, dict):
        fields_0 = props  # TODO sort according to relevant fields info
    else:
        fields_0 = dict(sorted(props.model_fields.items(), key=lambda item: relevant_fields.index(item[0]) if item[0] in relevant_fields else len(relevant_fields))) \
                      if relevant_fields is not None else props.model_fields

    fields = [{"field": "order", "pinned": True}, {"field": "lot", "pinned": True},
                {"field": "equipment", "headerTooltip": "Current equipment location of the order"},
                {"field": "costs", "headerTooltip": "Transition costs from previous order."},
                {"field": "weight", "headerTooltip": "Order weight in tons." },
                {"field": "due_date", "headerTooltip": "Order due date." },
                {"field": "priority", "headerTooltip": "Order priority."}] + \
             [column_def_for_field(key, info) for key, info in fields_0.items()]

    last_plant: int|None = None
    last_order: Order|None = None
    plant_obj: Equipment|None = None
    predecessor_orders: dict[int, str]|None = best_result.previous_orders

    def order_to_json(o: Order, lot: str|None):
        nonlocal last_plant
        nonlocal last_order
        nonlocal plant_obj
        as_dict = o.material_properties.model_dump(exclude_none=True, exclude_unset=True) if isinstance(o.material_properties, BaseModel) \
            else o.material_properties
        as_dict["order"] = o.id
        as_dict["lot"] = lot or ""
        as_dict["weight"] = o.actual_weight
        as_dict["due_date"] = o.due_date
        as_dict["priority"] = o.priority
        if o.current_equipment is not None:
            as_dict["equipment"] = ", ".join([plants[p].name_short or str(plants[p]) for p in o.current_equipment])
        if lot is None:
            return as_dict
        lot_obj = next(l for l in lots if l.id == lot)
        plant: int = lot_obj.equipment
        if plant == last_plant:
            tr_costs = costs.transition_costs(plant_obj, last_order, o)
            as_dict["costs"] = tr_costs
        else:
            plant_obj = plants[plant]
            if predecessor_orders is not None and plant in predecessor_orders:
                start_order_id = predecessor_orders[plant]
                start_order = snap_obj.get_order(start_order_id) if start_order_id is not None else None
                if start_order is not None:
                    tr_costs = costs.transition_costs(plant_obj, start_order, o)
                    as_dict["costs"] = tr_costs
        last_plant = plant
        last_order = o
        return as_dict

    order_rows = [order_to_json(o, lot) for lot, orders in orders_by_lot.items() for o in orders] + \
        [order_to_json(o, None) for o in unassigned_orders.values()]

    fields = [f for f in fields if any(order.get(f["field"]) is not None for order in order_rows)]
    structure = None
    structure_targets = None
    show_structure: bool = best_result.target_structure is not None and len(best_result.target_structure) > 0
    if show_structure:
        structure0 = ModelUtils.aggregated_structure(site, best_result)  # dict[str, dict[str, float]]
        # required format: { mat category id: { name: str, classes: { mat class id: {name: cl name, weight: aggregated weight} } } }
        all_cats: list[MaterialCategory] = site.material_categories
        structure = {cat.id: {"name": cat.name or cat.id, "classes": {cl.id: {"name": cl.name or cl.id, "weight": structure0[cat.id][cl.id]} for cl in cat.classes if cl.id in structure0[cat.id] }}
                                                        for cat in all_cats if cat.id in structure0}
        structure_targets = best_result.target_structure  # dict[str, float]
    return False, data, data, False, fields, order_rows, structure, structure_targets, not show_structure


# Lots export
@callback(
    Output("planning-lots-table", "exportDataAsCsv"),
    Output("planning-lots-table", "csvExportParams"),
    Input("download-csv", "n_clicks"),
    State("selected-snapshot", "data"),
    State("process-selector-lotplanning", "value"),
    State("planning-selected-solution", "data"),
    prevent_initial_call=True,
)
def export_data_as_csv(n_clicks, snapshot: str|None, process: str|None, solution: str|None):
    snapshot = DatetimeUtils.parse_date(snapshot)
    if not dash_authenticated(config) or process is None or snapshot is None or solution is None:
        return True, None
    filename = "lots_" + process + "_" + \
               DatetimeUtils.format(snapshot).replace("+0000","").replace(":", "").replace("-", "").replace("T", "") + \
               "_" + solution.replace("\\", "_").replace("/", "_").replace(":", "_") + ".csv"
    options = {"fileName": filename, "columnSeparator": ";" }
    return True, options


# Orders with lot information export
@callback(
    Output("planning-lots-order-table", "exportDataAsCsv"),
    Output("planning-lots-order-table", "csvExportParams"),
    Input("download-orders-csv", "n_clicks"),
    State("selected-snapshot", "data"),
    State("process-selector-lotplanning", "value"),
    State("planning-selected-solution", "data"),
    prevent_initial_call=True,
)
def export_order_data_as_csv(n_clicks, snapshot: str|None, process: str|None, solution: str|None):
    snapshot = DatetimeUtils.parse_date(snapshot)
    if not dash_authenticated(config) or process is None or snapshot is None or solution is None:
        return False, None
    filename = "orders_lots_" + process + "_" + \
               DatetimeUtils.format(snapshot).replace("+0000","").replace(":", "").replace("-", "").replace("T", "") + \
               "_" + solution.replace("\\", "_").replace("/", "_").replace(":", "_") + ".csv"
    options = {"fileName": filename, "columnSeparator": ";"}
    # TODO columns selector
    return True, options


clientside_callback(
    ClientsideFunction(
        namespace="createlots",
        function_name="showLotsSwimlane"
    ),
    Output("planning-lots-swimlane", "title"),
    Input("planning-solution-data", "data"),
    State("planning-lots-swimlane", "id"),
    State("process-selector-lotplanning", "value"),
    State("planning-swimlane-mode", "value")
)

clientside_callback(
    ClientsideFunction(
        namespace="createlots",
        function_name="setLotsSwimlaneMode"
    ),
    Output("planning-lotsview-header", "title"),
    Input("planning-swimlane-mode", "value")
)

clientside_callback(
    ClientsideFunction(
        namespace="lots2",
        function_name="setBacklogStructureOverview"
    ),
    Output("lotplanning-structure-view", "title"),
    Input("lotplanning-material-structure", "data"),
    Input("lotplanning-material-targets", "data"),
    State("lotplanning-structure-view", "id"),
)

# FIXME closing the popup and reopening the same lot does not work
# open popup on selection, but only if a lot is really selected, and if it is not part of the snapshot solution
@callback(
    Output("planning-selected-lot", "data"),
    Output("lotplanning-transfer-selectedlot", "children"),
    Output("lotplanning-transfer-lotname", "value"),
    Output("lotplanning-transfer-oders", "options"),
    Output("lotplanning-transfer-oders", "value"),
    Input("planning-lots-table", "selectedRows"),
    State("planning-selected-solution", "data"),
    State("lotplanning-transferred-lot", "data"),
    prevent_initial_call=True,
)
def lot_row_selected(rows, solution_id: str, last_transferred_solution: str|None):
    global lottransfer_results
    # clear last transfer result so the alert does not show up immediately
    if last_transferred_solution is not None and last_transferred_solution in lottransfer_results:
        lottransfer_results.pop(last_transferred_solution)
    if rows is None or len(rows) == 0 or solution_id == "_SNAPSHOT_":
        return dash.no_update, "", "", [], []
    sinks = state.get_lot_sinks()
    if len(sinks) == 0:
        return dash.no_update, "", "", [], []
    lot = rows[0].get("id")
    orders = rows[0].get("order_ids")
    if isinstance(orders, str):
        orders = [o for o in (o.strip() for o in orders.split(",")) if o != ""]
    options = []
    if isinstance(orders, Iterable):
        options = [{"value": o, "label": o} for o in orders]
    return lot if lot is not None else dash.no_update, lot if lot is not None else "", lot, options, orders


clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="showModal"
    ),
    Output("lotplanning-transfer-dialog", "title"),
    Input("planning-selected-lot", "data"),
    State("lotplanning-transfer-dialog", "id"),
)

clientside_callback(
    ClientsideFunction(
        namespace="dialog",
        function_name="closeModal"
    ),
    Output("lotplanning-transfer-cancel", "title"),
    Input("lotplanning-transfer-cancel", "n_clicks"),
    State("lotplanning-transfer-dialog", "id"),
)

"""
@callback(
    Output("lotplanning-transfer-start", "disabled"),
    Output("lotplanning-transfer-start", "title"),
    Input("planning-selected-lot", "data"),
    Input("lotplanning-transfer-lotname", "value"),
    Input("lotplanning-transfer-oders", "value"),
    Input("lotplanning-transfer-target", "value"),
    Input("planning-interval", "n_intervals"),

)
"""
def disable_transfer_button(lot: str, new_lotname: str, orders: list[str]|str, transfer_target: str|None) -> tuple[bool, str]:
    if not lot:
        return True, "No lot selected"
    if not new_lotname or len(new_lotname.strip()) < 3:
        return True, "Lotname too short, need three characters at least"
    if orders is None or len(orders) == 0:
        return True, "No order(s) selected"
    if not transfer_target:
        return True, "No transfer target selected"
    #running, result = check_running_transfer()
    #if running:
    #    return True, "Transfer active"
    return False, "Transfer lot to backend system " + str(transfer_target)


@callback(
    Output("planning-interval", "interval"),
    Output("lotplanning-transfer-start", "disabled"),
    Output("lotplanning-transfer-start", "title"),
    Output("lotplanning-transferred-lot", "data"),
    Output("lotplanning-transfer-message", "data"),
    Output("lotplanning-transfer-type", "data"),
    Input("lotplanning-transfer-start", "n_clicks"),
    Input("planning-interval", "n_intervals"),
    Input("planning-selected-lot", "data"),
    Input("lotplanning-transfer-lotname", "value"),
    Input("lotplanning-transfer-oders", "value"),
    Input("lotplanning-transfer-target", "value"),
    State("selected-snapshot", "data"),
    State("process-selector-lotplanning", "value"),
    State("planning-selected-solution", "data"),
    State("lotplanning-transferred-lot", "data"),
    config_prevent_initial_callbacks=True
)
def check_start_transfer(_, __, lot: str, new_lotname: str, orders: list[str] | str, transfer_target: str | None, snapshot: str | datetime | None, process: str | None,
                         solution: str | None, last_transferred_lot: str|None):
    snapshot = DatetimeUtils.parse_date(snapshot)
    if not dash_authenticated(config) or process is None or snapshot is None or solution is None or solution == "_SNAPSHOT_" or transfer_target is None:
        return 3_600_000, True, "", dash.no_update, None, None
    running, new_result = check_running_transfer(last_transferred_lot)   # TODO display result somehow... and if the transfer succeeded, store information to avoid transferring it again
    transfer_alert_msg = None
    transfer_alert_type = None
    if new_result is not None:
        is_error = isinstance(new_result, Exception)
        transfer_alert_msg = str(new_result)
        transfer_alert_type = "success" if not is_error else "error"
    if running:
        return 1_000, True, "Transfer active", dash.no_update, transfer_alert_msg, transfer_alert_type
    btn_disabled, btn_title = disable_transfer_button(lot, new_lotname, orders, transfer_target)
    if btn_disabled:
        return 3_600_000, True, btn_title, dash.no_update, transfer_alert_msg, transfer_alert_type
    changed = GuiUtils.changed_ids()
    is_start_command = "lotplanning-transfer-start" in changed
    if is_start_command:
        orders = orders if not isinstance(orders, str) else [orders]
        success: str|None = start_transfer0(lot, new_lotname, orders, snapshot, process, solution, transfer_target) if orders is not None and len(orders) > 0 else None
        if success is not None:
            return 1_000, True, "Transfer active", success, transfer_alert_msg, transfer_alert_type
        else:
            return 3_600_000, False, "Start transfer", None, transfer_alert_msg, transfer_alert_type
    return 3_600_000, btn_disabled, btn_title, dash.no_update, transfer_alert_msg, transfer_alert_type


def start_transfer0(lot_id: str, new_lotname: str, orders: list[str], snapshot: datetime, process: str, solution: str, transfer_target: str) -> str|None:
    best_result: ProductionPlanning
    result: LotsOptimizationState = state.get_results_persistence().load(snapshot, process, solution)
    if result is None or result.best_solution is None:  # TODO error msg
        return None
    best_result: ProductionPlanning = result.best_solution
    lot_obj: Lot | None = next((lot for plant_lots in best_result.get_lots().values() for lot in plant_lots if lot.id == lot_id), None)
    sink = state.get_lot_sinks().get(transfer_target)
    if lot_obj is None or sink is None:  # TODO error msg?
        print("Lot or sink not found. Lot: ", lot_id, "is None:", lot_obj is None, ", sink:", transfer_target, "is None:", sink is None)
        return None
    snapshot_obj = state.get_snapshot(snapshot)
    if snapshot_obj is None:
        print("Snapshot object not found for lot transfer", snapshot)
        return None
    if len(orders) != len(lot_obj.orders):
        lot_obj = lot_obj.copy(update={"orders": orders})
    return transfer_internal(lot_obj, snapshot_obj, new_lotname, sink)


def transfer_internal(lot: Lot, snapshot: Snapshot, name: str, sink: LotSink) -> str|None:
    global lottransfer_thread
    global lottransfer_result
    if lottransfer_thread is not None:
        return None
    lottransfer_result = None
    identifier = str(uuid.uuid4())
    lottransfer_thread = LotTransferThread(lot, snapshot, name, sink, identifier)
    lottransfer_thread.start()
    return identifier


def check_running_transfer(last_transferred_lot: str|None) -> tuple[bool, any]:
    global lottransfer_thread
    global lottransfer_results
    if lottransfer_thread is not None:
        if not lottransfer_thread.is_alive():
            err = lottransfer_thread.error()
            result = err if err is not None else lottransfer_thread.result()
            while len(lottransfer_results) > 10:
                key = iter(lottransfer_results)
                lottransfer_results.pop(key)
            lottransfer_results[lottransfer_thread.identifier()] = result
            lottransfer_thread = None
    result = lottransfer_results.get(last_transferred_lot) if last_transferred_lot is not None else None
    return lottransfer_thread is not None, result


# clientside arguments: msg, type, siblingId, dummyReturnValue
clientside_callback(
    ClientsideFunction(
        namespace="alert",
        function_name="showAlert"
    ),
    Output("lotplanning-transfer-grid", "title"),
    Input("lotplanning-transfer-message", "data"),
    Input("lotplanning-transfer-type", "data"),
    State("lotplanning-transfer-grid", "id"),
)


class LotTransferThread(threading.Thread):

    def __init__(self, lot: Lot, snapshot: Snapshot, name: str, sink: LotSink, identifier: str):
        super().__init__(name=lottransfer_thread_name)
        self._lot = lot
        self._snapshot = snapshot
        self._name = name
        self._sink = sink
        self._identifier = identifier
        self._result = None
        self._error = None

    def identifier(self) -> str:
        return self._identifier

    def lot(self) -> Lot:
        return self._lot

    def result(self):
        return self._result

    def error(self):
        return self._error

    def run(self):
        try:
            result = self._sink.transfer_new(self._lot, self._snapshot, external_id=self._name)
            result = "Successfully transferred: " + str(result) if result is not None else "Lot " + (self._name if self._name is not None else self._lot.id) + " successfully transferred"
            self._result = result
        except Exception as e:
            traceback.print_exc()
            self._error = e


