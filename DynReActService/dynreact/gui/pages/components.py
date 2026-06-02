from datetime import datetime, timedelta
from typing import Sequence

import numpy as np
from dash import html, dcc
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Lot, ProductionPlanning, Order, Material, Equipment, PlannedWorkingShift

from dynreact.app import state


def lots_view(id_prefix: str, initial_hidden: bool=True, ids_toggle: bool=False, *args, **kwargs):
    lot_size: str | None = kwargs.get("lotsize", "time")
    controls = [
        html.Span("Display mode: "),
        dcc.Dropdown(id=id_prefix + "-swimlane-mode", options=[
            {"value": "time", "label": "Time",
             "title": "Show a gantt chart of lots."},
            {"value": "constant", "label": "Lots",
             "title": "All lots are shown with the same width, depending on the available screen space."},
            {"value": "weight", "label": "Weight",
             "title": "The width of a lot is proportional to the total weight of its coils."},
            {"value": "orders", "label": "Orders",
             "title": "The width of a lot is proportional to the number of orders it contains."},
            {"value": "coils", "label": "Coils",
             "title": "The width of a lot is proportional to the number of coils it contains."},
        ], value=lot_size)
    ]
    if ids_toggle:
        controls.append(html.Span("Show lot ids: "))
        controls.append(dcc.Checklist(id=id_prefix + "-lotid-toggle", options= [{"value": ""}] , value=[""]))
    return html.Div([
        html.Div([
            html.H2("Lots view"),
            html.Div(controls, className="planning-swimlane-mode")
        ], id=id_prefix + "-lotsview-header", hidden=initial_hidden),
        html.Div(id=id_prefix + "-lots-swimlane")
    ])


