import argparse
from datetime import timedelta
from enum import Enum

from dynreact.app_config import DynReActSrvConfig
from dynreact.base.CostProvider import CostProvider
from dynreact.base.LotsOptimizer import LotsOptimizationState
from dynreact.base.model import Snapshot, Material, OrderAssignment, Order, EquipmentProduction, ProductionTargets, \
    ProductionPlanning, ObjectiveFunction, Site
from dynreact.plugins import Plugins


class Boolean(str, Enum):
    true = "true"
    false = "false"


def _trafo_args(parser: argparse.ArgumentParser|None=None) -> argparse.ArgumentParser:
    parser = parser if parser is not None else argparse.ArgumentParser()
    parser.add_argument("-cp", "--config-provider", help="Config provider id, such as", type=str, default=None)
    parser.add_argument("-snp", "--snapshot-provider", help="Snapshot provider id, such as", type=str, default=None)
    parser.add_argument("-cost", "--cost-provider", help="Cost provider id, such as", type=str, default=None)
    parser.add_argument("-d", "--details", help="Show details", action="store_true")
    return parser


def analyze_snapshot():
    parser = _trafo_args()
    args = parser.parse_args()
    config = DynReActSrvConfig(config_provider=args.config_provider, snapshot_provider=args.snapshot_provider)
    plugins = Plugins(config)
    snapshot: Snapshot = plugins.get_snapshot_provider().load()
    print(f"Snapshot {snapshot.timestamp}, orders: {len(snapshot.orders)}, materials: {len(snapshot.material)}, lots: {sum(len(l) for l in snapshot.lots.values())}")


def analyze_lots():
    parser = _trafo_args()
    parser.add_argument("-e", "--equipment", help="Plant name or plant id", type=str, default=None)
    parser.add_argument("-p", "--process", help="Process(es), separated by \",\"", type=str, default=None)
    parser.add_argument("-so", "--skip-orders", help="Skip orders", action="store_true")
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
    snapshot: Snapshot = plugins.get_snapshot_provider().load()
    plant_ids = list(snapshot.lots.keys())
    processes = [p.name_short for p in site.processes]
    plants = [site.get_equipment(p, do_raise=True) for p in plant_ids]
    plants.sort(key=lambda p: (processes.index(p.process) if p.process in processes else -1, p.id))
    orders = {o.id: o for o in snapshot.orders}
    material: dict[str, list[Material]] = {}  # keys: order ids
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
            lot_orders = [orders.get(o) for o in lot.orders]
            total_weight = sum(o.actual_weight for o in lot_orders)
            if lot.active:
                aggregated_tons += total_weight
            if status is not None and lot.status != status:
                continue
            if active is not None and str(lot.active).lower() != active:
                continue
            materials = [mat for order in lot_orders for mat in material.get(order.id)]
            lot_line = f"    Lot {lot.id}, active={lot.active}, status={lot.status}, weight={total_weight:7.2f}t, order cnt={len(lot.orders):2}, material cnt={len(materials):2}"
            if not skip_comment and lot.comment is not None:
                lot_line += f", comment={lot.comment}"
            if not args.skip_orders:
                lot_line += f", orders= {lot.orders}"
            lines.append(lot_line)
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
    snapshot: Snapshot = plugins.get_snapshot_provider().load()
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
    parser.add_argument("-it", "--iterations", help="Specify number of optimization iterations", type=int, default=100)
    parser.add_argument("-se", "--start-existing", help="If the flag is set and an existing lot is specified via \"--lot\", then the algorithm will start from the configuration of the existing lot, otherwise it will start from an empty configuration", action="store_true")
    parser = _trafo_args(parser=parser)
    args = parser.parse_args()
    config = DynReActSrvConfig(config_provider=args.config_provider, snapshot_provider=args.snapshot_provider, cost_provider=args.cost_provider)

    plugins = Plugins(config)
    site = plugins.get_config_provider().site_config()
    snapshot: Snapshot = plugins.get_snapshot_provider().load()
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
    order_assignments = {o: OrderAssignment(equipment=-1, order=o, lot="", lot_idx=-1) for o in orders.keys()} if not args.start_existing or args.lot is None else \
        {o: OrderAssignment(equipment=equipment_id, order=o, lot=lot.id, lot_idx=idx+1) for idx, o in enumerate(orders.keys())}
    period = (snapshot.timestamp, snapshot.timestamp + timedelta(days=1))
    targets = ProductionTargets(process=equipment.process, period=period, target_weight={equipment_id: EquipmentProduction(equipment=equipment_id, total_weight=tons)})
    # initial solution
    empty_start = costs.evaluate_order_assignments(equipment.process, order_assignments, targets, snapshot)
    algo = plugins.get_lots_optimization()
    optimization = algo.create_instance(equipment.process, snapshot, costs, targets, initial_solution=empty_start)
    # TODO in separate thread, interruptable?
    state: LotsOptimizationState = optimization.run(max_iterations=args.iterations)
    sol = state.best_solution
    _print_planning(sol, snapshot, site, costs)


def _print_field_name(f: str) -> str:
    if "." in f:
        dot = f.rindex(".")
        f = f[dot+1:]
    if len(f) > 17:
        f = f[:15] + ".."
    return f

def _separator_for_field(f: str) -> str:
    return "".join(["-" for _ in f]) + "--"

def _value_for_col(order: Order, f: str) -> str|float|None:
    obj = order
    while "." in f and obj is not None:
        idx = f.index(".")
        first = f[:idx]
        f = f[idx+1:]
        obj = getattr(obj, first, None)
    return getattr(obj, f, None) if obj is not None else None

def _format_value(v: float|int|str|None, l: int) -> str:
    if v is None:
        return "".join([" " for _ in range(l+2)])
    if isinstance(v, str):
        return (" {:" + str(l) + "s} ").format(v)
    if isinstance(v, int):
        return (" {:" + str(l) + "d} ").format(v)
    return (" {:" + str(l) + ".2f} ").format(v)

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
