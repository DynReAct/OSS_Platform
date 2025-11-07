import argparse
import glob
import json
import os.path
import time
from typing import Sequence, Mapping, Any
from datetime import timedelta, datetime, timezone
from enum import Enum

from pydantic import BaseModel

from dynreact.app_config import DynReActSrvConfig
from dynreact.base.AggregationProvider import AggregationLevel
from dynreact.base.CostProvider import CostProvider
from dynreact.base.LotSink import LotSink
from dynreact.base.LotsOptimizer import LotsOptimizationState
from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.impl.AggregationPersistence import AggregationInternal
from dynreact.base.impl.AggregationProviderImpl import AggregationProviderImpl
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.MaterialAggregation import MaterialAggregation
from dynreact.base.impl.Scenarios import MidTermScenario, MidTermBenchmark
from dynreact.base.model import Snapshot, Material, OrderAssignment, Order, EquipmentProduction, ProductionTargets, \
    ProductionPlanning, ObjectiveFunction, Site, LabeledItem, Lot, Process, Equipment, PlannedWorkingShift
from dynreact.plugins import Plugins


class Boolean(str, Enum):
    true = "true"
    false = "false"


def _trafo_args(parser: argparse.ArgumentParser|None=None, include_snapshot: bool=True) -> argparse.ArgumentParser:
    parser = parser if parser is not None else argparse.ArgumentParser()
    parser.add_argument("-cp", "--config-provider", help="Config provider id, such as", type=str, default=None)
    parser.add_argument("-snp", "--snapshot-provider", help="Snapshot provider id, such as", type=str, default=None)
    if include_snapshot:
        parser.add_argument("-s", "--snapshot", help="Snapshot timestamp", type=str, default=None)
    parser.add_argument("-cost", "--cost-provider", help="Cost provider id, such as", type=str, default=None)
    parser.add_argument("-d", "--details", help="Show details", action="store_true")
    return parser


# TODO option to aggregate by storage content
def analyze_snapshot():
    parser = _trafo_args()
    parser.add_argument("-e", "--equipment", help="Optional equipment id, only relevant if --details flag is set", type=str, default=None)
    parser.add_argument("-p", "--process", help="Optional process id, only relevant if --details flag is set", type=str, default=None)
    parser.add_argument("-cat", "--category", help="Optional material category, only relevant if --details flag is set", type=str, default=None)
    args = parser.parse_args()
    config = DynReActSrvConfig(config_provider=args.config_provider, snapshot_provider=args.snapshot_provider)
    plugins = Plugins(config)
    snap: datetime|None = DatetimeUtils.parse_date(args.snapshot)
    snapshot: Snapshot = plugins.get_snapshot_provider().load(time=snap)
    orders = snapshot.orders
    material = snapshot.material
    lots: list[Lot] = [l for lots in snapshot.lots.values() for l in lots]
    site = plugins.get_config_provider().site_config()
    proc_text = ""
    if args.process:
        proc_obj = site.get_process(args.process.upper())
        if proc_obj is None:
            p_upper =  args.process.upper()
            proc_obj = next((p for p in site.processes if p.synonyms is not None and any(s.upper() == p_upper for s in p.synonyms)), None)
            if proc_obj is None:
                raise Exception("Process not found ", args.process)
        orders = [o for o in orders if any(p in proc_obj.process_ids for p in o.current_processes)]
        material = [m for m in material if m.current_process in proc_obj.process_ids]
        lots = [l for l in lots if site.get_equipment(l.equipment, do_raise=True).process == proc_obj.name_short]
        proc_text = f", [process={proc_obj.name_short}]"
    print(f"Snapshot {snapshot.timestamp}{proc_text}, orders: {len(orders)} (weight: {sum(o.actual_weight for o in orders):.1f}t), materials: {len(material)}, lots: {len(lots)}")
    if args.details:
        agg = MaterialAggregation(site, plugins.get_snapshot_provider())
        plant_agg: dict[int, dict[str, dict[str, float]]] = agg.aggregate_categories_by_plant(snapshot)
        for plant, mat in plant_agg.items():
            pl_obj = site.get_equipment(plant)
            if args.equipment:
                if pl_obj is None and args.equipment != str(plant):
                    continue
                elif pl_obj is not None:
                    if args.equipment != str(plant) and args.equipment.upper() != pl_obj.name_short.upper():
                        continue
            if args.process and args.process.upper() != pl_obj.process.upper():
                proc = site.get_process(pl_obj.process)
                wanted = args.process.upper()
                if proc.synonyms is None or wanted not in proc.synonyms:
                    continue
            print(f"Equipment {_print_obj(pl_obj if pl_obj is not None else plant)}: ")
            for cat, classes in mat.items():
                cat_obj = next((c for c in site.material_categories if c.id == cat), None)
                if args.category is not None:
                    if cat_obj is None and args.category.lower() !=  cat.lower():
                        continue
                    elif cat_obj is not None:
                        c = args.category.lower()
                        if c != cat.lower() and c != cat_obj.name.lower():
                            continue
                text = ", ".join([f"{_print_obj(next(clz for clz in cat_obj.classes if clz.id == cl) if cat_obj is not None else cl)}: {value:.1f}t" for cl, value in classes.items()])
                print(f"  {cat_obj.name or cat_obj.id if cat_obj is not None else cat}: {text}")

