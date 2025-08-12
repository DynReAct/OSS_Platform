from datetime import datetime
from typing import Mapping

from dynreact.base.model import Lot, Snapshot, Site, Order


class UpdatedSnapshot(Snapshot):
    original: Snapshot
    "Reference to the original snapshot"


class SnapshotUpdate(Mapping):

    def __init__(self, site: Site):
        self._site = site
        self._refs: dict[datetime, UpdatedSnapshot] = {}

    def clear(self):
        self._refs.clear()

    def __getitem__(self, key):
        return self._refs[key]

    def __iter__(self):
        return iter(self._refs)

    def __len__(self):
        return len(self._refs)

    def __delitem__(self, key):
        del self._refs[key]

    def __contains__(self, key) -> bool:
        return key in self._refs

    def __repr__(self):
        return f"{self.__class__.__name__}[{list(self._refs.keys())}]"

    def __str__(self):
        return f"{self.__class__.__name__}"

    def update_snapshot(self, snapshot: Snapshot, lot: Lot) -> UpdatedSnapshot:
        """Creates a new snapshot with orders and lots updated TODO update material fields order_positions"""
        lot_plant = self._site.get_equipment(lot.equipment, do_raise=True)
        process = lot_plant.process
        affected_plants: list[int] = [e.id for e in self._site.get_process_equipment(process)]
        all_lots: dict[int, list[Lot]] = {p: list(lts) for p, lts in snapshot.lots.items()}  # semi-deep copy
        affected_lots: list[Lot] = [lot for plant, lts in all_lots.items() for lot in lts if plant in affected_plants]
        orders: list[str] = lot.orders
        all_orders = list(snapshot.orders)
        order_objects: dict[str, Order] = {o.id: o for o in all_orders}
        for other_lot in affected_lots:
            contains_order = any(o in orders for o in other_lot.orders)
            if not contains_order:
                continue
            new_orders = [o for o in other_lot.orders if o not in orders]
            plant_lots = all_lots[other_lot.equipment]
            idx = plant_lots.index(other_lot)
            plant_lots.pop(idx)
            if len(new_orders) > 0:
                new_weight = sum(order_objects[o].actual_weight for o in new_orders) if other_lot.weight is not None else None
                new_lot = other_lot.copy(update={"orders": new_orders, "weight": new_weight})
                plant_lots.insert(idx, new_lot)
                for lot_idx, order_id in enumerate(new_orders):
                    order = order_objects[order_id]
                    if order.lot_positions is not None:
                        order_idx = all_orders.index(order)
                        order = order.copy(update={"lot_positions": lot_idx+1})
                        all_orders.pop(order_idx)
                        all_orders.insert(order_idx, order)
        if lot.equipment not in all_lots:
            all_lots[lot.equipment] = []
        all_lots[lot.equipment].append(lot)
        for lot_idx, order_id in enumerate(orders):
            order = order_objects[order_id]
            o_lots = dict(order.lots) if order.lots is not None else {}
            o_lot_positions = dict(order.lot_positions) if order.lot_positions is not None else {}
            o_lots[process] = lot.id
            o_lot_positions[process] = lot_idx + 1
            o_idx = all_orders.index(order)
            order = order.copy(update={"lot_positions": o_lot_positions, "lots": o_lots})
            all_orders.pop(o_idx)
            all_orders.insert(o_idx, order)
        original = snapshot.original if isinstance(snapshot, UpdatedSnapshot) else snapshot
        update = UpdatedSnapshot(timestamp=snapshot.timestamp, orders=all_orders, material=snapshot.material, lots=all_lots, inline_material=snapshot.inline_material, original=original)
        refs = self._refs
        if len(refs) > 4:
            keys = sorted(list(refs.keys()))
            refs.pop(keys[0])
            refs.pop(keys[1])
        refs[snapshot.timestamp] = update
        return update

