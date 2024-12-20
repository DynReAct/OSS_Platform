from datetime import datetime, timedelta, timezone
from typing import Iterator, Literal, Annotated

from dynreact.base.LotsOptimizer import LotsOptimizer
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Snapshot, Equipment, Site, Material, Order, EquipmentStatus, EquipmentDowntime, MaterialOrderData, \
    ProductionPlanning, ProductionTargets
from fastapi import FastAPI, HTTPException
from fastapi.params import Path, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import AliasChoices

from dynreact.app import config, state
from dynreact.auth.authentication import fastapi_authentication
from dynreact.service.model import EquipmentTransition, EquipmentTransitionStateful

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


@fastapi_app.get("/site",
                tags=["dynreact"],
                response_model_exclude_unset=True,
                response_model_exclude_none=True,
                summary="Get a list of process steps and plants configured for the site")
def site(username = username) -> Site:
    try:
        return state.get_site()
    except:
        raise HTTPException(status_code=502, detail="Information not available")


def _get_snapshot_plant(snapshot_id: str|datetime, plant_id: int) -> tuple[Snapshot, Equipment]:
    if isinstance(snapshot_id, str):
        snapshot_id = parse_datetime_str(snapshot_id)
    site0 = site()
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
def snapshots(start: str|datetime|None=Query(None, description="Optional start time.",
                                             examples=["now-2d", "2023-04-25T00:00Z"], openapi_examples={
                "now-2d": {"description": "Two days ago", "value": "now-2d"},
                "2023-04-25T00:00Z": {"description": "A specific timestamp", "value": "2023-04-25T00:00Z"},
            }),
            end: str|datetime|None=Query(None, description="Optional start time.",
                                             examples=["now", "2023-04-26T0:00Z"], openapi_examples={
                "now": {"description": "Current timestamp", "value": "now"},
                "2023-04-26T00:00Z": {"description": "A specific timestamp", "value": "2023-04-26T00:00Z"}
            }),
            sort: Literal["asc", "desc"] = "asc", limit: int=100,
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
    return result


@fastapi_app.get("/snapshots/{timestamp}",
                 tags=["dynreact"],
                 response_model_exclude_unset=True,
                 response_model_exclude_none=True,
                 summary="Get a specific snapshot; the one with largest timestamp <= the provided timestamp")
def snapshot(timestamp: str | datetime = Path(..., examples=["now", "now-1d", "2023-12-04T23:59Z"],
                                               openapi_examples={
                "now": {"description": "Get the most recent snapshot", "value": "now"},
                "now-1d": {"description": "Get yesterday's snapshot", "value": "now-1d"},
                "2023-04-25T23:59Z": {"description": "A specific timestamp", "value": "2023-04-25T23:59Z"},
            }), username = username) -> Snapshot:
    if isinstance(timestamp, str):
        timestamp = parse_datetime_str(timestamp)
    snapshot0: Snapshot = state.get_snapshot(timestamp)
    return snapshot0


@fastapi_app.get("/equipmentdowntimes",
                 tags=["dynreact"],
                 response_model_exclude_unset=True,
                 response_model_exclude_none=True,
                 summary="Get a specific snapshot; the one with largest timestamp <= the provided timestamp")
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


@fastapi_app.post("/costs/transitions",  # TODO
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
                 unit: Literal["material", "order"] = Query("order", description="Treat coils as basic unit or orders (default)?"),
                 planning_horizon: Annotated[timedelta|str|None, Query(openapi_examples={"2d": {"value": "2d", "description": "A duration of two days"}},
                     # not working, need to use planning_horizon
                    validation_alias=AliasChoices("planning-horizon", "planning_horizon", "planningHorizon"))] = timedelta(days=1),
                 # how to determine this? default throughput per plant; long term planning results; ...?
                 target_weight: Annotated[float|None, Query(description="Target weight. If not specified, it is determined from the snapshot")] = None,
                 current: str|None = Query(None, description="Order id or coil id; determined from snapshot by default"),
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
    if current is None and snapshot.inline_material is not None and equipment_id in snapshot.inline_material:
        order_coil_data: list[MaterialOrderData] = snapshot.inline_material[equipment_id]
        if len(order_coil_data) == 1:
            current = order_coil_data[0].material if order_coil_data[0].material is not None else order_coil_data[0].order
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
                                                      coil_based=coil_based, current=current_order, current_material=current_coils)


@fastapi_app.post("/costs/transitions-stateful",
                tags=["dynreact"],
                response_model_exclude_unset=True,
                response_model_exclude_none=True,
                summary="Invoke cost service for order to order or coil to coil transitions, taking into account " +
                        "global objectives and constraints.")
def target_function_update(transition: EquipmentTransitionStateful, username = username) -> EquipmentStatus:
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
    targets = ProductionTargets(process=plant.process, target_weight={plant.id: status.target_weight}, period=status.planning_period)
    optimizer: LotsOptimizer = state.get_lots_optimization().create_instance(plant.process, snapshot, state.get_cost_provider(),
                                                                    initial_solution=initial_solution, targets=targets)
    new_status: EquipmentStatus = optimizer.update_transition_costs(plant, current_order, next_order, status,
                                                                    snapshot, current_material=current_coil, next_material=next_coil)[0]
    return new_status


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
