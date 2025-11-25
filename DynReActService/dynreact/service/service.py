import random
import sys
import threading
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Iterator, Literal, Annotated, Sequence

from starlette.responses import PlainTextResponse

from dynreact.base.LotsOptimizer import LotsOptimizer, LotsOptimizationAlgo, OptimizationStatistics
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.MaterialAggregation import MaterialAggregation
from dynreact.base.model import Snapshot, Equipment, Site, Material, Order, EquipmentStatus, EquipmentDowntime, \
    MaterialOrderData, ProductionPlanning, ProductionTargets, EquipmentProduction, AggregatedStorageContent, \
    AggregatedMaterial, Histogram, ServiceMetrics, PrimitiveMetric, PlannedWorkingShift, Lot
from fastapi import FastAPI, HTTPException, Response
from fastapi.params import Path, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AliasChoices

from dynreact.app import config, state
from dynreact.auth.authentication import fastapi_authentication
from dynreact.service.model import EquipmentTransition, EquipmentTransitionStateful, LotsOptimizationInput, \
    LotsOptimizationResults, TransitionInfo, MaterialTransfer, LongTermPlanningResults
from dynreact.service.optim_listener import LotsOptimizationListener


@asynccontextmanager
async def lifespan(app: FastAPI):
    # start aggregation
    aggregation = state.get_aggregation_provider()
    aggregation.start()
    yield
    try:
        aggregation.stop()
    except:
        pass

fastapi_app = FastAPI(
    title="DynReAct production planning service",
    description="DynReAct mid-term production planning service for steel plants.",
    version="0.0.1",
    contact={
        "name": "VDEh-Betriebsforschungsinstitut (BFI)",
        "url": "https://www.bfi.de",
        "email": "info@bfi.de"
    },
    openapi_tags=[{"name": "dynreact"}],
    lifespan=lifespan if config.aggregation else None
)
if config.cors:
    fastapi_app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

username = fastapi_authentication(config)
start = time.time()


@fastapi_app.get("/site",
                tags=["dynreact"],
                response_model_exclude_unset=True,
                response_model_exclude_none=True,
                summary="Get a list of process steps and plants configured for the site")
def site(response: Response, username = username) -> Site:
    try:
        response.headers["Cache-Control"] = "max-age=6000"  # 100 minutes
        return state.get_site()
    except:
        raise HTTPException(status_code=502, detail="Information not available")