def analyze_lots():
    parser = _trafo_args()
    parser.add_argument("-e", "--equipment", help="Plant name or plant id", type=str, default=None)
    parser.add_argument("-p", "--process", help="Process(es), separated by \",\"", type=str, default=None)
    parser.add_argument("-so", "--skip-orders", help="Skip orders", action="store_true")
    parser.add_argument("-lt", "--lot", help="Filter by lot id; separate multiple by \",\"", type=str, default=None)
    parser.add_argument("-ls", "--lot-status", help="Filter by lot status", type=int, default=None)  # TODO can we allow for a list as well?
    parser.add_argument("-la", "--lot-active", help="Filter by lot active status", type=Boolean, default=None, choices=[b.value for b in Boolean])
    parser.add_argument("-sc", "--skip-comment", help="Hide lot comment", action="store_true")
    args = parser.parse_args()
    config = DynReActSrvConfig(config_provider=args.config_provider, snapshot_provider=args.snapshot_provider)
    equipment = args.equipment
    if equipment is not None:
        equipment = [e.strip().upper() for e in equipment.split(",")]
    process = args.process
    if process is not None:
        process = [P.strip().upper() for P in process.split(",")]
    skip_comment = args.skip_comment
    status = args.lot_status
    active = args.lot_active
    plugins = Plugins(config)
    site = plugins.get_config_provider().site_config()
    snap: datetime | None = DatetimeUtils.parse_date(args.snapshot)
    snapshot: Snapshot = plugins.get_snapshot_provider().load(time=snap)
    plant_ids = list(snapshot.lots.keys())
    processes = [p.name_short for p in site.processes]
    plants = [site.get_equipment(p, do_raise=True) for p in plant_ids]
    plants.sort(key=lambda p: (processes.index(p.process) if p.process in processes else -1, p.id))
    orders = {o.id: o for o in snapshot.orders}
    material: dict[str, list[Material]] = {}  # keys: order ids
    lot_filter = [l.strip().upper() for l in args.lot.split(",")] if args.lot is not None else None
    for m in snapshot.material:
        if m.order not in material:
            material[m.order] = []
        material[m.order].append(m)
    for plant in plants:
        plant_id = plant.id
        plant = site.get_equipment(plant_id, do_raise=True)
        if equipment is not None and (plant.name_short is None or plant.name_short.upper() not in equipment) and str(plant_id) not in equipment:
            continue
        if process is not None and plant.process.upper() not in process:
            proc = next(p for p in site.processes if p.name_short == plant.process)
            if proc.synonyms is None or not any(syn in process for syn in proc.synonyms):
                continue
        lots = snapshot.lots[plant_id]
        lines = []
        aggregated_tons = 0
        for lot in lots:
            if lot_filter is not None and lot.id.upper() not in lot_filter:
                continue
            lot_orders = [orders.get(o) for o in lot.orders]
            total_weight = sum(o.actual_weight for o in lot_orders)
            if lot.active:
                aggregated_tons += total_weight
            if status is not None and lot.status != status:
                continue
            if active is not None and str(lot.active).lower() != active:
                continue
            has_any = True
            materials = [mat for order in lot_orders for mat in material.get(order.id)]
            lot_line = f"    Lot {lot.id}, active={lot.active}, status={lot.status}, weight={total_weight:7.2f}t, order cnt={len(lot.orders):2}, material cnt={len(materials):2}"
            if hasattr(lot, "priority"):
                lot_line += f", priority={getattr(lot, 'priority')}"
            if not skip_comment and lot.comment is not None:
                lot_line += f", comment={lot.comment}"
            if not args.skip_orders:
                lot_line += f", orders= {lot.orders}"
            lines.append(lot_line)
        if lot_filter is not None and len(lines) == 0:
            continue
        print(f"  Plant {plant.name_short} [id={plant.id}, process={plant.process}, active lots weight={aggregated_tons:7.1f}t]:")
        for lot_line in lines:
            print(lot_line)


def analyze_site():
    parser = _trafo_args()
    args = parser.parse_args()
    config = DynReActSrvConfig(config_provider=args.config_provider)
    plugins = Plugins(config)
    site = plugins.get_config_provider().site_config()
    print(f"Site has {len(site.processes)} processes, {len(site.equipment)} equipments, {len(site.storages)} storages.")
    if args.details:
        print("Processes: ", [p.name_short for p in site.processes])
        for p in site.processes:
            plants = site.get_process_equipment(p.name_short)
            print(f"  Process {p.name_short}:")
            for plant in plants:
                print(f"    Plant {plant.name_short} ({plant.id}) [storage_in: {plant.storage_in}, storage_out: {plant.storage_out}]")
        print("Storages:")
        for stg in site.storages:
            print(f"  Storage {stg.name_short} [plants={stg.equipment}, capacity={stg.capacity_weight}]")
        print("Material categories:")
        for cat in site.material_categories:
            print(f"  Category {cat.id} [name={cat.name}]:")
            for cl in cat.classes:
                extra = ""
                if cl.default_share is not None:
                    extra = f", default_share={cl.default_share}"
                if cl.is_default:
                    extra = f", default_class=true"
                print(f"    Class {cl.id} [name={cl.name}{extra}]")

def evaluate_lot():
    parser = argparse.ArgumentParser()
    parser.add_argument("lot", help="Lot id", type=str)
    parser = _trafo_args(parser=parser)
    args = parser.parse_args()
    config = DynReActSrvConfig(config_provider=args.config_provider, snapshot_provider=args.snapshot_provider, cost_provider=args.cost_provider)
    lot_id = args.lot.strip().upper()
    plugins = Plugins(config)
    site = plugins.get_config_provider().site_config()
    snap: datetime | None = DatetimeUtils.parse_date(args.snapshot)
    snapshot: Snapshot = plugins.get_snapshot_provider().load(time=snap)
    all_lots = (lot for lots in snapshot.lots.values() for lot in lots)
    lot = next((lot for lot in all_lots if lot.id.upper() == lot_id), None)
    if lot is None:
        raise Exception(f"Lot not found: {args.lot} in snapshot {snapshot.timestamp}")
    costs = plugins.get_cost_provider()
    equipment_id = lot.equipment
    equipment = site.get_equipment(equipment_id, do_raise=True)
    lot_orders: dict[str, Order] = {o: snapshot.get_order(o, do_raise=True) for o in lot.orders}
    order_assignments = {o_id: OrderAssignment(equipment=equipment_id, order=o_id, lot=lot_id, lot_idx=idx + 1) for idx, (o_id, o) in enumerate(lot_orders.items())}
    period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
    targets = ProductionTargets(process=equipment.process, period=period, target_weight={equipment_id:
                                EquipmentProduction(equipment=equipment_id, total_weight=sum(o.actual_weight for o in lot_orders.values()))})
    result: ProductionPlanning = costs.evaluate_order_assignments(equipment.process, order_assignments, targets, snapshot)
    #objectives: ObjectiveFunction = costs.objective_function(result.equipment_status[equipment_id])
    #total_weight = sum(t.total_weight for t in targets.target_weight.values())
    _print_planning(result, snapshot, site, costs)


