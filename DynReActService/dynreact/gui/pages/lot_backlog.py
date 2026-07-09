from datetime import datetime, timedelta
from typing import Literal, Any, Sequence

import dash
from dash import html, callback, Input, Output, dcc, State
import dash_ag_grid as dash_ag

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Equipment, Order, Process, Lot, LotTimes

dash.register_page(__name__, path="/lots/backlog")
translations_key = "lots-backlog"


def layout(*args, **kwargs):
    processes = state.get_site().processes
    process: str | None = kwargs.get("process")
    equipments = state.get_site().equipment if process is None or process == "" else state.get_site().get_process_equipment(process)
    equipment = _plant_for_id(equipments, kwargs.get("equipment")) or equipments[0]
    process = process or equipment.process
    return html.Div([
        html.H1("Order backlog view", id=f"{translations_key}-title"),
        html.Div([
            html.Div([
                html.H2("Equipment", id=f"{translations_key}-equipment-header"),
                html.Div([
                    html.Span("Snapshot"), html.Span(id=f"{translations_key}-snapshot"),
                    html.Span("Select process:", id=f"{translations_key}-proc-select-label"),
                    dcc.Dropdown(options=[{"value": p.name_short, "label": p.name_short} for p in processes],
                                 value=process, id=f"{translations_key}-proc-select", style={"min-width": "12em"}),
                    html.Span("Select equipment:", id=f"{translations_key}-eq-select-label"),
                    dcc.Dropdown(options=[{"value": e.id, "label": e.name_short} for e in
                                          state.get_site().get_process_equipment(process)], value=equipment.id,
                                 id=f"{translations_key}-eq-select", style={"min-width": "12em"}),
                    html.Span("Select start lot:", id=f"{translations_key}-startlot-select-label"),
                    dcc.Dropdown(id=f"{translations_key}-startlot-select", style={"min-width": "12em"}),
                    html.Span("Select planning start:", id=f"{translations_key}-planning-start-label"),
                    html.Div([
                        dcc.Input(type="date", id=f"{translations_key}-planning-start-date"),
                        dcc.Input(type="time", id=f"{translations_key}-planning-start-time"),
                    ], className="lot2-planning-start", style={"padding": "0.5em 0"})
                ], className="grid-2 gap-1"),
            ], className="settings-panel"),
            html.Div([
                html.H2("Order filter", id=f"{translations_key}-filter-header"),
                html.Div([
                    html.Span("Include orders not applicable to equipment:",
                              id=f"{translations_key}-not-applicable-label"),
                    dcc.Checklist(options=[{"value": ""}], value=[], id=f"{translations_key}-not-applicable"),
                    html.Span("Include orders at later stages:", id=f"{translations_key}-later-stages-label"),
                    dcc.Checklist(options=[{"value": ""}], value=[], id=f"{translations_key}-later-stages"),
                    html.Span("Include orders at unknown equipment:", id=f"{translations_key}-unknown-eq-label"),
                    dcc.Checklist(options=[{"value": ""}], value=[], id=f"{translations_key}-unknown-eq")
                ], className="grid-2 gap-1"),
            ], className="settings-panel"),
            html.Div([
                html.H2("Backlog overview", id=f"{translations_key}-overview-header"),
                html.Div([
                    html.Span("Tons available:", id=f"{translations_key}-tons-available-label"),
                    html.Span(id=f"{translations_key}-tons-available"),
                    html.Span("Tons total:", title="Sum of order weights shown in table",
                              id=f"{translations_key}-tons-total-label"), html.Span(id=f"{translations_key}-tons-total"),
                ], className="grid-2 gap-1"),
            ], className="settings-panel")
        ], style={"display": "flex", "column-gap": "4em", "flex-wrap": "wrap", "row-gap": "1em"}),
        html.H2("Order backlog", id=f"{translations_key}-backlog-header"),
        dash_ag.AgGrid(
            id=f"{translations_key}-orders-table",
            columnDefs=table_columns(None),
            rowData=[],
            getRowId="params.data.id",
            className="ag-theme-alpine",  # ag-theme-alpine-dark
            # style={"height": "70vh", "width": "80vw", "margin-bottom": "5em"},
            columnSizeOptions={"defaultMinWidth": 125, "defaultMaxWidth": 150},
            # important to set, since the sizeToFit is applied the first time when the grid is not visible yet
            columnSize="sizeToFit",  # need to reset this whenever the column definitions change
            # columnSize="responsiveSizeToFit",  # super annoying; but sizeToFit is not enough, since this is called already when the grid is still empty
            # tooltipField is not used, but it must match an existing field for the tooltip to be shown
            #defaultColDef={"tooltipComponent": "CoilsTooltip", "tooltipField": "id"},
            #dashGridOptions={"rowSelection": "multiple", "suppressRowClickSelection": True, "animateRows": False, }
        ),
        dcc.Store(id="lots-backlog-planning-start", storage_type="memory")
    ], id="lots-backlog")


