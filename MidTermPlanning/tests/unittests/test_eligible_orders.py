import random
import unittest
from datetime import datetime, timezone, timedelta

from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.model import Process, Equipment, Site, Lot, Snapshot, Order, Material


def _create_order(oid: str, equipment: list[int], processes: list[int], weight: float=10, material_count: int=1,
                  lots: dict[str, str]|None = None, lot_positions: dict[str, int]|None=None) -> Order:
    return Order(id=oid, target_weight=weight, actual_weight=weight, material_count=material_count, allowed_equipment=equipment, current_processes=processes,
                 active_processes={p: "PENDING" for p in processes}, lots=lots, lot_positions=lot_positions, material_properties={})

def _create_material_for_order(o: Order, process: int, material_count: int = 1) -> list[Material]:
    return [Material(id=f"{o.id}_{i+1}", order=o.id, weight=o.actual_weight/material_count, current_process=process) for i in range(material_count)]


class EligibleOrdersTest(unittest.TestCase):

    def test_eligible_orders_works1(self):
        rand = random.Random(x=42)
        process_names = ("proc1", "proc2", "proc3")
        num_plants_per_proc = 2
        processes: list[Process] = [Process(name_short=proc, process_ids=[idx+1], next_steps=[process_names[idx+1]] if idx<2 else None) for idx, proc in enumerate(process_names)]
        equipments = [Equipment(id=idx*num_plants_per_proc + cnt, name_short=f"proc{idx+1}_{cnt+1}", process=proc) for idx, proc in enumerate(process_names) for cnt in range(num_plants_per_proc)]
        site = Site(processes=processes, equipment=equipments, storages=[], material_categories=[])
        sp = SnapshotProvider("test:", site)
        snap_time = datetime(year=2025, month=11, day=1, tzinfo=timezone.utc)
        # planning for the next day
        planning_period = (snap_time + timedelta(days=1), snap_time + timedelta(days=2))
        proc1_plants: list[Equipment] = site.get_process_equipment(process_names[0])
        proc2_plants: list[Equipment] = site.get_process_equipment(process_names[1])
        proc3_plants: list[Equipment] = site.get_process_equipment(process_names[2])
        all_equipment = [e.id for e in equipments]
        lots: dict[int, list[Lot]] = {}
        orders = []
        material = []
        for plant_list in (proc1_plants, proc2_plants, proc3_plants):
            for e in plant_list:
                e_lots: dict[str, list[str]] = {f"{e.name_short}.{idx:02d}": [] for idx in range(3)}
                lot_ids = list(e_lots.keys())
                lot_statuses = [1,3,4]
                lot_start_times = [None, snap_time + timedelta(days=1), snap_time]
                lot_end_times = [None, snap_time + timedelta(days=1, hours=8), snap_time + timedelta(hours=8)]  # only the last lot will be finished in time for the planning horizon
                proc_ids = site.get_process(e.process, do_raise=True).process_ids
                for i in range(20):
                    lt: str = lot_ids[rand.randint(0, len(lot_ids)-1)]
                    o_lots = {e.process: lt}
                    pos = len(e_lots[lt])
                    o = _create_order(f"o_{e.name_short}_{i+1}", all_equipment, [proc_ids[0]], lots=o_lots, lot_positions={lt: pos+1})
                    e_lots[lt].append(o.id)
                    orders.append(o)
                    m = _create_material_for_order(o, proc_ids[0])
                    for mat in m:
                        material.append(mat)
                lots[e.id] = [Lot(id=lid, equipment=e.id, orders=lorders, active=True, status=lot_statuses[lot_ids.index(lid)],
                                  start_time=lot_start_times[lot_ids.index(lid)], end_time=lot_end_times[lot_ids.index(lid)]) for lid, lorders in e_lots.items()]
        snap = Snapshot(timestamp=snap_time, orders=orders, material=material, inline_material={}, lots=lots)
        active_process = process_names[-1]
        proc_obj = site.get_process(active_process, do_raise=True)
        proc_ids = proc_obj.process_ids
        active_equipments = site.get_process_equipment(active_process, do_raise=True)
        active_eq_ids = [e.id for e in active_equipments]
        eligible_orders: list[str] = sp.eligible_orders2(snap, active_process, planning_period)
        orders_at_current_stage: list[Order] = [o for o in orders if any(p in proc_ids for p in o.current_processes)]
        active_lots: list[Lot] = [lt for eq, eq_lots in lots.items() if eq in active_eq_ids for lt in eq_lots]
        lots_reschedulable: list[Lot] = [lt for lt in active_lots if sp.is_lot_reschedulable(lt)]
        lots_not_reschedulable: list[Lot] = [lt for lt in active_lots if lt not in lots_reschedulable]
        orders_at_current_stage_reschedulable: list[str] = [o for lot in lots_reschedulable for o in lot.orders]
        orders_at_current_stage_notreschedulable: list[str] = [o for lot in lots_not_reschedulable for o in lot.orders]
        l1 = len(orders_at_current_stage_reschedulable) + len(orders_at_current_stage_notreschedulable)
        orders_by_id = {o.id: o for o in orders}
        lots_by_ids = {lot.id: lot for eq_lots in lots.values() for lot in eq_lots}
        assert l1 == len(orders_at_current_stage), \
            f"Something wrong in the setup; lengths of orders from lots {l1} does not match number of orders at process stage {len(orders_at_current_stage)}"
        assert all(o in eligible_orders for o in orders_at_current_stage_reschedulable), \
            f"Found order in reschedulable lot that was not considered eligible for planning: {next(o for o in orders_at_current_stage_reschedulable if o not in eligible_orders)}, lot {lots_by_ids[orders_by_id[next(o for o in orders_at_current_stage_reschedulable if o not in eligible_orders)].lots[active_process]]}"
        assert all(o not in eligible_orders for o in orders_at_current_stage_notreschedulable), \
            f"Found order in not reschedulable lot that was considered eligible for planning: {next(o for o in orders_at_current_stage_notreschedulable if o in eligible_orders)}, lot {lots_by_ids[orders_by_id[next(o for o in orders_at_current_stage_notreschedulable if o in eligible_orders)].lots[active_process]]}"
        prev_eq = [e.id for e in site.get_process_equipment(process_names[1], do_raise=True)]
        prev_lots: list[Lot] = [lt for eq, eq_lots in lots.items() if eq in prev_eq for lt in eq_lots]
        prev_lot_eligible: list[Lot] = [lt for lt in prev_lots if lt.status == 4]  # status 3 would be acceptable, as well, but we have built the scenario such that status 3 lots will not finish in time for the planning period
        assert 0 < len(prev_lot_eligible) < len(prev_lots), f"Unexpected size of eligible lots for previous stage, {len(prev_lot_eligible)}, expected 0 < size < {len(prev_lots)}."
        prev_orders_eligible = [o for lt in prev_lot_eligible for o in lt.orders]
        prev_orders_noteligible = [o for lt in prev_lots for o in lt.orders if o not in prev_orders_eligible]
        assert all(o in eligible_orders for o in prev_orders_eligible), f"Order at previous stage expected eligibile but found non-eligible {next(o for o in prev_orders_eligible if o not in eligible_orders)}"
        assert all(o not in eligible_orders for o in prev_orders_noteligible), f"Order at previous stage found eligibile although it shouldn't be {next(o for o in prev_orders_noteligible if o in eligible_orders)}"


if __name__ == '__main__':
    unittest.main()