def create_lots():
    parser = argparse.ArgumentParser()
    parser.add_argument("-l", "--lot", help="Use all orders from one or multiple existing lot(s), separated by \",\"", type=str)
    parser.add_argument("-o", "--order", help="Specify orders to include in the backlog, separated by \",\"", type=str)
    parser.add_argument("-t", "--tons", help="Target weight to be scheduled. If not specified but the \"--lot\" parameter is set, then the size of the lot it used instead. Otherwise it is set to the overall size of the order backlog.", type=float, default=None)
    parser.add_argument("-e", "--equipment", help="Specify the equipment for which the lot will be created. Can be skipped if the \"--lot\" parameter is set.", type=str, default=None)
    parser.add_argument("-it", "--iterations", help="Specify number of optimization iterations. Default: 100.", type=int, default=100)
    parser.add_argument("-se", "--start-existing", help="If the flag is set and an existing lot is specified via \"--lot\", then the algorithm will start from the configuration of the existing lot, otherwise it will start from an empty configuration", action="store_true")
    parser.add_argument("-fao", "--force-all-orders", help="Enforce that all orders are assigned to a lot", action="store_true")
    parser.add_argument("-fo", "--force-orders", help="Enforce that specific orders are assigned to a lot", type=str)
    parser = _trafo_args(parser=parser)
    args = parser.parse_args()
    config = DynReActSrvConfig(config_provider=args.config_provider, snapshot_provider=args.snapshot_provider, cost_provider=args.cost_provider)

    plugins = Plugins(config)
    site = plugins.get_config_provider().site_config()
    snap: datetime | None = DatetimeUtils.parse_date(args.snapshot)
    snapshot: Snapshot = plugins.get_snapshot_provider().load(time=snap)
    costs = plugins.get_cost_provider()
    equipment_id = args.equipment
    if args.lot is not None:
        lot_id = args.lot.strip().upper()  # TODO could be multiple lots!
        all_lots = (lot for lots in snapshot.lots.values() for lot in lots)
        lot = next((lot for lot in all_lots if lot.id.upper() == lot_id), None)
        if lot is None:
            raise Exception(f"Lot not found: {args.lot} in snapshot {snapshot.timestamp}")
        equipment_id = lot.equipment
        orders: dict[str, Order] = {o: snapshot.get_order(o, do_raise=True) for o in lot.orders}
    else:
        if args.order is None:
            raise Exception("Neither \"--lot\" nor \"--order\" parameter has been set.")
        orders0 = (o.trim() for o in args.order.split(","))
        orders = {o: snapshot.get_order(o, do_raise=True) for o in orders0 if o != ""}
    tons = args.tons
    if tons is None:
        tons = sum(o.actual_weight for o in orders.values())
    equipment = site.get_equipment(equipment_id, do_raise=True) if isinstance(equipment_id, int) else site.get_equipment_by_name(equipment_id, do_raise=True)
    equipment_id = equipment.id
    do_force: bool = args.force_all_orders
    start_existing = args.lot is not None and args.start_existing
    order_assignments = {o: OrderAssignment(equipment=-1, order=o, lot="", lot_idx=-1) for o in orders.keys()} if not start_existing else \
        {o: OrderAssignment(equipment=equipment_id, order=o, lot=lot.id, lot_idx=idx+1) for idx, o in enumerate(orders.keys())}
    period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
    targets = ProductionTargets(process=equipment.process, period=period, target_weight={equipment_id: EquipmentProduction(equipment=equipment_id, total_weight=tons)})
    # initial solution
    empty_start = costs.evaluate_order_assignments(equipment.process, order_assignments, targets, snapshot)
    algo = plugins.get_lots_optimization()
    forced_orders = list(orders.keys()) if do_force else [o.strip() for o in args.force_orders.split(",")] if args.force_orders is not None else None
    optimization = algo.create_instance(equipment.process, snapshot, costs, targets, initial_solution=empty_start, forced_orders=forced_orders)
    # TODO in separate thread, interruptable?
    state: LotsOptimizationState = optimization.run(max_iterations=args.iterations)
    sol = state.best_solution
    _print_planning(sol, snapshot, site, costs)


def show_orders():
    parser = argparse.ArgumentParser(description="The fields to be shown can be selected either by means of the -f/--field parameter (supports initial or final wildcard '*'), or the "+
                            "-ef/--equipment-fields parameter. In the latter case, the cost-relevant fields for the specified equipment are shown. \n" +
                            "Orders can be selected either directly via the -o/--order field, via -p/--process, via -e/--equipment, or via -lt/--lot.")
    parser = _trafo_args(parser=parser)
    parser.add_argument("-o", "--order", help="Select order(s) to be displayed. Separate multiple fields by \",\"", type=str, default=None)
    parser.add_argument("-f", "--field", help="Select field(s) to be displayed. Separate multiple fields by \",\"", type=str, default=None)
    parser.add_argument("-ef", "--equipment-fields", help="Select fields to be displayed based on the cost-relevant fields for the specified equipment", type=str, default=None)
    parser.add_argument("-p", "--process", help="Filter orders by current process stage", type=str, default=None)
    parser.add_argument("-lt", "--lot", help="Filter orders by lot(s)", type=str, default=None)
    parser.add_argument("-e", "--equipment", help="Filter orders by current equipment", type=str, default=None)
    parser.add_argument("-w", "--wide", help="Show wide cells, do not crop content", action="store_true")
    parser.add_argument("-sen", "--skip-equipment-name", help="Show only equipment ids, no names, for fields involving equipment references", action="store_true")
    args = parser.parse_args()
    config = DynReActSrvConfig(config_provider=args.config_provider)
    plugins = Plugins(config)
    site = plugins.get_config_provider().site_config()
    snap: datetime | None = DatetimeUtils.parse_date(args.snapshot)
    snapshot: Snapshot = plugins.get_snapshot_provider().load(time=snap)
    orders = snapshot.orders
    if args.order:
        order_ids = [o.strip() for o in args.order.split(",")]
        orders = [o for o in orders if o.id in order_ids]
    if args.process:
        process_ids = [p for p in (p.strip() for p in args.process.split(",")) if p != ""]
        processes = [_process_for_id(site.processes, p) for p in process_ids]
        process_codes: list[int] = [code for p in processes for code in p.process_ids]
        orders = [o for o in orders if any(p in process_codes for p in o.current_processes)]
    if args.equipment:
        plant_ids = [p for p in (p.strip() for p in args.equipment.split(",")) if p != ""]
        plants = [_plant_for_id(site.equipment, p) for p in plant_ids]
        plant_codes = [p.id for p in plants]
        orders = [o for o in orders if o.current_equipment is not None and any(e in plant_codes for e in o.current_equipment)]
    if args.lot:
        lot_ids = [l.strip().upper() for l in args.lot.split(",")]
        lots = [lot for lots in snapshot.lots.values() for lot in lots if lot.id.upper() in lot_ids]
        if len(lots) == 0:
            print(f"No matching lot found for {args.lot}")
            return
        order_ids = [o for lot in lots for o in lot.orders]
        orders = [o for o in orders if o.id in order_ids]
    if len(orders) == 0:
        print("No matching orders found")
        return
    fields = (f.strip() for f in args.field.split(",")) if args.field is not None else None
    first = orders[0]
    fields = [f for flds in (_field_for_order(first, f) for f in fields) for f in flds] if fields is not None else None
    if args.equipment_fields:
        plant = _plant_for_id(site.equipment, args.equipment_fields)
        relevant_fields: list[str]|None = plugins.get_cost_provider().relevant_fields(plant)
        if relevant_fields is not None:
            fields = fields if fields is not None else []
            fields = fields + [f for f in relevant_fields if f not in fields]
    if fields is not None and len(fields) == 0:
        print("No matching field found for ", args.field)
        return
    filter_existing = args.field is None
    equipment = None if args.skip_equipment_name else site.equipment
    wide: bool = args.wide or fields is not None and len(fields) < 3
    _print_orders(orders, fields, wide=wide, filter_existent_properties=filter_existing, equipment=equipment)