def _plant_for_id(plants: list[Equipment], plant_id0: str|None) -> Equipment|None:
    if plant_id0 is None or len(plant_id0) == 0:
        return None
    plant = next((p for p in plants if str(p.id) == plant_id0), None)
    if plant is not None:
        return plant
    plant_id = plant_id0.upper()
    plant = next((p for p in plants if (p.name_short is not None and p.name_short.upper() == plant_id) or (p.name is not None and p.name.upper() == plant_id)), None)
    return plant

@callback(Output("lots-backlog-snapshot", "children"),
          Input("selected-snapshot", "data"))
def table_columns(snapshot: str|None):
    return snapshot

@callback(Output("lots-backlog-orders-table", "columnDefs"),
          Input("lang", "data"))
def table_columns(lang: str|None):
    is_de: bool = lang and lang.startswith("de")
    #  "agDateColumnFilter", "agNumberColumnFilter"
    table_cols = [
        {"field": "id", "pinned": True, "filter": "agTextColumnFilter", "headerTooltip": "Auftragsnummer" if is_de else "Order id"},
        {"field": "available", "headerName": "Verfügbar" if is_de else "Available",
                "headerTooltip": "Ist der Auftrag verplanbar an der ausgewählten Prozessstufe?" if is_de else "Is the order available for scheduling at the selected process stage?"},
        {"field": "equipment", "headerName": "Aktuelle Anlage" if is_de else "Current equipment", "filter": "agTextColumnFilter",
                "headerTooltip": "Anlage an der sich der Auftrag befindet" if is_de else "Equipment where order is located"},
        {"field": "process_ids", "headerName": "Aktuelle Prozesse" if is_de else "Current processes", "filter": "agTextColumnFilter",
                "headerTooltip": "Aktuelle Prozess-IDs für den Auftrag" if is_de else "Current process ids for the order"},
        #{"field": "process_match", "headerName": "Anlagenstufe?" if is_de else "Process?",
        #        "headerTooltip": "Befindet sich der Auftrag bereits an der ausgewählten Prozessstufe?" if is_de else "Is the order located at the selected process stage?"},
        {"field": "reason", "headerName": "Grund" if is_de else "Reason", "filter": "agTextColumnFilter",
                "headerTooltip": "Grund für Nicht-Verfügbarkeit" if is_de else "Reason for non-availability"},
        {"field": "current_lot", "headerName": "Los Zielstufe" if is_de else "Lot target process", "filter": "agTextColumnFilter",
                "headerTooltip": "Vorhandenes Los an der Zielstufe" if is_de else "Existing lot for the target process"},
        {"field": "current_lot_active", "headerName": "Los aktiv" if is_de else "Lot active",
                "headerTooltip": "Ist das vorhandenes Los an der Zielstufe aktiv?" if is_de else "Is existing lot for the target process active?"},
        {"field": "previous_lot", "headerName": "Los Vorgängerstufe" if is_de else "Lot previous process", "filter": "agTextColumnFilter",
                "headerTooltip": "Vorhandenes Los an der Vorgängerstufe" if is_de else "Existing lot for the previous process stage"},
        {"field": "previous_lot_end", "headerName": "Fertigstellung Vorgängerlos" if is_de else "Lot end time at previous process", "filter": "agDateColumnFilter",
                "headerTooltip": "Geplante Ferstigstellung des Vorgängerloses" if is_de else "Targeted end time for lot at previous process stage"},
        {"field": "order_end",  "headerName": "Fertigstellung Auftrag" if is_de else "Order end time at previous process", "filter": "agDateColumnFilter",
                "headerTooltip": "Geplante Ferstigstellung des Auftrags an der Vorgängeranlage" if is_de else "Targeted end time for order at previous process stage"},
        {"field": "transport_time", "headerName": "Transportzeit / h" if is_de else "Transport time / h", "filter": "agNumberColumnFilter",
                "headerTooltip": "Transportzeit von der Vorängeranlage in Stunden" if is_de else "Transport time from previous equipment in hours"},
    ]
    return table_cols