def prepare_lots_for_lot_view(snapshot: str|datetime|None, process: str|None, result: ProductionPlanning | None,
                              is_snap_solution: bool=False, preprend_snapshot: bool=False) -> list[dict[str, any]]:
    snapshot = DatetimeUtils.parse_date(snapshot)
    if process is None or snapshot is None or result is None:
        return []
    plants: dict[int, Equipment] = {p.id: p for p in state.get_site().equipment if p.id in result.equipment_status}
    # XXX these lots lost the initial timing information
    lots: list[Lot] = [lot for plant_lots in result.get_lots().values() for lot in plant_lots if lot.equipment in plants]
    shifts: dict[int, Sequence[PlannedWorkingShift]] = state.get_shifts_provider().load_all(snapshot, end=snapshot+timedelta(days=8), equipments=tuple(plants.keys()))
    snap_obj = state.get_snapshot(snapshot)
    snap_provider = state.get_snapshot_provider()
    # previous_orders: dict[int, Order] = {plant: snap_obj.get_order(order, do_raise=True) for plant, order in result.previous_orders} if result.previous_orders is not None else {}
    previous_lots: dict[int, Lot] = {plant: next((lot for lot in snap_obj.lots[plant] if order in lot.orders), None) for plant, order in result.previous_orders.items() if plant in plants} \
                if result.previous_orders is not None and preprend_snapshot else {}
    previous_lots = {plant: lot for plant, lot in previous_lots.items() if lot is not None}
    previous_complete: dict[int, bool] = {plant: snap_provider.is_lot_complete(lot) for plant, lot in previous_lots.items()}
    if is_snap_solution or preprend_snapshot:
        for eq, eq_lots in snap_obj.lots.items():
            if eq not in plants:
                continue
            for lt in eq_lots:
                match = next((lot for lot in lots if lot.id == lt.id), None)
                if match:  # only necessary because we go through the get_snapshot_solution() method
                    match.start_time = lt.start_time
                    match.end_time = lt.end_time
                    match.status = lt.status
                if preprend_snapshot and eq in previous_lots:  # TODO also show plants without lots but in targets
                    prev_complete = previous_complete[lt.equipment]
                    current_complete = snap_provider.is_lot_complete(lt)
                    if (prev_complete and not current_complete) or (previous_lots[eq].end_time is not None and lt.end_time is not None and lt.end_time > previous_lots[eq].end_time):
                        continue
                    if not prev_complete and not current_complete:
                        plant_lots = snap_obj.lots[eq]
                        if plant_lots.index(previous_lots[eq]) < plant_lots.index(lt):
                            continue
                    lots.insert(0, lt)
    orders_by_lot: dict[str, list[Order | None]] = {lot.id: [snap_obj.get_order(o_id) for o_id in lot.orders] for lot in lots}
    all_due_dates = {lot: [o.due_date for o in orders if o is not None] for lot, orders in orders_by_lot.items()}
    first_due_dates = {lot: min((o.due_date for o in orders if o is not None and o.due_date is not None), default=DatetimeUtils.to_datetime(0)) for
                       lot, orders in orders_by_lot.items()}
    total_weights = {lot: sum(
        o.actual_weight if o.actual_weight is not None else (o.target_weight if o.target_weight is not None else 0)
        for o in orders if o is not None) for lot, orders in orders_by_lot.items()}
    equipment_with_missing_time_info = set(lot.equipment for lot in lots if lot.start_time is None or lot.end_time is None)
    equipment_timing_info = {e: [lot.weight/((lot.end_time - lot.start_time).total_seconds()/3_600) for lot in lots if lot.equipment == e and lot.start_time is not None and lot.end_time is not None and lot.weight is not None]
                             for e in equipment_with_missing_time_info}
    # tons per hour
    throughput_capacity: dict[int, float] = {e: plants[e].throughput_capacity or (np.mean(equipment_timing_info[e]) if len(equipment_timing_info[e]) > 0 else 1.) for e in equipment_with_missing_time_info}
    start_time_by_equipment: dict[int, datetime] = {e: max([lt.end_time for lt in lots if lt.end_time is not None and lt.equipment == e] + [snapshot]) for e in equipment_with_missing_time_info}
    start_times_calculated: dict[str, datetime] = {}
    end_times_calculated: dict[str, datetime] = {}
    _empty = tuple()
    for e in equipment_with_missing_time_info:
        start_time = start_time_by_equipment[e]
        cap = throughput_capacity[e]
        eq_shifts = shifts.get(e, _empty)
        shift_horizon: datetime = max(shift.period[1] for shift in eq_shifts) if len(eq_shifts) > 0 else snapshot
        for lot in (lt for lt in lots if lt.equipment == e and lt.end_time is None):
            weight = total_weights[lot.id]
            current_shift_idx, current_shift = next(((shift_idx, shift) for shift_idx, shift in enumerate(eq_shifts) if shift.period[1] > start_time and shift.worktime.total_seconds() > 0),
                                                    (None, None)) if start_time < shift_horizon else (None, None)
            if current_shift is None:
                end_time = start_time + timedelta(hours=weight / cap)
            else:
                weight_assigned = 0
                start_time = max(start_time, current_shift.period[0])
                end_time = start_time
                while weight_assigned < weight - 1e-4 and current_shift is not None:
                    lot_start = max(current_shift.period[0], start_time)
                    fraction_available: float = 1. if current_shift.period[0] >= start_time else (current_shift.period[1] - start_time)/(current_shift.period[1]-current_shift.period[0])
                    available: timedelta = fraction_available * current_shift.worktime
                    if available.total_seconds() > 0:
                        max_prod = available.total_seconds()/3_600 * cap
                        if max_prod >= weight - weight_assigned - 1e-4:  # done
                            new_assigned = weight - weight_assigned
                            weight_assigned += new_assigned
                            fraction = new_assigned / max_prod
                            end_time = lot_start + fraction * (current_shift.period[1] - lot_start)
                            break
                        else:
                            weight_assigned += max_prod
                            end_time = current_shift.period[1]
                    current_shift_idx += 1
                    current_shift = eq_shifts[current_shift_idx] if len(eq_shifts) > current_shift_idx else None
                if weight_assigned < weight - 1e-4:
                    end_time = end_time + timedelta(hours=(weight-weight_assigned) / cap)
            start_times_calculated[lot.id] = start_time
            end_times_calculated[lot.id] = end_time
            start_time = end_time
    all_coils_by_orders: dict[str, list[Material]] = state.get_coils_by_order(snapshot)
    num_coils = {
        lot: sum(len(all_coils_by_orders[o.id]) if o.id in all_coils_by_orders else 0 for o in orders if o is not None)
        for lot, orders in orders_by_lot.items()}

    def row_for_lot(lot: Lot) -> dict[str, any]:
        return {
            "id": lot.id,
            "equipment": lot.equipment,
            "plant": plants[lot.equipment].name_short if lot.equipment in plants and plants[
                lot.equipment].name_short is not None else str(lot.equipment),
            "active": lot.active,
            "status": lot.status,
            "lot_complete": snap_provider.is_lot_complete(lot),
            "num_orders": len(lot.orders),
            "num_coils": num_coils[lot.id],
            "order_ids": lot.orders,  # ", ".join(lot.orders),
            "first_due_date": first_due_dates[lot.id],
            "all_due_dates": all_due_dates[lot.id],
            "total_weight": total_weights[lot.id],
            "start_time": lot.start_time or start_times_calculated.get(lot.id),
            "end_time": lot.end_time or end_times_calculated.get(lot.id)
        }

    data = [row_for_lot(lot) for lot in lots]
    if not any(lt.get("end_time") is None for lt in data):
        data = sorted(data, key=lambda lot: lot["end_time"])
    else:
        data = sorted(data, key=lambda lot: lot["id"])
    return data