def show_material():
    parser = _trafo_args()
    parser.add_argument("-m", "--material", help="Specify material ids to be displayed. Separate multiple entries by \",\"",type=str, default=None)
    parser.add_argument("-o", "--order", help="Select order(s) to be displayed. Separate multiple orders by \",\"", type=str, default=None)
    parser.add_argument("-p", "--process", help="Filter orders by current process stage", type=str, default=None)
    parser.add_argument("-lt", "--lot", help="Filter orders by lot(s)", type=str, default=None)
    parser.add_argument("-e", "--equipment", help="Filter orders by current equipment", type=str, default=None)
    parser.add_argument("-f", "--field", help="Select field(s) to be displayed. Separate multiple fields by \",\"", type=str, default=None)
    parser.add_argument("-w", "--wide", help="Show wide cells, do not crop content", action="store_true")
    # parser.add_argument("-sen", "--skip-equipment-name", help="Show only equipment ids, no names, for fields involving equipment references", action="store_true")
    args = parser.parse_args()
    config = DynReActSrvConfig(config_provider=args.config_provider)
    plugins = Plugins(config)
    site = plugins.get_config_provider().site_config()
    snap: datetime | None = DatetimeUtils.parse_date(args.snapshot)
    snapshot: Snapshot = plugins.get_snapshot_provider().load(time=snap)
    material = snapshot.material
    orders = snapshot.orders
    if args.order:
        order_ids = [o.strip() for o in args.order.split(",")]
        orders = [o for o in orders if o.id in order_ids]
    if args.process:
        process_ids = [p for p in (p.strip() for p in args.process.split(",")) if p != ""]
        processes = [_process_for_id(site.processes, p) for p in process_ids]
        process_codes: list[int] = [code for p in processes for code in p.process_ids]
        orders = [o for o in orders if any(p in process_codes for p in o.current_processes)]
    if args.equipment:
        plant_ids = [p for p in (p.strip() for p in args.equipment.split(",")) if p != ""]
        plants = [_plant_for_id(site.equipment, p) for p in plant_ids]
        plant_codes = [p.id for p in plants]
        orders = [o for o in orders if o.current_equipment is not None and any(e in plant_codes for e in o.current_equipment)]
    if args.lot:
        lot_ids = [l.strip().upper() for l in args.lot.split(",")]
        lots = [lot for lots in snapshot.lots.values() for lot in lots if lot.id.upper() in lot_ids]
        if len(lots) == 0:
            print(f"No matching lot found for {args.lot}")
            return
        order_ids = [o for lot in lots for o in lot.orders]
        orders = [o for o in orders if o.id in order_ids]
    if len(orders) == 0:
        print("No matching orders found")
        return
    if args.material is not None:
        mat_ids = [m.strip() for m in args.material.split(",")]
        material = [m for m in material if m.id in mat_ids]
    material = {o.id: [m for m in material if m.order == o.id] for o in orders}
    if len(material) == 0 or sum(len(m) for m in material.values()) == 0:
        print("No matching material found")
        return
    first: Material = next(iter(material.values()))[0]
    fields = (f.strip() for f in args.field.split(",")) if args.field is not None else None
    fields = [f for flds in (_field_for_order(first, f) for f in fields) for f in flds] if fields is not None else None
    wide=args.wide
    eq = site.equipment
    for o_id, mat in material.items():
        all_mats = [m for m in snapshot.material if m.order == o_id]
        print(f"Order {o_id} has {len(all_mats)} materials and actual weight {sum(m.weight for m in all_mats):.2f}t.")
        _print_orders(mat, fields, wide=wide, equipment=eq)


