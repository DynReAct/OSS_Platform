from datetime import datetime

from dash import html, dcc
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Lot, ProductionPlanning, Order, Material

from dynreact.app import state


# TODO
def lots_view(id_prefix: str, *args, **kwargs):
    lot_size: str | None = kwargs.get("lotsize", "weight")
    return html.Div([
        html.Div([
            html.H2("Lots view"),
            html.Div([
                html.Div("Display mode: "),
                dcc.Dropdown(id=id_prefix + "-swimlane-mode", options=[
                    {"value": "constant", "label": "Constant",
                     "title": "All lots are shown with the same width, depending on the available screen space."},
                    {"value": "weight", "label": "Weight",
                     "title": "The width of a lot is proportional to the total weight of its coils."},
                    {"value": "orders", "label": "Orders",
                     "title": "The width of a lot is proportional to the number of orders it contains."},
                    {"value": "coils", "label": "Coils",
                     "title": "The width of a lot is proportional to the number of coils it contains."},
                ], value=lot_size)
            ], className="planning-swimlane-mode")
        ], id=id_prefix + "-lotsview-header", hidden=True),
        html.Div(id=id_prefix + "-lots-swimlane")
    ])


def prepare_lots_for_lot_view(snapshot: str|datetime|None, process: str|None, result: ProductionPlanning | None) -> list[dict[str, any]]:
    snapshot = DatetimeUtils.parse_date(snapshot)
    if process is None or snapshot is None or result is None:
        return []
    lots: list[Lot] = [lot for plant_lots in result.get_lots().values() for lot in plant_lots]
    plants = {p.id: p for p in state.get_site().equipment}
    snap_obj = state.get_snapshot(snapshot)
    orders_by_lot: dict[str, list[Order | None]] = {}
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
    all_due_dates = {lot: [o.due_date for o in orders if o is not None] for lot, orders in orders_by_lot.items()}
    first_due_dates = {lot: min((o.due_date for o in orders if o is not None and o.due_date is not None), default=DatetimeUtils.to_datetime(0)) for
                       lot, orders in orders_by_lot.items()}
    total_weights = {lot: sum(
        o.actual_weight if o.actual_weight is not None else (o.target_weight if o.target_weight is not None else 0)
        for o in orders if o is not None) for lot, orders in orders_by_lot.items()}
    all_coils_by_orders: dict[str, list[Material]] = state.get_coils_by_order(snapshot)
    num_coils = {
        lot: sum(len(all_coils_by_orders[o.id]) if o.id in all_coils_by_orders else 0 for o in orders if o is not None)
        for lot, orders in orders_by_lot.items()}

    def row_for_lot(lot: Lot) -> dict[str, any]:
        return {
            "id": lot.id,
            "plant_id": lot.equipment,
            "plant": plants[lot.equipment].name_short if lot.equipment in plants and plants[
                lot.equipment].name_short is not None else str(lot.equipment),
            "num_orders": len(lot.orders),
            "num_coils": num_coils[lot.id],
            "order_ids": lot.orders,  # ", ".join(lot.orders),
            "first_due_date": first_due_dates[lot.id],
            "all_due_dates": all_due_dates[lot.id],
            "total_weight": total_weights[lot.id]
        }

    data = sorted([row_for_lot(lot) for lot in lots], key=lambda lot: lot["id"])
    return data

