import traceback
from datetime import datetime, date
from typing import Any

import dash
from dash import html, dcc, callback, Output, Input, State
import dash_ag_grid as dash_ag
from pydantic import BaseModel
from pydantic.fields import FieldInfo

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.base.PlantPerformanceModel import PlantPerformanceModel, PlantPerformanceResults
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Process, Equipment, Order

perf_models: list[PlantPerformanceModel] = state.get_plant_performance_models()

if len(perf_models) > 0:
    dash.register_page(__name__, path="/perfmodels")

    translations_key = "perf"

    def layout(*args, **kwargs):
        def option_for_model(m: PlantPerformanceModel) -> dict[str, str]:
            try:
                procs, plants = m.applicable_processes_and_plants()
                status = m.status()
                opt = {"value": m.id(), "label": m.label(), "title": m.description() or m.label(), "status": status,
                       "processes": procs}
            except:
                m_id = str(m)
                title = "The id of the model is unknown, a connection could not be established yet"
                opt = {"value": m_id, "label": m_id, "title": title, "status": 1}
            stat = opt.get("status")
            status_label = "active (0)" if stat == 0 else "disconnected (1)" if stat == 1 else "Code: " + str(stat)
            opt["status_label"] = status_label
            return opt

        model_options: list[dict[str, str]] = [option_for_model(p) for p in perf_models]
        first_available_model_opt = next((option for option in model_options if option.get("status") == 0), None) or next(
            option for option in model_options)
        first_available_model = first_available_model_opt["value"]
        layout_ = html.Div([
            html.H1("Plant performance models", id="perf-title"),
            # ======= Models table ==============
            html.H2("Models overview", id="perf-overview"),
            html.Div(
                dash_ag.AgGrid(
                    id="perf-overview-table",
                    columnDefs=[{"field": "value", "headerName": "Id", "pinned": True},
                                {"field": "label"},
                                {"field": "processes"},
                                {"field": "status_label", "filter": "agNumberColumnFilter", "headerName": "Status"},
                                {"field": "description"}
                                ],
                    defaultColDef={"filter": "agTextColumnFilter", "filterParams": {"buttons": ["reset"]}},
                    dashGridOptions={"tooltipShowDelay": 250, "rowSelection": "single", "domLayout": "autoHeight"},
                    rowData=model_options,
                    getRowId="params.data.value",
                    className="ag-theme-alpine",  # ag-theme-alpine-dark
                    # style={"height": None, "width": "100%", "margin-bottom": "5em"},
                    style={"height": None},  # required with autoHeight
                    columnSizeOptions={"defaultMinWidth": 125},
                    #columnSize="responsiveSizeToFit",
                )
            ),
            # ======= Model selector and process indicator =========
            html.H2("Model details", id="perf-details"),
            html.Div([
                html.Div("Model: ", title="Select a plant performance model"),
                dcc.Dropdown(id="perf-model-selector", className="perf-model-selector", persistence=True, options=model_options, value=first_available_model),
                html.Div(html.Div([
                    html.Div("Process: "),
                    html.Div(id="perf-selected-process"),
                    html.Div("Equipment: "),
                    html.Div(id="perf-selected-equipment"),
                ], className="perf-process-container"), id="perf-process-container", hidden=True)
            ], className="perf-model-selection"),
            html.Br(),
            html.H3("Orders", id="perf-orders-header"),
            html.Div([
                dash_ag.AgGrid(
                    id="perf-orders-table",
                    columnDefs=[{"field": "id", "pinned": True}],
                    rowData=[],
                    getRowId="params.data.id",
                    className="ag-theme-alpine",  # ag-theme-alpine-dark
                    style={"width": "100%", "margin-bottom": "1em"},
                    columnSizeOptions={"defaultMinWidth": 125},
                    columnSize="responsiveSizeToFit",
                    # tooltipField is not used, but it must match an existing field for the tooltip to be shown
                    defaultColDef={"tooltipComponent": "CoilsTooltip", "tooltipField": "id"},
                    dashGridOptions={"rowSelection": "multiple","suppressRowClickSelection": True, "animateRows": False},
                    # "autoSize"  # "responsiveSizeToFit" => this leads to essentially vanishing column size
                ),
                html.Br(),
                # TODO input: submit selected orders to performance model!
                html.Button("Submit orders", id="perf-orders-submit-button", className="dynreact-button", disabled=True),
                html.Br(),
                html.Div("Results: "),
                html.Div(id="perf-results"),
                html.Br(),
            ], id="perf-orders-container", hidden=True),

            dcc.Store(id="perf-process"),   # comma-separated list of strings, or None
            dcc.Store(id="perf-plants")     # comma-separated list of ints, or None
        ], id="perf-title")
        return layout_

    def find_model(model_id: str|None) -> PlantPerformanceModel|None:
        models = state.get_plant_performance_models()

        def get_id(model: PlantPerformanceModel) -> str:
            try:
                return model.id()
            except:
                return str(model)
        selected_model = next((m for m in models if get_id(m) == model_id), None)
        return selected_model

    def find_processes_and_plants(procs: str|None, plants: str|None) -> tuple[list[Process], list[Equipment]|None]:
        site = state.get_site()
        process_list = [p.strip() for p in procs.split(",")] if procs else None
        plants_list = [p.strip() for p in procs.split(",")] if plants else None
        processes: list[Process] | None = [p for p in (site.get_process(p) for p in process_list) if p is not None] \
            if process_list is not None else None
        if processes is not None and len(processes) == 0:
            processes = None
        plants: list[Equipment] | None = [p for p in (site.get_equipment(p) for p in plants_list) if p is not None] \
            if plants_list is not None else None
        if plants is not None and len(plants) == 0:
            plants = None
        if processes is None and plants is None:
            return [], []
        if processes is None:
            processes = sorted(list({site.get_process(p.process, do_raise=True) for p in plants}),
                               key=lambda p: p.process_ids[0])
        return processes, plants


    @callback(
              Output("perf-process", "data"),
              Output("perf-plants", "data"),
              Output("perf-selected-process", "children"),
              Output("perf-selected-equipment", "children"),
              Output("perf-process-container", "hidden"),
              Output("perf-orders-container", "hidden"),
              Input("perf-model-selector", "value")
    )
    def procs_and_plants(selected_model_id: str) -> tuple[str|None, str|None, str|None, str|None, bool, bool]:
        if not dash_authenticated(config) or selected_model_id is None:
            return None, None, None, None, True, True
        selected_model = find_model(selected_model_id)
        try:
            procs, plants = selected_model.applicable_processes_and_plants()
            if procs is not None:
                procs = ",".join(procs)
            if plants is not None and len(plants) > 0:
                plants = ",".join(str(pl) for pl in plants)
            else:
                plants = "all"
            return procs, plants, procs, plants, False, False
        except:
            return None, None, None, None, True, True

    @callback(
              Output("perf-orders-table", "columnDefs"),
              Output("perf-orders-table", "rowData"),
              Input("selected-snapshot", "data"),
              Input("perf-process", "data"),
              Input("perf-plants", "data"),
    )
    def procs_changed(snapshot: str, procs: str|None, plants: str|None):
        if not dash_authenticated(config) or (not procs and not plants):
            return None, None
        snapshot = DatetimeUtils.parse_date(snapshot)   # TODO
        if snapshot is None:
            return None, None
        snapshot_serialized: str = DatetimeUtils.format(snapshot)
        snapshot_obj = state.get_snapshot(snapshot)
        site = state.get_site()
        processes, plants = find_processes_and_plants(procs, plants)

        # TODO to util?... copied from lot_creation2
        def column_def_for_field(field: str, info: FieldInfo):
             filter_id = "agNumberColumnFilter" if info.annotation == float or info.annotation == int else \
                   "agDateColumnFilter" if info.annotation == datetime or info.annotation == date else "agTextColumnFilter"
             col_def = {"field": field, "filter": filter_id, "filterParams": {"buttons": ["reset"]}}
             return col_def

        def column_def_for_dict_entry(field: str, value: Any):
            filter_id = "agNumberColumnFilter" if isinstance(value, float) else \
                "agDateColumnFilter" if isinstance(value, datetime) or isinstance(value, date) else "agTextColumnFilter"
            col_def = {"field": field, "filter": filter_id, "filterParams": {"buttons": ["reset"]}}
            return col_def

        fields = [column_def_for_field(key, info) for key, info in snapshot_obj.orders[0].model_fields.items() if (key not in ["material_properties", "lot", "lot_position" ])] + \
                    ([column_def_for_field(key, info) for key, info in snapshot_obj.orders[0].material_properties.model_fields.items()] if isinstance(snapshot_obj.orders[0].material_properties, BaseModel) else
                     [column_def_for_dict_entry(key, info) for key, info in snapshot_obj.orders[0].material_properties.items()] if isinstance(snapshot_obj.orders[0].material_properties, dict) else [])

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
            elif isinstance(o.material_properties, dict):
                as_dict.update(o.material_properties)
            return as_dict

        process_ids: list[list[int]] = [p.process_ids for p in site.processes]
        num_processes = len(processes)
        current_process_index = process_ids.index(processes[0].process_ids)
        process_plants: list[list[int]] = [sorted([plant.id for plant in site.get_process_equipment(proc.name_short)]) for proc in site.processes]

        def process_index_for_proc_id(proc_id: int) -> int:
            return next((idx for idx, proc in enumerate(process_ids) if proc_id in proc), num_processes)

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

        orders_sorted = sorted(snapshot_obj.orders, key=process_index_for_order)
        return fields, [order_to_json(order) for order in orders_sorted]


    @callback(
              Output("perf-orders-submit-button", "disabled"),
              Input("perf-orders-table", "selectedRows")
    )
    def orders_selected(selected_orders: list[dict[str, any]]|None):
        if not dash_authenticated(config) or not selected_orders or len(selected_orders) == 0:
            return True
        return False

    # TODO cache results per session, add clear button
    @callback(
              Output("perf-results", "children"),
              Input("perf-orders-submit-button", "n_clicks"),
              State("perf-process", "data"),
              State("perf-plants", "data"),
              State("selected-snapshot", "data"),
              State("perf-model-selector", "value"),
              State("perf-orders-table", "selectedRows")
    )
    def submit_orders(_, procs: str|None, plants: str|None, snapshot: str|None, selected_model_id: str, selected_orders: list[dict[str, any]]|None) -> str|None:
        snapshot = DatetimeUtils.parse_date(snapshot)
        if not dash_authenticated(config) or snapshot is None or not selected_model_id or not selected_orders or not (procs or plants):
            return None
        snapshot_serialized: str = DatetimeUtils.format(snapshot)
        snapshot_obj = state.get_snapshot(snapshot)
        selected_model = find_model(selected_model_id)
        processes, plants = find_processes_and_plants(procs, plants)
        if snapshot_obj is None or selected_model is None or not (processes or plants):
            return None
        orders = [o for o in snapshot_obj.orders if any(sel for sel in selected_orders if sel.get("id") == o.id)]
        if len(orders) == 0:
            return None
        if plants is None or len(plants) == 0:
            site = state.get_site()
            plants: list[int] = sorted(list({plant.id for proc in processes for plant in site.get_process_equipment(proc.name_short)}))
        res = ""
        for plant in plants:
            plant_orders = [o for o in orders if plant in o.allowed_equipment]
            result: PlantPerformanceResults = selected_model.bulk_performance(plant, plant_orders)
            res += result.model_dump_json(exclude_none=True, exclude_unset=True)
        return res