def show_shifts():
    parser = argparse.ArgumentParser()
    parser.add_argument("-p", "--process", help="Filter by process stage", type=str, default=None)
    parser.add_argument("-eq", "--equipment", help="Filter by equipment; separate multiple by commas.", type=str, default=None)
    parser.add_argument("-s", "--start", help="Start time", type=str, default=None)
    parser.add_argument("-e", "--end", help="End time", type=str, default=None)
    parser.add_argument("-l", "--limit", help="Limit, max number of shifts to show", type=int, default=100)
    parser.add_argument("-cp", "--config-provider", help="Config provider id, such as", type=str, default=None)
    #parser.add_argument("-w", "--wide", help="Show wide cells, do not crop content", action="store_true")
    args = parser.parse_args()
    start: datetime | None = DatetimeUtils.parse_date(args.start)
    end: datetime | None = DatetimeUtils.parse_date(args.end)
    if start is None:
        start = DatetimeUtils.now()
    config = DynReActSrvConfig(config_provider=args.config_provider)
    plugins = Plugins(config)
    site = plugins.get_config_provider().site_config()
    provider = plugins.get_shifts_provider()
    equipment: list[Equipment]|None = _plants_for_ids(args.equipment, site)
    procs = _processes_for_ids(args.process, site)
    if procs is not None:
        proc_ids = [p.name_short for p in procs]
        equipment = [e for e in equipment if e.process in proc_ids] if equipment is not None else [e for proc in proc_ids for plants in site.get_process_equipment(proc) for e in plants]
    all_shifts: dict[int, Sequence[PlannedWorkingShift]] = provider.load_all(start, end=end, equipments=[e.id for e in equipment], limit=args.limit)
    print("Shifts:")
    for plant, shifts in all_shifts.items():
        equip = site.get_equipment(plant)
        print(f"Equipment {equip.name_short or equip.id}:")
        for shift in shifts:
            hours = shift.worktime.total_seconds() / 3600
            hours = int(hours) if hours == int(hours) else round(hours, 1)
            print(f"|  {DatetimeUtils.format(shift.period[0], use_zone=False).replace("T", " ")}  |  {DatetimeUtils.format(shift.period[1], use_zone=False).replace("T", " ")} | {hours} |")


def _field_for_order(o: Order|Material, field: str) -> Sequence[str]:
    if hasattr(o, field):
        return (field, )
    if isinstance(o, Order) and hasattr(o.material_properties, field):
        return ("material_properties." + field, )
    if "*" in field:
        start_wildcard: bool = field.startswith("*")
        end_wildcard: bool = field.endswith("*")
        if start_wildcard:
            new_field = field.upper()
            new_field = new_field[1:]
        if end_wildcard:
            new_field = new_field[:-1]
        fields = [key for key, info in o.model_fields.items() if new_field in key.upper() and (start_wildcard or key.upper().startswith(new_field)) and (end_wildcard or key.upper().endswith(new_field))] + \
                 (["material_properties." + key for key, info in o.material_properties.model_fields.items() if new_field in key.upper() and (start_wildcard or key.upper().startswith(new_field)) and
                                (end_wildcard or key.upper().endswith(new_field))] if isinstance(o, Order) and o.material_properties is not None and isinstance(o.material_properties, BaseModel) else [])
        return fields
    return ()


def _processes_for_ids(process_arg: str|None, site: Site) -> list[Process]|None:
    if not process_arg:
        return None
    process_ids = [p for p in (p.strip() for p in process_arg.split(",")) if p != ""]
    return [_process_for_id(site.processes, p) for p in process_ids]


def _process_for_id(processes: list[Process], process_id0: str) -> Process:
    process_id = process_id0.upper()
    proc = next((p for p in processes if p.name_short.upper() == process_id), None)
    if proc is not None:
        return proc
    proc = next((p for p in processes if process_id in [s.upper() for s in p.synonyms]), None)
    if proc is None:
        raise Exception(f"Process not found: {process_id0}")
    return proc


def _plants_for_ids(equipment_arg: str|None, site: Site) -> list[Equipment]|None:
    if not equipment_arg:
        return None
    plant_ids = [p for p in (p.strip() for p in equipment_arg.split(",")) if p != ""]
    return [_plant_for_id(site.equipment, p) for p in plant_ids]

def _plant_for_id(plants: list[Equipment], plant_id0: str) -> Equipment:
    plant = next((p for p in plants if str(p.id) == plant_id0), None)
    if plant is not None:
        return plant
    plant_id = plant_id0.upper()
    plant = next((p for p in plants if (p.name_short is not None and p.name_short.upper() == plant_id) or (p.name is not None and p.name.upper() == plant_id)), None)
    if plant is None:
        raise Exception(f"Plant not found: {plant_id0}")
    return plant


def _print_field_name(f: str, wide:bool=False, values: list[Any] | None=None) -> str:
    if "." in f:
        dot = f.rindex(".")
        f = f[dot+1:]
    if wide and values is not None:
        max_length = max(len(str(v)) for v in values)
        f = ("{:" + str(max_length) + "s}").format(f)
    elif len(f) > 17:
        f = f[:15] + ".."
    return f

def _separator_for_field(f: str) -> str:
    return "".join(["-" for _ in f]) + "--"

def _value_for_col(order: Order, f: str, equipment: list[Equipment]|None=None) -> str|float|None:
    obj = order
    while "." in f and obj is not None:
        idx = f.index(".")
        first = f[:idx]
        f = f[idx+1:]
        obj = getattr(obj, first, None)
    obj = getattr(obj, f, None) if obj is not None else None
    if equipment is not None and (f == "current_equipment" or f == "allowed_equipment") and isinstance(obj, Sequence):
        obj = [next((f"{e.name_short} ({e.id})" for e in equipment if e.id == p and e.name_short is not None), str(p)) for p in obj]
    return obj

def _format_value(v: float|int|str|None, l: int, wide: bool=False) -> str:
    if v is None:
        return "".join([" " for _ in range(l+2)])
    if isinstance(v, Mapping) or isinstance(v, Sequence):
        v = str(v)
    if isinstance(v, str):
        return (" {:" + str(l) + "." + str(l) + "s} ").format(v) if not wide else (" {:" + str(l) + "s} ").format(v)
    if isinstance(v, int):
        return (" {:" + str(l) + "d} ").format(v)
    return (" {:" + str(l) + ".2f} ").format(v)  # if not wide else (" {:" + str(l) + "f} ").format(v)