@callback(Output("lots-backlog-eq-select", "options"),
          Output("lots-backlog-eq-select", "value"),
          Input("lots-backlog-proc-select", "value"),
          State("lots-backlog-eq-select", "value"))
def process_changed(proc: str|None, selected_plant: int|None):
    if proc is None or not dash_authenticated(config):
        return [], None
    equipment = state.get_site().get_process_equipment(proc)
    options = [{"value": eq.id, "label": eq.name_short} for eq in equipment]
    value = dash.no_update if selected_plant is not None and any(e.id == selected_plant for e in equipment) else equipment[0].id
    return options, value


@callback(Output("lots-backlog-startlot-select", "options"),
          Output("lots-backlog-startlot-select", "value"),
          Input("lots-backlog-eq-select", "value"),
          State("lots-backlog-startlot-select", "value"),
          State("selected-snapshot", "data"))
def equipment_changed(equipment: int|None, current_selection: str|None, snapshot: str|None):
    snapshot = DatetimeUtils.parse_date(snapshot)
    if not dash_authenticated(config) or equipment is None or not snapshot:
        return [], None
    snap_obj = state.get_snapshot(time=snapshot)
    lots = [lot for lot in snap_obj.lots.get(equipment, []) if lot.active and lot.end_time]
    lot_ids = [lot.id for lot in lots]
    options = [{"value": lot, "label": lot} for lot in lot_ids]
    if current_selection and current_selection in lot_ids:
        value = dash.no_update
    elif len(lot_ids) == 0:
        value = None
    else:
        last_lot = sorted(lots, key=lambda lot: lot.end_time)[-1]
        value = last_lot.id
    return options, value

@callback(Output("lots-backlog-planning-start-date", "value"),
            Output("lots-backlog-planning-start-time", "value"),
          Input("lots-backlog-eq-select", "value"),
          Input("lots-backlog-startlot-select", "value"),
          State("selected-snapshot", "data"))
def equipment_changed(equipment: int|None, selected_lot: str|None, snapshot: str|None):
    snapshot = DatetimeUtils.parse_date(snapshot)
    if not dash_authenticated(config) or equipment is None or not snapshot or not selected_lot:
        return DatetimeUtils.format(state.as_timezone(snapshot or DatetimeUtils.now()), use_zone=False).split("T")
    snap_obj = state.get_snapshot(time=snapshot)
    lots = [lot for lot in snap_obj.lots.get(equipment, []) if lot.active and lot.end_time]
    selected = next((lot for lot in lots if lot.id == selected_lot), None)
    return DatetimeUtils.format(state.as_timezone(selected.end_time if selected is not None else snap_obj.timestamp), use_zone=False).split("T")

@callback(Output("lots-backlog-planning-start", "data"),
        Input("lots-backlog-planning-start-date", "value"),
        Input("lots-backlog-planning-start-time", "value"),
        State("selected-snapshot", "data"))
def start_time_changed(dat: str | None, time: str | None, snapshot: str|None):
    if dat is None or time is None:
        snapshot = DatetimeUtils.parse_date(snapshot)
        return DatetimeUtils.format(state.as_timezone(snapshot or DatetimeUtils.now()))
    dt_time_str = dat + "T" + time
    return DatetimeUtils.format(state.as_timezone(DatetimeUtils.parse_date(dt_time_str)))

@callback(Output("lots-backlog-orders-table", "rowData"),
          Output("lots-backlog-tons-available", "children"),
          Output("lots-backlog-tons-total", "children"),
          Input("lots-backlog-eq-select", "value"),
          Input("lots-backlog-planning-start", "data"),
          Input("lots-backlog-not-applicable", "value"),
          Input("lots-backlog-later-stages", "value"),
          Input("lots-backlog-unknown-eq", "value"),
          Input("lang", "data"),
          State("selected-snapshot", "data"))