def _get_snapshot_plant(snapshot_id: str|datetime, plant_id: int) -> tuple[Snapshot, Equipment]:
    if isinstance(snapshot_id, str):
        snapshot_id = parse_datetime_str(snapshot_id)
    site0 = state.get_site()
    snapshot: Snapshot = state.get_snapshot(snapshot_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No such snapshot: " + DatetimeUtils.format(snapshot_id))
    plant = site0.get_equipment(plant_id)
    if plant is None:
        raise HTTPException(status_code=404, detail="No such plant: " + str(plant_id))
    return snapshot, plant


@fastapi_app.get("/snapshots",
                 tags=["dynreact"],
                 response_model_exclude_unset=True,
                 response_model_exclude_none=True,
                 summary="Get a list of available snapshots identified by their timestamps")
def snapshots(response: Response, start: str|datetime|None=Query(None, description="Optional start time.",
                                             examples=["now-2d", "2023-04-25T00:00Z"], openapi_examples={
                "now-2d": {"description": "Two days ago", "value": "now-2d"},
                "2023-04-25T00:00Z": {"description": "A specific timestamp", "value": "2023-04-25T00:00Z"},
            }),
            end: str|datetime|None=Query(None, description="Optional start time.",
                                             examples=["now", "2023-04-26T0:00Z"], openapi_examples={
                "now": {"description": "Current timestamp", "value": "now"},
                "2023-04-26T00:00Z": {"description": "A specific timestamp", "value": "2023-04-26T00:00Z"}
            }),
            sort: Literal["asc", "desc"] = "asc",
            limit: int=100,
            username = username) -> list[datetime]:
    if isinstance(start, str):
        start = parse_datetime_str(start)
    if isinstance(end, str):
        end = parse_datetime_str(end)
    if start is None:
        start = datetime.fromtimestamp(0, tz=timezone.utc)
    if end is None:
        end = datetime.fromtimestamp(9_999_999_999, tz=timezone.utc)
    result = []
    it: Iterator[datetime] = state.get_snapshot_provider().snapshots(start_time=start, end_time=end, order=sort)
    for idx in range(0, limit):
        try:
            result.append(next(it))
        except StopIteration:
            break
    response.headers["Cache-Control"] = "max-age=60"  # 1 minute...
    return result


@fastapi_app.get("/snapshots/{timestamp}/aggregation",
                 tags=["dynreact"],
                 summary="Get a specific snapshot; the one with largest timestamp <= the provided timestamp")
def aggregate_material(response: Response, timestamp: str | datetime = Path(..., examples=["now", "now-1d", "2023-12-04T23:59Z"],
                                               openapi_examples={
                "now": {"description": "Get the most recent snapshot", "value": "now"},
                "now-1d": {"description": "Get yesterday's snapshot", "value": "now-1d"},
                "2023-04-25T23:59Z": {"description": "A specific timestamp", "value": "2023-04-25T23:59Z"},
            }),
            level: Literal["plant","storage","process"] = Query("plant", description="The aggregation level."),
            username = username) -> dict[int|str, AggregatedMaterial]:
    is_relative_timestamp: bool = isinstance(timestamp, str) and timestamp.startswith("now")
    if isinstance(timestamp, str):
        timestamp = parse_datetime_str(timestamp)
    # snapshot0: Snapshot = state.get_snapshot(timestamp)
    stg: AggregatedStorageContent = state.get_aggregation_provider().aggregated_storage_content(timestamp)
    if not is_relative_timestamp:
        response.headers["Cache-Control"] = "max-age=604800"  # 1 week
    if level == "storage":
        return stg.content_by_storage
    elif level == "process":
        return stg.content_by_process
    return stg.content_by_equipment

    #snapshot0: Snapshot = state.get_snapshot(timestamp)
    #agg = MaterialAggregation(state.get_site(), state.get_snapshot_provider())
    #agg_by_plants = agg.aggregate_categories_by_plant(snapshot0)
    #if not is_relative_timestamp:
    #    response.headers["Cache-Control"] = "max-age=604800"  # 1 week
    #if level == "storage":
    #    return agg.aggregate_by_storage(agg_by_plants)
    #elif level == "process":
    #    return agg.aggregate_by_process(agg_by_plants)
    #return agg_by_plants


@fastapi_app.get("/snapshots/{timestamp}",
                 tags=["dynreact"],
                 response_model_exclude_unset=True,
                 response_model_exclude_none=True,
                 summary="Get a specific snapshot; the one with largest timestamp <= the provided timestamp")
def snapshot(response: Response, timestamp: str | datetime = Path(..., examples=["now", "now-1d", "2023-12-04T23:59Z"],
                                               openapi_examples={
                "now": {"description": "Get the most recent snapshot", "value": "now"},
                "now-1d": {"description": "Get yesterday's snapshot", "value": "now-1d"},
                "2023-04-25T23:59Z": {"description": "A specific timestamp", "value": "2023-04-25T23:59Z"},
            }), username = username) -> Snapshot:
    is_relative_timestamp: bool = isinstance(timestamp, str) and timestamp.startswith("now")
    if isinstance(timestamp, str):
        timestamp = parse_datetime_str(timestamp)
    snapshot0: Snapshot = state.get_snapshot(timestamp)
    if not is_relative_timestamp:
        response.headers["Cache-Control"] = "max-age=604800"  # 1 week
    else:
        response.headers["Cache-Control"] = "max-age=60"  # 1 minute
    return snapshot0

@fastapi_app.get("/lots",
                 tags=["dynreact"],
                 response_model_exclude_unset=True,
                 response_model_exclude_none=True,
                 summary="Get lots from a specific snapshot")
def lots(response: Response, snapshot: str|datetime|None = Query(None, description="Specify the snapshot id. If not set, the latest snapshot will be used", examples=[None, "now", "now-1d", "2023-12-04T23:59Z"],
                                               openapi_examples={
                "unset": {"description": "No snapshot timestamp specified, will use latest", "value": None},
                "now": {"description": "Get the most recent snapshot", "value": "now"},
                "now-1d": {"description": "Get yesterday's snapshot", "value": "now-1d"},
                "2023-04-25T23:59Z": {"description": "A specific timestamp", "value": "2023-04-25T23:59Z"},
            }), equipment: str|int|None = Query(None, description="Filter by equipment", examples=[None, 1, "PKL01"], openapi_examples={
                "unset": {"description": "No equipment filter", "value": None},
                "1": {"description": "Specify equipment by equipment id", "value": 1},
                "PKL01": {"description": "Specify equipment by name", "value": "PKL01"}
            }), process: str|int|None = Query(None, description="Filter by process stage", examples=[None, "PKL", 1], openapi_examples={
                "unset": {"description": "No process filter", "value": None},
                "PKL": {"description": "Specify process by name", "value": "PKL"},
                "1": {"description": "Specify process by process id", "value": 1},
            }), status: list[int]|None = Query(None, description="Lot status. Keys: 1: created; 2: blocked; 3: released; 4: in progress; 5: completed.",
                    examples=[None, 1, 2, 3, 4, 5], openapi_examples={
                "unset": {"description": "No status filter", "value": None},
                "1": {"description": "Created", "value": [1]},
            }), active: bool|None = Query(None, description="Filter on active/inactive lots"),
            reschedulable: bool | None = Query(None, description="Filter on reschedulable lots"),
            complete: bool | None = Query(None, description="Filter on complete lots, i.e. those ready to be processed"),
            username = username) -> list[Lot]:
    is_absolute_timestamp: bool = isinstance(snapshot, str) and not snapshot.startswith("now")
    if isinstance(snapshot, str):
        snapshot = None if snapshot == "" else parse_datetime_str(snapshot)
    snap = state.get_snapshot(snapshot)
    if equipment is not None:
        equipment = None if equipment == "" else _get_equipment_id(equipment)
    if process is not None:
        process = None if process == "" else _get_process_name(process)
    all_lots = snap.lots
    if equipment is not None:
        lots = all_lots.get(equipment, [])
    elif process is not None:
        equipments: list[int] = [p.id for p in state.get_site().get_process_equipment(process)]
        lots = [lot for equip, eq_lots in all_lots.items() if equip in equipments for lot in eq_lots]
    else:
        lots = [lot for eq_lots in all_lots.values() for lot in eq_lots]
    if is_absolute_timestamp:
        response.headers["Cache-Control"] = "max-age=604800"  # 1 week
    else:
        response.headers["Cache-Control"] = "max-age=60"  # 1 minute
    if status is not None:
        lots = [l for l in lots if l.status in status]
    if active is not None:
        lots = [l for l in lots if l.active == active]
    sp = state.get_snapshot_provider()
    if reschedulable is not None:
        lots = [l for l in lots if sp.is_lot_reschedulable(l) == reschedulable]
    if complete is not None:
        lots = [l for l in lots if sp.is_lot_complete(l) == complete]
    return lots

@fastapi_app.get("/planning-horizon",
                 tags=["dynreact"],
                 response_model_exclude_unset=True,
                 response_model_exclude_none=True,
                 summary="Get the planning horizon by equipment id based on scheduled lots")
def planning_horizon(response: Response, snapshot: str|datetime|None = Query(None, description="Specify the snapshot id. If not set, the latest snapshot will be used", examples=[None, "now", "now-1d", "2023-12-04T23:59Z"],
                                               openapi_examples={
                "unset": {"description": "No snapshot timestamp specified, will use latest", "value": None},
                "now": {"description": "Get the most recent snapshot", "value": "now"},
                "now-1d": {"description": "Get yesterday's snapshot", "value": "now-1d"},
                "2023-04-25T23:59Z": {"description": "A specific timestamp", "value": "2023-04-25T23:59Z"},
            }), equipment: list[str|int]|None = Query(None, description="Filter by equipment", examples=[None, 1, "PKL01"], openapi_examples={
                "unset": {"description": "No equipment filter", "value": None},
                "1": {"description": "Specify equipment by equipment id", "value": [1]},
                "PKL01": {"description": "Specify equipment by name", "value": ["PKL01"]}
            }), process: str|int|None = Query(None, description="Filter by process stage", examples=[None, "PKL", 1], openapi_examples={
                "unset": {"description": "No process filter", "value": None},
                "PKL": {"description": "Specify process by name", "value": "PKL"},
                "1": {"description": "Specify process by process id", "value": 1},
            }),
            username = username) -> dict[int|str, datetime]:
    is_absolute_timestamp: bool = isinstance(snapshot, str) and not snapshot.startswith("now")
    if isinstance(snapshot, str):
        snapshot = None if snapshot == "" else parse_datetime_str(snapshot)
    snap = state.get_snapshot(snapshot)
    if equipment is not None:
        equipment = [_get_equipment_id(e) for e in equipment]   # convert to all ints
    if process is not None:
        process = None if process == "" else _get_process_name(process)
    if process is not None:
        plants = state.get_site().get_process_equipment(process, do_raise=True)
        equipment = [p.id for p in plants if equipment is None or p.id in equipment]
    if equipment is None:
        equipment = [e.id for e in state.get_site().equipment]
    horizons = {e: state.get_snapshot_provider().planning_horizon(snap, e) for e in equipment}
    if is_absolute_timestamp:
        response.headers["Cache-Control"] = "max-age=604800"  # 1 week
    else:
        response.headers["Cache-Control"] = "max-age=60"  # 1 minute
    return {"snapshot": snap.timestamp}|horizons


@fastapi_app.get("/equipmentdowntimes",
                 tags=["dynreact"],
                 deprecated=True,
                 response_model_exclude_unset=True,
                 response_model_exclude_none=True,
                 summary="Get plant downtimes. Deprecated, use planned-shifts instead.")
def plant_downtimes(
        start:  str|datetime|None = Query(None, description="Start time. If neither start nor end time are specified, "
                        + "start is set to now", examples=["now", "now+1d", "2023-04-25T00:00Z"], openapi_examples={
                "now": {"description": "Get current downtimes", "value": "now"},
                "now+1d": {"description": "Get yesterday's snapshot", "value": "now+2d"},
                "2023-04-25T00:00Z": {"description": "A specific timestamp", "value": "2023-04-25T00:00Z"},
            }),
        end:  str|datetime|None = Query(None, description="End time. If neither start nor end time are specified, "
                        + "end is set to now+60d", examples=["now+2d", "2023-04-27T00:00Z"], openapi_examples={
                "now+2d": {"description": "Two days from now", "value": "now+2d"},
                "2023-04-27T00:00Z": {"description": "A specific timestamp", "value": "2023-04-27T00:00Z"},
            }),
        process: str|None = Query(None, description="Process step id"),
        plant: list[int]|None = Query(None, description="Plant id"),
        sort: Literal["asc", "desc"] = "asc",
        limit: int = 250,
        username = username) -> list[EquipmentDowntime]:
    if isinstance(start, str):
        start = parse_datetime_str(start)
    if isinstance(end, str):
        end = parse_datetime_str(end)
    if start is None:
        start = DatetimeUtils.now()
    if end is None:
        end = start + timedelta(days=60)
    downtimes: Iterator[EquipmentDowntime] = state.get_downtime_provider().downtimes(start, end, plant=plant, process=process, order=sort)
    result = []
    for idx in range(limit):
        try:
            result.append(next(downtimes))
        except StopIteration:
            break
    return result


@fastapi_app.post("/costs/transitions",
                tags=["dynreact"],
                response_model_exclude_unset=True,
                response_model_exclude_none=True,
                summary="Invoke cost service for order to order or coil to coil transitions. Global objectives and constraints are ignored.")
def transition_cost(transition: EquipmentTransition, username = username) -> float:
    snapshot, plant = _get_snapshot_plant(transition.snapshot_id, transition.equipment)
    current_coil: Material | None = None
    next_coil: Material | None = None
    current_order: Order|None = snapshot.get_order(transition.current_order)
    next_order: Order|None = snapshot.get_order(transition.next_order)
    if current_order is None:
        raise HTTPException(status_code=404, detail="Current order " + str(transition.current_order) + " not found")
    if next_order is None:
        raise HTTPException(status_code=404, detail="Next order " + str(transition.next_order) + " not found")
    if transition.next_material is not None:
        current_coil = snapshot.get_material(transition.current_material)
        next_coil = snapshot.get_material(transition.next_material)
        if next_coil is None:
            raise HTTPException(status_code=404, detail="Coil " + str(transition.next_material) + " not found")
        if current_coil is None:
            raise HTTPException(status_code=404, detail="Current coil " + str(transition.current_material) + " not found or not provided")
    costs: float = state.get_cost_provider().transition_costs(plant, current_order, next_order, current_material=current_coil, next_material=next_coil)
    return costs


@fastapi_app.post("/costs/logistics",
                tags=["dynreact"],
                response_model_exclude_unset=True,
                response_model_exclude_none=True,
                summary="Query logistics costs for transfer of material from one equipment to the other.")
def logistics_cost(transfer_data: MaterialTransfer, username = username) -> float:
    snapshot, plant = _get_snapshot_plant(transfer_data.snapshot_id, transfer_data.new_equipment)
    order: Order|None = snapshot.get_order(transfer_data.order)
    if order is None:
        raise HTTPException(status_code=404, detail=f"Current order {transfer_data.order} not found")
    coil = None
    if transfer_data.material is not None:
        coil = snapshot.get_material(transfer_data.material)
        if coil is None:
            raise HTTPException(status_code=404, detail=f"Current coil {transfer_data.material} not found or not provided")
    costs: float = state.get_cost_provider().logistic_costs(new_equipment=plant, order=order, material=coil)
    return costs

@fastapi_app.get("/costs/status/{equipment_id}/{snapshot_timestamp}",
                tags=["dynreact"],
                response_model_exclude_unset=True,
                response_model_exclude_none=True,
                summary="Get the initial plant status for an optimization task.")
def plant_status(equipment_id: int, snapshot_timestamp: datetime | str = Path(..., examples=["now", "now-1d"],
                                                                              openapi_examples={
                "now": {"description": "Get the most recent snapshot", "value": "now"},
                "now-1d": {"description": "Get yesterday's snapshot", "value": "now-1d"},
                "2023-12-04T23:59Z": {"description": "A specific timestamp", "value": "2023-12-04T23:59Z"},
            }),
                 unit: Literal["material", "order"] = Query("order", description="Treat materials as basic unit or orders (default)?"),
                 planning_horizon: Annotated[timedelta|str|None, Query(openapi_examples={"2d": {"value": "2d", "description": "A duration of two days"}},
                     # not working, need to use planning_horizon
                    validation_alias=AliasChoices("planning-horizon", "planning_horizon", "planningHorizon"))] = timedelta(days=1),
                 # how to determine this? default throughput per plant; long term planning results; ...?
                 target_weight: Annotated[float|None, Query(description="Target weight. If not specified, it is determined from the snapshot")] = None,
                 current: str|None = Query(None, description="Order id or material id; determined from snapshot by default"),
                 username = username) -> EquipmentStatus:
    coil_based: bool = unit.lower().startswith("material")
    if planning_horizon is None:
        planning_horizon = timedelta(days=1)
    if type(planning_horizon) != timedelta:
        planning_horizon = parse_duration(planning_horizon)
    snapshot, plant = _get_snapshot_plant(snapshot_timestamp, equipment_id)
    current_order=None
    current_coil=None
    interval = [snapshot.timestamp, snapshot.timestamp + planning_horizon]
    if current is None and coil_based and snapshot.inline_material is not None and equipment_id in snapshot.inline_material:
        order_coil_data: list[MaterialOrderData] = snapshot.inline_material[equipment_id]
        if len(order_coil_data) > 0:
            current = order_coil_data[-1].material if order_coil_data[-1].material is not None else order_coil_data[-1].order
    if current is not None:
        current_coil = snapshot.get_material(current)
        if current_coil is not None:
            current_order = snapshot.get_order(current_coil.order, do_raise=True)
        else:
            current_order = snapshot.get_order(current, do_raise=True)
    current_coils = [current_coil] if current_coil is not None else []
    if target_weight is None:
        target_weights = state.get_snapshot_provider().target_weights_from_snapshot(snapshot, plant.process)
        target_weight = target_weights.get(plant.id, 0)
    return state.get_cost_provider().equipment_status(snapshot, plant, planning_period=interval, target_weight=target_weight,
                                                      material_based=coil_based, current=current_order, current_material=current_coils)


@fastapi_app.post("/costs/transitions-stateful",
                tags=["dynreact"],
                response_model_exclude_unset=True,
                response_model_exclude_none=True,
                summary="Invoke cost service for order to order or coil to coil transitions, taking into account " +
                        "global objectives and constraints.")
def target_function_update(transition: EquipmentTransitionStateful, username = username) -> TransitionInfo:
    if transition.current_order == "":
        transition.current_order = None
    if transition.equipment_status.current_order == "":
        transition.equipment_status.current_order = None
    if transition.current_order != transition.equipment_status.current_order:
        raise HTTPException(status_code=400, detail="Current transition id does not match plant status current id: "
                                                    + str(transition.current_order) + " - " + str(transition.equipment_status.current_order))
    snapshot, plant = _get_snapshot_plant(transition.snapshot_id, transition.equipment)
    current_coil: Material | None = None
    next_coil: Material | None = None
    current_order: Order | None = snapshot.get_order(transition.current_order)
    next_order: Order | None = snapshot.get_order(transition.next_order)
    if next_order is None or current_order is None:
        raise HTTPException(status_code=404, detail="Current or next order " + str(transition.current_order) + "/" + str(transition.next_order) + " not found")
    if transition.next_material is not None:
        current_coil = snapshot.get_material(transition.current_material)
        next_coil = snapshot.get_material(transition.next_material)
        if current_coil is None or next_coil is None:
            raise HTTPException(status_code=404, detail="Current/Next coil " + str(transition.current_material) + "/" + str(transition.next_material) + " not found")
    # this is actually allowed at the beginning
    #if current_order is None and current_coil is None:
    #    raise HTTPException(status_code=404, detail="Current coil or order " + str(transition.current) + " not found")
    status = transition.equipment_status
    initial_solution = ProductionPlanning(process=plant.process, equipment_status={plant.id: status}, order_assignments={})
    targets = ProductionTargets(process=plant.process, target_weight={plant.id: status.targets},
                                period=status.planning_period)
    optimizer: LotsOptimizer = state.get_lots_optimization().create_instance(plant.process, snapshot, state.get_cost_provider(),
                                                                    initial_solution=initial_solution, targets=targets)
    new_status, new_objective = optimizer.update_transition_costs(plant, current_order, next_order, status,
                                                                    snapshot, current_material=current_coil, next_material=next_coil)
    return TransitionInfo(status=new_status, costs=new_objective)


lots_optimization: tuple[int, LotsOptimizationListener]|None = None


@fastapi_app.post("/lots/optimization",
                tags=["dynreact"],
                status_code=202,
                summary="Invoke mid term service/lots creation.")
def run_lots_optimization(data: LotsOptimizationInput, username = username) -> int:
    global lots_optimization
    if lots_optimization is not None and not lots_optimization[1].is_done():
        raise HTTPException(status_code=..., detail="There is an ongoing optimization which needs to be stopped before starting a new one.")
    optimizer = state.get_lots_optimization()
    snapshot: Snapshot = state.get_snapshot(data.snapshot)
    if snapshot is None:
        raise HTTPException(status_code=404, detail=f"Snapshot {data.snapshot} not found")
    instance = optimizer.create_instance(data.targets.process, snapshot, state.get_cost_provider(),
                targets=data.targets, initial_solution=data.initial_solution, min_due_date=data.min_due_date,
                orders=data.orders)
    instance_id: int = random.randint(0, sys.maxsize)
    listener = LotsOptimizationListener(data.snapshot, data.targets, data.orders, data.trace_results)
    instance.add_listener(listener)
    thread = threading.Thread(target=lambda: instance.run(), name=f"Service-LotsOptimization-{instance_id}")
    thread.run()
    lots_optimization = (instance_id, instance)
    return instance_id


@fastapi_app.delete("/lots/optimization/{optimization_id}",
                tags=["dynreact"],
                summary="Stop the lots optimization. Returns true if the optimization was stopped, false if it was not running")
def stop_lots_optimization(optimization_id: int, username = username) -> bool:
    global lots_optimization
    if lots_optimization is None or lots_optimization[0] != optimization_id:
        return False
    was_done = lots_optimization[1].is_done()
    lots_optimization[1].stop()
    return not was_done


@fastapi_app.get("/lots/optimization/{optimization_id}",
                tags=["dynreact"],
                summary="Query the optimization result. Returns intermediate results while not done.")
def get_lots_optimization_results(optimization_id: int, username = username) -> LotsOptimizationResults:
    global lots_optimization
    if lots_optimization is None or lots_optimization[0] != optimization_id:
        raise HTTPException(status_code=404, detail=f"No such optimization id: {optimization_id}")
    listener = lots_optimization[1]
    return listener.get_results()


@fastapi_app.get("/longtermplanning",
                tags=["dynreact"],
                summary="Long term planning results with start times in the specified period")
def get_longtermplanning_results(
        start:  str|datetime|None = Query(None, description="Start time. If neither start nor end time are specified, "
                        + "start is set to now.", examples=["now", "now-31d", "2023-04-25T00:00Z"], openapi_examples={
                "now": {"description": "Get next month's planning", "value": "now"},
                "now-31d": {"description": "Get last month's planning", "value": "now-31d"},
                "2023-04-25T00:00Z": {"description": "A specific timestamp", "value": "2023-04-25T00:00Z"},
            }),
        end:  str|datetime|None = Query(None, description="End time. If neither start nor end time are specified, "
                        + "end is set to now+31d", examples=["now", "now+31d", "2023-04-27T00:00Z"], openapi_examples={
                "now": {"description": "Get last month's planning", "value": "now"},
                "now+31d": {"description": "A month ahead of now", "value": "now+31d"},
                "2023-04-27T00:00Z": {"description": "A specific timestamp", "value": "2023-04-27T00:00Z"},
            }),
        sort: Literal["asc", "desc"] = "asc",
        limit: int|None=10,
        username = username) -> dict[str, list[str]]:
    if isinstance(start, str):
        start = parse_datetime_str(start)
    if isinstance(end, str):
        end = parse_datetime_str(end)
    results_ctrl = state.get_results_persistence()
    start_times = results_ctrl.start_times_ltp(start=start, end=end, sort=sort, limit=limit)
    return {DatetimeUtils.format(time): results_ctrl.solutions_ltp(time) for time in start_times}


@fastapi_app.get("/longtermplanning/{start}/{solution_id}",
                tags=["dynreact"],
                summary="Long term planning results with start times in the specified period")
def get_longtermplanning_result(
        start:  str|datetime = Path(..., description="Start time. ",
                examples=["now", "now-31d", "2023-04-25T00:00Z"], openapi_examples={
                    "now": {"description": "Get next month's planning", "value": "now"},
                    "now-31d": {"description": "Get last month's planning", "value": "now-31d"},
                    "2023-04-25T00:00Z": {"description": "A specific timestamp", "value": "2023-04-25T00:00Z"},
                }),
        solution_id: str = Path(..., description="Unique solution id"), username = username) -> LongTermPlanningResults|None:
    if isinstance(start, str):
        start = parse_datetime_str(start)
    results_ctrl = state.get_results_persistence()
    targets, levels = results_ctrl.load_ltp(start, solution_id)
    return LongTermPlanningResults(targets=targets, storage_levels=levels)

@fastapi_app.get("/planned-shifts",
                tags=["dynreact"],
                summary="Get working shifts by equipment id")
def planned_shifts(
        process: str|None = Query(None, description="Process steps to be included. Equipment for all processes will be included if not specified."),
        equipment: list[int|str]|None = Query(None, description="Equipment ids to be included. All equipments will be included in the response if not specified (unless the process filter is set)"),
        start: str|datetime|None = Query(None, description="Start time. If neither start nor end time are specified, "
                                     + "start is set to now.",  examples=["now", "now-31d", "2023-04-25T00:00Z"], openapi_examples={
                "now": {"description": "Get next month's planning", "value": "now"},
                "now-31d": {"description": "Get last month's planning", "value": "now-31d"},
                "2023-04-25T00:00Z": {"description": "A specific timestamp", "value": "2023-04-25T00:00Z"},
            }),
        end: str|datetime|None = Query(None, description="End time, optional.", examples=["now+31d", "2023-04-27T00:00Z"], openapi_examples={
                "now+31d": {"description": "A month ahead of now", "value": "now+31d"},
                "2023-04-27T00:00Z": {"description": "A specific timestamp", "value": "2023-04-27T00:00Z"},
            }),
        limit: int=100,
        username = username) -> dict[int, Sequence[PlannedWorkingShift]]:
    if isinstance(start, str):
        start = parse_datetime_str(start)
    if isinstance(end, str):
        end = parse_datetime_str(end)
    if start is None:
        if end is None:
            start = DatetimeUtils.now()
        else:
            start = end.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            if end-start < timedelta(days=2):
                start = (start - timedelta(days=5)).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    if equipment is not None:
        equipment = [_get_equipment_id(e) for e in equipment]
    if process:
        plants = state.get_site().get_process_equipment(process)
        if len(plants) == 0:
            raise HTTPException(404, f"No equipment found for process {process}")
        equipment_p = [p.id for p in plants if equipment is None or p.id in equipment]
        equipment = equipment_p
    return state.get_shifts_provider().load_all(start, end=end, limit=limit, equipments=equipment)


@fastapi_app.get("/metrics",
                tags=["dynreact"],
                summary="Prometheus metrics for the DynReAct service")
def metrics(username = username) -> PlainTextResponse:
    result = ""
    service_prefix = "dynreact_"
    result += f"{service_prefix}uptime_seconds {int(time.time()-start)}\n"
    result += _print_service_metrics(state.get_lots_optimization().metrics())
    result += _print_service_metrics(state.get_snapshot_provider().metrics())
    lot_sinks = state.get_lot_sinks(if_exists=True)
    if lot_sinks is not None:
        for sink in lot_sinks.values():
            result += _print_service_metrics(sink.metrics())
    return PlainTextResponse(result)

def _print_service_metrics(metrics: ServiceMetrics) -> str:
    prefix = "dynreact_" + metrics.service_id + "_"
    result = ""
    for metric in metrics.metrics:
        if isinstance(metric, Histogram):
            result += _print_histogram(metric, prefix)
        elif isinstance(metric, PrimitiveMetric):
            labels_agg_str = "" if metric.labels is None or len(metric.labels) == 0 else "{" + ",".join([k + "=\"" + v + "\"" for k, v in metric.labels.items()]) + "}"
            result += f"{prefix + metric.id}{labels_agg_str} {metric.value}\n"
    return result

def _print_histogram(histogram: Histogram, prefix: str) -> str:
    result = ""
    if len(histogram.data) == 0:
        return result
    labels = histogram.labels
    metric = prefix + histogram.id
    data = histogram.data
    labels_str = "" if labels is None or len(labels) == 0 else ",".join([k + "=\"" + v + "\"" for k, v in labels.items()]) + ","
    for bucket in histogram.buckets:
        result += f"{metric}_bucket{{{labels_str}le=\"{bucket}\"}} {sum(1 for d in data if d <= bucket)}\n"
    if histogram.include_infinity:
        result += f"{metric}_bucket{{{labels_str}le=\"+Inf\"}} {len(data)}\n"
    labels_agg_str = "" if labels is None or len(labels) == 0 else "{" + ",".join([k + "=\"" + v + "\"" for k, v in labels.items()]) + "}"
    result += f"{metric}_count{labels_agg_str} {len(data)}\n"
    result += f"{metric}_sum{labels_agg_str} {sum(data)}\n"
    return result


def parse_datetime_str(dt: str) -> datetime:
    attempt = DatetimeUtils.parse_date(dt)
    if attempt is not None:
        return attempt
    dt = dt.strip()
    if not dt.lower().startswith("now"):
        raise HTTPException(status_code=400, detail="Invalid date time " + str(dt))
    now = DatetimeUtils.now()
    if dt.lower() == "now":
        return now
    is_minus: bool = False
    cnt: int = 0
    for char in dt[len("now"):]:
        cnt += 1
        if char == " ":
            continue
        if char == "+":
            break
        if char == "-":
            is_minus = True
            break
        raise HTTPException(status_code=400, detail="Invalid date time " + str(dt))
    dur: timedelta = parse_duration(dt[len("now")+cnt:])
    return now - dur if is_minus else now + dur


def parse_duration(d: str) -> timedelta:
    num: str = ""
    unit: str = ""
    for char in d:
        if len(unit) > 0:
            raise HTTPException(status_code=400, detail="Invalid date time " + d)
        if not char.isdigit():
            unit = char
        else:
            num += char
    if len(num) == 0 or len(unit) == 0:
        raise HTTPException(status_code=400, detail="Invalid date time " + d)
    digit = int(num)
    if unit == "d" or unit == "D":
        return timedelta(days=digit)
    if unit == "M":
        return timedelta(days=digit * 30)
    if unit == "y" or unit == "Y":
        return timedelta(days=digit * 365)
    if unit == "w" or unit == "W":
        return timedelta(weeks=digit)
    if unit == "h" or unit == "H":
        return timedelta(hours=digit)
    if unit == "m":
        return timedelta(minutes=digit)
    if unit == "s" or unit == "S":
        return timedelta(seconds=digit)
    raise HTTPException(status_code=400, detail="Unknown time unit " + unit)

def _get_equipment_id(equipment: int|str) -> int:
    if isinstance(equipment, str):
        try:
            equipment = int(equipment)
        except ValueError:
            equipment_obj = state.get_site().get_equipment_by_name(equipment, do_raise=False)
            if equipment_obj is None:
                raise HTTPException(status_code=404, detail=f"Equipment not found: {equipment}")
            equipment = equipment_obj.id
    return equipment


def _get_process_name(process: int|str) -> str:
    if isinstance(process, int|float):
        proc = next((p for p in state.get_site().processes if process in p.process_ids), None)
    else:
        process = process.upper()
        proc = next((p for p in state.get_site().processes if p.name_short.upper() == process or (p.synonyms is not None and any(process == s.upper() for s in p.synonyms))), None)
    if proc is None:
        raise HTTPException(status_code=404, detail=f"Process not found: {process}")
    return proc.name_short