def _print_planning(sol: ProductionPlanning, snapshot: Snapshot, site: Site, costs: CostProvider, filter_existent_properties: bool = True):
    equipment = next(iter(sol.equipment_status.keys()))
    plant = site.get_equipment(equipment, do_raise=True)
    relevant_fields: list[str] | None = costs.relevant_fields(plant)
    orders: list[Order] = [snapshot.get_order(assign.order, do_raise=True) for assign in sol.order_assignments.values()]
    if relevant_fields is not None:
        order_values = [[_value_for_col(o, f) for f in relevant_fields] for o in orders]
        cols_included: list[int] = [idx for idx in range(len(relevant_fields)) if any(
            ov[idx] is not None for ov in order_values)] if filter_existent_properties else list(
            range(len(relevant_fields)))
        relevant_fields = [f for idx, f in enumerate(relevant_fields) if idx in cols_included]
        field_names = [_print_field_name(f) for f in relevant_fields]
        order_values = [[v for idx, v in enumerate(ov) if idx in cols_included] for ov in order_values]
    else:
        order_values = []
        relevant_fields = []
        field_names = []
    fields = "|".join([f" {f} " for f in field_names]) + "|"
    print(f"| {'Order':9s} | {'Lot':11s} | {'Weight/t':7s} | {'Costs':6s} |" + fields)
    att = "|".join(_separator_for_field(f) for f in field_names) + "|"
    separator = "|-----------|-------------|----------|--------|" + att
    print(separator)
    previous_lot = ""
    previous_order = None
    for idx, assign in enumerate(sol.order_assignments.values()):
        order = orders[idx]
        cols = [_format_value(order_values[idx][field_idx], len(field_names[field_idx])) for field_idx, f in
                enumerate(relevant_fields)]
        trans_costs = costs.transition_costs(plant, previous_order, order) if previous_order is not None else 0
        if idx > 0 and previous_lot != assign.lot:
            print(separator)
        print(
            f"| {order.id[:9]:9s} | {assign.lot:11s} |  {order.actual_weight:6.2f}  | {trans_costs:6.2f} |" + "|".join(
                cols) + "|")
        previous_lot = assign.lot
        previous_order = order
    print(separator)
    print("Objectives", costs.objective_function(next(iter(sol.equipment_status.values()))))
    print()


def _print_orders(orders: list[Order]|list[Material], fields: list[str]|None, filter_existent_properties: bool=True, wide: bool=False, equipment: list[Equipment]|None=None):
    if fields is None:
        o1 = orders[0]
        fields = [key for key, info in o1.model_fields.items() if (key not in ["material_properties", "material_status", "lot", "lot_position", "id", "material_classes", "order"])] + \
                 (["material_properties." + key for key, info in o1.material_properties.model_fields.items()] if isinstance(o1, Order) and o1.material_properties is not None and isinstance(o1.material_properties, BaseModel) else [])
    order_values = [[_value_for_col(o, f, equipment=equipment) for f in fields] for o in orders]
    cols_included: list[int] = [idx for idx in range(len(fields)) if any(
        ov[idx] is not None for ov in order_values)] if filter_existent_properties else list(range(len(fields)))
    fields = [f for idx, f in enumerate(fields) if idx in cols_included]
    order_values = [[v for idx, v in enumerate(ov) if idx in cols_included] for ov in order_values]
    field_names = [_print_field_name(f, wide=wide, values=[ov[field_idx] for ov in order_values]) for field_idx, f in enumerate(fields)]
    field_str = "|".join([f" {f} " for f in field_names]) + "|"
    #print(f"| {'Order':9s} | {'Lot':11s} | {'Weight/t':7s} | {'Costs':6s} |" + fields)
    base_header = "Order" if isinstance(orders[0], Order) else "Material"
    print(f"| {base_header:9s} |" + field_str)
    att = "|".join(_separator_for_field(f) for f in field_names) + "|"
    separator = "|-----------|" + att
    print(separator)
    previous_lot = ""
    previous_order = None
    for idx, order in enumerate(orders):
        cols = [_format_value(order_values[idx][field_idx], len(field_names[field_idx]), wide=wide) for field_idx, f in enumerate(fields)]
        #trans_costs = costs.transition_costs(plant, previous_order, order) if previous_order is not None else 0
        #if idx > 0 and previous_lot != assign.lot:
        #    print(separator)
        print(f"| {order.id[:9]:9s} |" + "|".join(cols) + "|")
        #previous_lot = assign.lot
        previous_order = order
    print(separator)
    print()


def _print_obj(obj: LabeledItem|str|int|None=None) -> str:
    if isinstance(obj, str|int|float|None):
        return str(obj)
    if obj.name is not None:
        return obj.name
    if hasattr(obj, "name_short"):
        return getattr(obj, "name_short")
    if hasattr(obj, "id"):
        return getattr(obj, "id")
    return str(obj)


def transition_costs():
    parser = argparse.ArgumentParser(description="Orders can be filtered by explicitly specifying them (-o/--orders), filtering by process (-p/--process), " +
                                "by lot(s) (-lt/--lot), or by choosing all orders available at the equipment (default)")
    parser.add_argument("equipment", help="Id or name of the targeted equipment", type=str)
    parser.add_argument("-o", "--order", help="Select orders to be included. Separate multiple fields by \",\"", type=str, default=None)
    parser.add_argument("-p", "--process", help="Filter orders by current process stage", type=str, default=None)
    parser.add_argument("-lt", "--lot", help="Filter orders by lot(s)", type=str, default=None)
    parser.add_argument("-w", "--wide", help="Show wide cells, do not crop content", action="store_true")
    parser = _trafo_args(parser=parser)
    args = parser.parse_args()
    config = DynReActSrvConfig(config_provider=args.config_provider)
    plugins = Plugins(config)
    site = plugins.get_config_provider().site_config()
    plant_id = args.equipment.upper()
    plant = next(e for e in site.equipment if str(e.id) == plant_id or (e.name_short is not None and e.name_short.upper() == plant_id))
    snap: datetime | None = DatetimeUtils.parse_date(args.snapshot)
    snapshot: Snapshot = plugins.get_snapshot_provider().load(time=snap)
    orders = snapshot.orders
    orders_filtered: bool = False
    if args.order:
        order_ids = [o.strip() for o in args.order.split(",")]
        orders = [o for o in orders if o.id in order_ids]
        orders_filtered = True
    if args.process:
        process_ids = [p for p in (p.strip() for p in args.process.split(",")) if p != ""]
        processes = [_process_for_id(site.processes, p) for p in process_ids]
        process_codes: list[int] = [code for p in processes for code in p.process_ids]
        orders = [o for o in orders if any(p in process_codes for p in o.current_processes)]
        orders_filtered = True
    if args.lot:
        lot_ids = [l.strip().upper() for l in args.lot.split(",")]
        lots = [lot for lots in snapshot.lots.values() for lot in lots if lot.id.upper() in lot_ids]
        if len(lots) == 0:
            print(f"No matching lot found for {args.lot}")
            return
        order_ids = [o for lot in lots for o in lot.orders]
        orders = [o for o in orders if o.id in order_ids]
        orders_filtered = True
    if not orders_filtered:
        p_id = plant.id
        orders = [o for o in orders if o.current_equipment is not None and p_id in o.current_equipment]
    if len(orders) < 2:
        print("No matching orders found" if len(orders) == 0 else f"Only a single order found: {orders[0].id}")
        return
    costs = plugins.get_cost_provider()
    print("========================")
    print(f"Transition costs {plant.name_short or plant.name or plant.id}")
    print("========================")
    header_row = "|          |"
    separator  = "|----------|"
    order_separator = separator[2:]
    for order in orders:
        header_row += " {:7s} |".format(order.id)
        separator  += order_separator
    print(header_row)
    print(separator)
    for order in orders:
        row = "|  {:7s} |".format(order.id)
        row += "|".join(["{:8.1f} ".format(costs.transition_costs(plant, order, other)) for other in orders]) + "|"
        print(row)
    print(separator)