def update_table(equipment: int|None, start_date0: str|None,
                 not_appl: Sequence[Literal[""]], later_stages: Sequence[Literal[""]], unknown_eq: Sequence[Literal[""]], lang: str|None, snapshot: str|None):
    snapshot = DatetimeUtils.parse_date(snapshot)
    start_date = DatetimeUtils.parse_date(start_date0)
    if not dash_authenticated(config) or equipment is None or not snapshot or not start_date:
        return [], None, None
    site = state.get_site()
    is_de = lang and lang.startswith("de")
    snap_obj = state.get_snapshot(time=snapshot)
    plant = site.get_equipment(equipment, do_raise=True)
    process = plant.process
    proc = site.get_process(process, do_raise=True)
    prev_procs, next_procs = _get_previous_and_subsequent_processes(site.processes, proc)
    immediately_preceding_stages: list[str] = [p.name_short for p in prev_procs if process in p.next_steps]
    previous_process_ids: Sequence[int] = [id for p in prev_procs for id in p.process_ids]
    next_process_ids: Sequence[int] = [id for p in next_procs for id in p.process_ids]
    previous_process_names = [p.name_short for p in prev_procs]
    next_process_names = [p.name_short for p in next_procs]
    all_lots: dict[str, Lot] = {lot.id: lot for lots in snap_obj.lots.values() for lot in lots}
    snap_provider = state.get_snapshot_provider()
    zero = timedelta()

    def data_for_order(order: Order):
        process_match = any(p in proc.process_ids for p in order.current_processes)
        is_at_previous_stage = any(p in previous_process_ids for p in order.current_processes)
        is_at_follow_up_stage = any(p in next_process_ids and not p in previous_process_ids and not p in proc.process_ids for p in order.current_processes)
        if not process_match and not is_at_previous_stage and not is_at_follow_up_stage and order.current_equipment is not None:
            # This sometimes happens if the process id is not known, e.g. for rework
            equipments = [site.get_equipment(e, do_raise=True) for e in order.current_equipment]
            is_at_follow_up_stage = any(e.process in next_process_names for e in equipments)
            is_at_previous_stage = any(e.process in previous_process_names for e in equipments)
            process_match = any(e.process == process for e in equipments)
        current_lot = order.lots[process] if order.lots and process in order.lots else None
        current_complete = True  # false
        prev_lot = next((order.lots[p] for p in immediately_preceding_stages if p in order.lots), None) if order.lots is not None else None
        prev_end_time = all_lots[prev_lot].end_time if prev_lot and prev_lot in all_lots else None
        available_at = prev_end_time
        current_active = current_lot is not None and current_lot in all_lots and all_lots[current_lot].active
        not_reschedulable = current_lot and current_lot in all_lots and not snap_provider.is_lot_reschedulable(all_lots[current_lot])
        sort = 0 if process_match else 1 if prev_lot is not None else 2 if is_at_previous_stage else 3 if is_at_follow_up_stage else 10
        current_eq = None
        if order.current_equipment is not None:
            current_eq = [site.get_equipment(e, do_raise=True).name_short for e in order.current_equipment]
        od = {"id": order.id, "weight": order.actual_weight, "equipment": current_eq, "process_match": process_match, "following_stage": is_at_follow_up_stage,
                "previous_stage": is_at_previous_stage, "current_lot": current_lot, "current_lot_active": current_active, "current_lot_complete": current_complete,
                "previous_lot": prev_lot, "previous_lot_end": DatetimeUtils.format(prev_end_time, use_zone=False).replace("T", " ") if prev_end_time is not None else None,
                "process_ids": order.current_processes, "sort": sort}
        if prev_lot is not None and prev_lot in all_lots:
            prev_eq = site.get_equipment(all_lots[prev_lot].equipment, do_raise=True)
            prev_proc = prev_eq.process
            tt = zero
            if site.transport_times is not None:
                delta: timedelta|None = site.transport_times.transport_times(prev_eq.id, equipment)
                od["transport_time"] = 0
                if delta is not None:
                    hours = delta.total_seconds()/3600
                    if hours != int(hours):
                        hours = round(hours*10) / 10
                    tt = delta
                    od["transport_time"] = hours
            times = snap_provider.get_order_lot_times(snap_obj.timestamp, order.id)
            if times and order.id in times:
                o_times: LotTimes|None = times[order.id].get(prev_proc)
                if o_times is not None:
                    od["order_end"] = DatetimeUtils.format(state.as_timezone(o_times.end), use_zone=False).replace("T", " ")
                available_at = o_times.end + tt
        if is_at_follow_up_stage:
            od["available"] = False
            od["later_stage"] = True
            partly = is_at_previous_stage or process_match
            od["reason"] = "Auftrag befindet sich bereits " + ("teilweise" if partly else "vollständig") + " an Nachfolgestufe" if is_de else \
                "Order already located " + ("partly" if partly else "entirely") + " at a later process stage"
        elif equipment not in order.allowed_equipment:
            od["available"] = False
            od["reason"]    = f"Anlage {plant.name_short} nicht zugelassen" if is_de else f"Equipment {plant.name_short} not applicable"
        elif current_active:
            od["available"] = False
            od["reason"] = "Bereits verplant an Zielstufe" if is_de else "Already scheduled at target stage"
        elif not_reschedulable:
            od["available"] = False
            od["reason"] = f"Bereits verplant an Zielstufe; Los {current_lot} darf nicht verändet werden." if is_de else f"Already scheduled at target stage; cannot change lot {current_lot}"
        elif is_at_previous_stage and not process_match and prev_lot is None:
            od["available"] = False
            od["reason"] = "Noch kein Vorgängerlos vorhanden" if is_de else "Not scheduled yet at previous process stage"
        elif is_at_previous_stage and available_at is not None:
            available = available_at <= start_date
            od["available"] = available
            if not available:
                avail_time = DatetimeUtils.format(state.as_timezone(available_at), use_zone=False).replace("T", " ")
                od["reason"] = f"Zeitverzehr von Vorgängerlos passt nicht: frühestens verfügbar um {avail_time}" if is_de else \
                    f"Not available in time, earliest availability at {avail_time}"
        elif process_match:
            od["available"] = True
        elif len(order.current_processes) == 0 or order.current_equipment is None or len(order.current_equipment) == 0:
            od["available"] = False
            od["reason"] = "Aktuelle Anlage nicht bekannt" if is_de else "Current equipment unknown"
        else:
            od["available"] = False
            od["reason"] = "Unbekannt" if is_de else "Unknown"
            # FIXME
            print("  UNKNOWN!", order.id, "prev stage: ",  is_at_previous_stage, " available at", available_at, " match", process_match, " at next stage", is_at_follow_up_stage)
        return od

    show_not_applicable: bool = not_appl and len(not_appl) > 0
    show_later_stages = later_stages and len(later_stages) > 0
    show_unknown_eq = unknown_eq and len(unknown_eq) > 0
    orders = snap_obj.orders
    if not show_not_applicable:
        orders = [o for o in orders if equipment in o.allowed_equipment]
    if not show_unknown_eq:
        orders = [o for o in orders if o.current_equipment and len(o.current_equipment) > 0]
    data = sorted([data_for_order(o) for o in orders], key=lambda dt: dt["sort"])
    if not show_later_stages:
        data = [d for d in data if not d.get("later_stage")]
    tons_available = sum(o["weight"] for o in data if o.get("available"))
    tons_total = sum(o["weight"] for o in data)
    return data, f"{tons_available:.5g}", f"{tons_total:.5g}"