def aggregate_production():
    parser = argparse.ArgumentParser()
    parser.add_argument("-s", "--start", help="Start time", type=str, default=None)
    parser.add_argument("-e", "--end", help="End time", type=str, default=None)
    parser = _trafo_args(parser=parser, include_snapshot=False)
    args = parser.parse_args()
    start: datetime|None = DatetimeUtils.parse_date(args.start)
    end: datetime | None = DatetimeUtils.parse_date(args.end)
    config = DynReActSrvConfig(config_provider=args.config_provider, snapshot_provider=args.snapshot_provider,cost_provider=args.cost_provider)
    plugins = Plugins(config)
    site = plugins.get_config_provider().site_config()
    snaps_provider: SnapshotProvider = plugins.get_snapshot_provider()
    first_snapshot = snaps_provider.next(start or datetime(year=1900, month=1, day=1, tzinfo=timezone.utc))
    last_snapshot  = snaps_provider.previous(end or datetime(year=3000, month=1, day=1, tzinfo=timezone.utc))
    if last_snapshot <= first_snapshot:
        print(f"Single snapshot {first_snapshot} found, cannot aggregate")
        return
    previous = first_snapshot
    previous_obj = snaps_provider.load(time=previous)
    next = snaps_provider.next(previous + timedelta(minutes=3))
    agg_p = AggregationProviderImpl(site, snaps_provider, plugins.get_aggregation_persistence(), interval=None, interval_start=None)
    agg = AggregationInternal(aggregation_interval=(first_snapshot, last_snapshot), closed=True, last_snapshot=first_snapshot, total_weight=0)
    level = AggregationLevel(id="custom_interval", interval=last_snapshot-first_snapshot)
    while next is not None and (end is None or next <= end):
        next_obj: Snapshot = snaps_provider.load(time=next)
        agg = agg_p._update_aggregation_internal(agg, previous_obj, next_obj, level, is_closing=False)
        previous = next
        previous_obj = next_obj
        next = snaps_provider.next(next + timedelta(minutes=3))
        if next and next <= previous:  # XXX
            raise Exception("Snapshot timestamp does not increase")
    print(f"Total production {agg.total_weight:.1f}t in time interval {agg.aggregation_interval}")
    if args.details:
        for cat in site.material_categories:
            clas = ", ".join([f"{_print_obj(cl)}: {agg.material_weights.get(cl.id, 0):.1f}t" for cl in cat.classes])
            print(f"  Material {_print_obj(cat)}: {clas}")

def lot_sinks():
    config = DynReActSrvConfig()
    plugins = Plugins(config)
    sinks = list(plugins.get_lot_sinks().keys())
    print("Sinks:", sinks)

def transfer_lot():
    parser = argparse.ArgumentParser(description="Append a set of orders to a lot on the target system.")
    parser.add_argument("order", help="Select orders to be included. Separate multiple fields by \",\"", type=str, default=None)
    parser.add_argument("-l", "--lot", help="Select a lot to append to. A new one will be created if left empty", type=str, default=None)
    parser.add_argument("-sn", "--sink", help="Select a lot sink", type=str, default=None)
    parser.add_argument("-ln", "--lot-name", help="Select a new lot name; only relevant if the \"lot\" parameter is not set", type=str, default=None)
    parser.add_argument("-e", "--equipment", help="Equipment name or id", type=str, default=None)
    parser.add_argument("-c", "--comment", help="Optional comment for lot", type=str, default=None)
    parser = _trafo_args(parser=parser, include_snapshot=True)
    args = parser.parse_args()
    if args.lot is None and args.equipment is None:
        raise Exception("Must specify either \"equipment\" or \"lot\".")
    orders = [o for o in (o.strip() for o in args.order.split(",")) if len(o) > 0]
    config = DynReActSrvConfig(config_provider=args.config_provider, snapshot_provider=args.snapshot_provider, cost_provider=args.cost_provider)
    plugins = Plugins(config)
    site = plugins.get_config_provider().site_config()
    snaps_provider: SnapshotProvider = plugins.get_snapshot_provider()
    snap: datetime | None = DatetimeUtils.parse_date(args.snapshot)
    snapshot: Snapshot = snaps_provider.load(time=snap)
    existing_lot = next((l for lots in snapshot.lots.values() for l in lots if l.id == args.lot), None) if args.lot is not None else None
    equipment = (args.equipment if args.equipment is not None else str(existing_lot.equipment)).upper()
    plant = site.get_equipment(int(equipment)) if equipment.isnumeric() else next(e for e in site.equipment if e.name_short.upper() == equipment)
    if existing_lot is not None and existing_lot.equipment != plant.id:
        raise Exception(f"Plant id {plant.id} does not match lot equipment {existing_lot.equipment}")
    sinks: dict[str, LotSink] = plugins.get_lot_sinks()
    if len(sinks) == 0:
        raise Exception("No lot sinks configured, cannot transfer")
    selected_sink = args.sink if args.sink is not None else next(iter(sinks.keys()))
    lot_sink = sinks[selected_sink]
    name = args.lot if args.lot is not None else args.lot_name if args.lot_name is not None else "test"
    lot = Lot(id=name, equipment=plant.id, active=False, status=1, orders=orders, comment=args.comment)
    if args.lot is not None:
        return lot_sink.transfer_append(lot, orders[0], snapshot)
    else:
        return lot_sink.transfer_new(lot, snapshot, external_id=name)