def _get_previous_and_subsequent_processes(processes: Sequence[Process], current: Process) -> tuple[Sequence[Process], Sequence[Process]]:
    current_id = current.name_short
    previous: list[Process] = _prev_processes_transitive(processes, [current], [current_id])
    nxt = _next_processes_transitive(processes, [current], [current_id])
    return previous, nxt


def _prev_processes_transitive(processes: Sequence[Process], previous: list[Process], checked_ids: list[str]) -> list[Process]:
    new_procs = [p for p in processes if p.name_short not in checked_ids and p.next_steps is not None and any(p2.name_short in p.next_steps for p2 in previous)]
    checked_ids = checked_ids + [p.name_short for p in new_procs]
    if len(new_procs) > 0:
        new_procs.extend(_prev_processes_transitive(processes, new_procs, checked_ids))
    return new_procs

def _next_processes_transitive(processes: Sequence[Process], nxt: list[Process], checked_ids: list[str]) -> list[Process]:
    follow_up_ids: list[str] = [f for p in nxt if p.next_steps is not None for f in p.next_steps if f not in checked_ids]
    follow_up_procs = [p for p in processes if p.name_short in follow_up_ids]
    if len(follow_up_procs) == 0:
        return []
    checked_ids = checked_ids + [p.name_short for p in follow_up_procs]
    follow_up_procs.extend(_next_processes_transitive(processes, follow_up_procs, checked_ids))
    return follow_up_procs