def mtp_scenario():
    parser = argparse.ArgumentParser(description="Run a mid-term planning optimization benchmark scenario from a file.")
    parser.add_argument("-f", "--file", help="Path to scenario file. If not specified, the first valid scenario file in the scenarios directory will be used.", default=None)
    parser.add_argument("-d", "--dir", help="Base directory; only relevant if the file parameter is not specified. Default: \"scenarios\"", type=str, default="scenarios")
    parser.add_argument("-p", "--print", help="Print solution", action="store_true")
    args = parser.parse_args()
    scenario: MidTermScenario | None = _find_scenario(args.file, args.dir)
    if scenario is None:
        print(f"No scenario found in {args.file if args.file else args.dir}")
        return
    if args.print:
        print("Solution:")
        # TODO
    jsn = scenario.model_dump(exclude_none=True, exclude_unset=True)
    del jsn["snapshot"]
    del jsn["solution"]
    jsn["backlog"] = json.dumps(scenario.backlog)
    jsn["lots"] = {p: [json.dumps({l.id: l.orders}) for l in lots] for p, lots in scenario.solution.get_lots().items()}
    print(json.dumps(jsn, indent=4, default=str).replace("\"{\\\"", "{\"").replace("\\\"]}\"", "]}")
          .replace("\"[\"", "[\"").replace("\"]\"", "\"]").replace("\\\"", "\""))
    return scenario

def mtp_benchmark():
    parser = argparse.ArgumentParser(description="Run a mid-term planning optimization benchmark scenario from a file.")
    parser.add_argument("-f", "--file", help="Path to scenario file. If not specified, the first valid scenario file in the scenarios directory will be used.", default=None)
    parser.add_argument("-d", "--dir", help="Base directory; only relevant if the file parameter is not specified. Default: \"scenarios\"", type=str, default="scenarios")
    parser.add_argument("-s", "--store", help="Store result in file? Default: false", action="store_true")
    parser.add_argument("-i", "--iterations", help="Specify number of iterations. If negative (default) then a default number for this scenario will be used", type=int, default=-1)
    parser.add_argument("-cp", "--child-processes", help="Number of child processes to use. Uses default value if unset. Set to 1 to disable child processes.", type=int, default=None)
    parser.add_argument("-p", "--print", help="Print solution", action="store_true")
    args = parser.parse_args()
    scenario: MidTermScenario|None = _find_scenario(args.file, args.dir)
    if scenario is None:
        print(f"No scenario found in {args.file if args.file else args.dir}")
        return
    iterations = args.iterations
    if iterations < 0:
        iterations = scenario.iterations if scenario.iterations is not None else 100
    config: DynReActSrvConfig = DynReActSrvConfig(config_provider=scenario.config, cost_provider=scenario.costs)
    plugins = Plugins(config)
    cfg_provider = plugins.get_config_provider()
    costs = plugins.get_cost_provider()
    site: Site = cfg_provider.site_config()
    algo = plugins.get_lots_optimization()
    snapshot = scenario.snapshot
    targets = scenario.targets
    empty_assignments = {order: OrderAssignment(order=order, equipment=-1, lot="", lot_idx=-1) for order in scenario.backlog}
    previous_orders = scenario.solution.previous_orders if scenario.solution is not None else None
    initial_solution = costs.evaluate_order_assignments(targets.process, empty_assignments, targets, snapshot, previous_orders=previous_orders)
    optimizer = algo.create_instance(targets.process, snapshot, costs, targets=targets, initial_solution=initial_solution, parameters=scenario.parameters)
    optimizer_params = getattr(optimizer, "_params", None)              # XXX
    if args.child_processes is not None and args.child_processes > 0:
        setattr(optimizer_params, "NParallel", args.child_processes)    # XXX
    start_time_cpu = time.process_time()
    start_time_wall = time.time()
    start_datetime = DatetimeUtils.now()
    result = optimizer.run(max_iterations=iterations)
    end_time_cpu = time.process_time()
    end_time_wall = time.time()
    if args.print:
        print("Solution:")
        # TODO
    procs = getattr(optimizer_params, "NParallel", -1) if optimizer_params is not None else -1   # we take 0 to mean "unknown"
    if optimizer_params is not None and not isinstance(optimizer_params, dict):
        optimizer_params = optimizer_params.__dict__
    lots = result.best_solution.get_lots()
    benchmark = MidTermBenchmark(scenario=scenario.id, iterations=iterations, child_processes=procs, cpu_time=end_time_cpu-start_time_cpu,
                                 wall_time=end_time_wall-start_time_wall, objective=result.best_objective_value,
                                 timestamp=start_datetime, optimizer_id="tabu_search", optimization_parameters=optimizer_params, lots=lots)
    for_display: dict[str, typing.Any] = benchmark.model_dump()
    for_display["lots"] = {p: [json.dumps({l.id: l.orders}) for l in lots] for p, lots in benchmark.lots.items()}
    print(json.dumps(for_display, indent=4, default=str).replace("\"{\\\"", "{\"").replace("\\\"]}\"", "]}").replace("\\\"", "\""))
    return benchmark

def _find_scenario(file: str|None, base_dir: str) -> MidTermScenario|None:
    if file is not None:
        if os.path.isfile(file):
            files = [file]
        else:
            files = glob.glob(file)
        e = None
        for f in files:
            try:
                with open(f, mode="r") as file:
                    return MidTermScenario.model_validate_json(file.read())
            except:
                import sys
                e = sys.exc_info()  # https://nedbatchelder.com/blog/200711/rethrowing_exceptions_in_python.html
        if e is not None:
            raise e[1](None).with_traceback(e[2])
        return None
    else:
        return _find_scenario_recursive(base_dir)

def _find_scenario_recursive(base_dir: str) -> MidTermScenario|None:
    e = None
    for f in sorted(os.listdir(base_dir), key=lambda f: "__" + f if os.path.isfile(f) else f):  # dirs later than files
        full_path = os.path.join(base_dir, f)
        if os.path.isfile(full_path):
            try:
                with open(full_path, mode="r") as file:
                    return MidTermScenario.model_validate_json(file.read())
            except:
                import sys
                e = sys.exc_info()  # https://nedbatchelder.com/blog/200711/rethrowing_exceptions_in_python.html
        else:
            result = _find_scenario_recursive(full_path)
            if result is not None:
                return result
    if e is not None:  # TODO
        pass
    return None
