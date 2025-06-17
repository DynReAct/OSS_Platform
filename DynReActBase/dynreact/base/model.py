"""
This module contains the basic domain model for the DynReAct production planning software.
It provides the definition of Equipment to be scheduled and Material as the unit of production,
as well as Orders (think production orders), which represent batches of Materials with common
properties.

The classes defined in this module are serializable and can be made accessible via a REST interface.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone, date
from typing import Any, TypeVar, Generic, Literal

from pydantic import BaseModel, Field, ConfigDict


class Model(BaseModel):
    # see https://github.com/pydantic/pydantic/pull/6563#issuecomment-2223251249
    model_config = ConfigDict(use_attribute_docstrings=True)


class LabeledItem(Model):
    name: str | None = None
    name_de: str | None = None
    description: str | None = None
    description_de: str | None = None


class ProcessInformation(Model):
    """
    An abstract class containing common information for process-related subclasses
    """
    throughput_capacity: float | None = None
    "unit: t/h"
    """
    FIXME in general this will be dependent on the material class
    """
    #throughput_capacity_mat: dict[str, float]|None = None  # key: material class id, value: throughput in ...


class Process(LabeledItem, ProcessInformation):
    name_short: str = Field(..., examples=["VA", "BZ"], min_length=1)
    "Short name uniquely identifying the process2."
    process_ids: list[int]
    "Internal process id(s)"
    synonyms: list[str]|None = Field(None, examples=["VEA"], min_length=1)
    "Alternative short names."
    next_steps: list[str]|None = None
    "Possible follow-up process steps."
    process_group: str|None = None
    "Id for a group of processes."


class Equipment(LabeledItem, ProcessInformation):
    """
    Equipment, such as a production plant.
    """

    id: int
    name_short: str
    process: str

    storage_in: str = None
    "Default storage location of material waiting to be processed by this equipment"
    storage_out: str = None
    "Default storage locations of material processed by this equipment"

    def get_equipment_name(self, idp: int):
        return self.name_short

    def get_equipment_id(self):
        return self.id


class MaterialConstraint(Model):

    excluded: list[str]
    "Material class ids"


# TODO how to deal with shared storages (common capacity, individual target levels)?
class Storage(LabeledItem):
    """
    Storage for materials.
    """
    name_short: str
    equipment: list[int]
    "Equipment served by this storage primarily."
    #secondary_plants: list[int]|None = Field(None, description="Plants served by this storage.")
    capacity_weight: float|None = None
    "Capacity in t."
    capacity_items: int|None = None
    "Capacity in items / material."
    target_filling_level: float|None = None  # TODO rather need a range
    "A number between 0 and 1"
    #target_filling_range: tuple[float, float]|None = Field(None, description="Numbers between 0 and 1")
    material_constraints: MaterialConstraint|None=None
    "Constraints on the type of material supported by this storage."


class EquipmentDowntime(Model):
    """
    @beta: currently not used
    """

    equipment: int
    start: datetime | None = None
    "Start of downtime, if known"
    end: datetime | None = None
    "End of downtime, if known. This is the scheduled end if in the future. TODO: do we need to model more uncertain situations?"
    reason: str|None = None


class EquipmentAvailability(Model):
    """
    @beta
    """
    equipment: int
    period: tuple[date, date]
    "The period this refers to, typically a month"
    daily_baseline: timedelta|None = None
    "The baseline availability, such as 24h or 1d. Default is 1d."
    deltas: dict[date, timedelta]|None = None
    "Deviations from the baseline per day. Defaults to 0 if a day is missing or the field is unset. Positive values mean extra time, negative values are outages etc."


PROPERTIES = TypeVar("PROPERTIES", bound=Model)  # Material-specific properties, not matching the MATERIAL parameter in the Order class


class Material(Model):
    model_config = ConfigDict(extra="allow")

    id: str
    "The material id"
    order: str
    weight: float
    "Material weight in t"
    order_position: int|None = None
    "@deprecated: 1-based index of material in order; note that this always refers to a lot"
    order_positions: dict[str, int]|None = None
    "1-based index of material in order for specific lots (keys: lot id)"
    current_equipment_name: str | None = None
    current_equipment: int | None = None
    current_storage: str | None = None
    "Note: this field is only relevant for short-term planning. The mid-term planning is based on current_equipment only."
    current_process: int
    "Process id, cf. field Process#process_ids"
    current_process_name: str|None = None
    "Process stage"
    properties: PROPERTIES|None = None
    "Material-specific properties."

    def get_current_equipment_name(self) -> str|None:
        return self.current_equipment_name
    
    def get_id(self) -> str:
        return self.id
    
    def get_order(self) -> str:
        return self.order


MATERIAL_PROPERTIES = TypeVar("MATERIAL_PROPERTIES", bound=Model)  # Material properties, such as dimensions at specific production facilities


class Order(Model, Generic[MATERIAL_PROPERTIES], arbitrary_types_allowed=True):
    id: str
    due_date: datetime|None = None
    "Due date"
    target_weight: float
    "Target weight in t"
    actual_weight: float
    "Sum of individual material weights in t"
    material_classes: dict[str, str] = {}
    "Keys: material category id, values: material class ids"
    allowed_equipment: list[int]   # TODO dict[process, list[int]]?
    current_equipment: list[int] | None = None
    # @deprecated
    current_processes: list[int]
    active_processes: dict[int, Literal["PENDING", "STARTED", "FINISHED"]]
    # FIXME a single order can be assigned to multiple orders at different process steps!
    # @deprecated
    lot: str|None = Field(None, deprecated=True)
    "DEPRECATED, use lots field instead"
    lots: dict[str, str]|None = None
    "Lot ids by process steps"
    # @deprecated
    lot_position: int|None = Field(None, deprecated=True)
    "DEPRECATED: use lot_positions instead. (1-based index of order in lot)"
    lot_positions: dict[str, int]|None = None
    "1-based index of order in lots, by process step"
    # FIXME this dict type with arbitrary_types_allowed is just a temporary workaround, need to find a better solution...
    material_properties: dict[str, Any] | MATERIAL_PROPERTIES
    "Use-case specific material characteristics."
    priority: int = 0
    "Order priority"

class Lot(Model):
    id: str
    equipment: int
    active: bool
    # TODO documentation
    status: int  # ?
    orders: list[str]
    processing_status: Literal["PENDING", "STARTED", "FINISHED"]|None = None
    comment: str|None = None


class MaterialOrderData(Model):
    order: str
    material: str | None = None

            
class PlanningData(Model):
    """
    This class holds the internal state of the optimization algorithm
    """
    model_config = ConfigDict(extra="allow", use_attribute_docstrings=True)

    target_fct: float = 0.0
    "Current value of the target function"
    # lots: list[list[str]] TODO?
    transition_costs: float = 0.0
    logistic_costs: float = 0.0
    lots_count: int = 0
    lot_weights: list[float] = []
    "Lot weights in tons."
    orders_count: int = 0
    delta_weight: float = 0.0
    "Deviation from target weight in t. Positive for missing tonnage."
    material_structure: dict[str, dict[str, float]]|None = None
    "Keep track of material classes. Outer key: category id, inner key: class id; special keys \"_sum\" represent the total/aggregated values"
    main_category: str|None = None
    "For nested structure planning, the main category."
    nested_material_structure: dict[str, dict[str, dict[str, float]]]|None = None
    """
    Keep track of nested material classes. Only used in case of nested structure targets. 
    Outermost key: class id for main category, middle key: sub category id, innermost key: class id; special keys \"_sum\" represent the total/aggregated values.
    """
    min_due_date: datetime|None = None
    assigned_priority: int = 0
    "sum priority of assigned orders"


P = TypeVar("P", bound=PlanningData)


class EquipmentStatus(Model, Generic[P]):

    targets: EquipmentProduction
    snapshot_id: datetime
    planning_period: tuple[datetime, datetime]
    current_order: str|None = None
    "Current order id"
    previous_order: str | None = None
    "Previous order id"
    current_material: list[str] | None = None
    "Material ids belonging to the currently processed order, if not the complete order"
    # @deprecated
    current: str|None = Field(None, deprecated=True)
    "DEPRECATED: use current_order and current_coils instead. (Either a coil id or order id)"
    # @deprecated
    previous: str|None = Field(None, deprecated=True)
    "DEPRECATED: use previous_order instead. (Either a coil id or order id)"
    #next: str|None = Field(None, description="Either a coil id or order id")
    planning: P|None = Field(None)  # FIXME should never be None?
    "Internal state of the optimization"


class ObjectiveFunction(Model, extra="allow"):
    """
    Note that this class may have use-case dependent extra fields
    """

    total_value: float
    "The overall objective function value"
    lots_count: float|None=None
    "Penalty for number of lots"
    transition_costs: float|None=None
    "Penalty for order to order transitions"
    logistic_costs: float|None=None
    "Penalty for necessary logistics"
    weight_deviation: float|None=None
    "Penalty for deviating from the targeted production size"
    lot_size_deviation: float|None = None
    "Penalty for deviating from the targeted lot sizes"
    structure_deviation: float|None = None
    "Penalty for deviating from the targeted material structure"
    priority_costs: float|None = None
    "Penalty for order priority"


class EquipmentProduction(Model):

    equipment: int
    total_weight: float
    lot_weight_range: tuple[float, float] | None = None
    "Weight restriction for lots in t"


SUM_MATERIAL: str = "_sum"
"A special entry in material class specifications that represents the aggregated/total value."


class ProductionTargets(Model):

    process: str
    target_weight: dict[int, EquipmentProduction]
    "Target production by equipment id"
    period: tuple[datetime, datetime]
    material_weights: dict[str, float|dict[str, float]] | None = None
    "Produced quantity by material class id, in t. This may be a nested model, in case a hierarchical structure is needed. The special value \"_sum\" represents the total weight."


class StorageLevel(Model):

    storage: str
    "Reference to the storage id"
    filling_level: float
    "Total filling level. Must be a value between 0 and 1."
    timestamp: datetime|None = None
    "The timestamp when the level was recorded or for which it is predicted."
    material_levels: dict[str, float]|None = None
    "Material-specific filling levels in the range 0 - 1, referring to the total storage capacity. Keys: material class ids."


class OrderAssignment(Model):  # base for SolutionElement
    """
    "Unassigned" is realized in terms of equipment=-1, lot="", lot_idx=-1
    """
    equipment: int
    order: str
    lot: str
    lot_idx: int


# TODO add lot weight targets to get_targets() return value
class ProductionPlanning(Model, Generic[P]):
    """
    The optimization needs to generate an object of this type
    """

    process: str
    order_assignments: dict[str, OrderAssignment]   # "sbest"
    "keys: order ids"
    equipment_status: dict[int, EquipmentStatus[P]]                  # "vbest"
    "keys: equipment ids"
    target_structure: dict[str, float|dict[str, float]] | None = None
    "Produced quantity by material class id, in t. This may be a nested model, in case a hierarchical structure is needed. Special key \"_sum\" represents the total/aggregated value."
    total_priority: int = 0
    "Sum priority orders"

    # TODO cache results?
    def get_lots(self) -> dict[int, list[Lot]]:
        """
        :return: dictionary with keys = equipment ids, values = lots
        """
        result: dict[int, dict[str, dict[int, str]]] = {}  # keys: equipment, lot_id, lot_idx, order
        for order, assignment in self.order_assignments.items():
            plant = assignment.equipment
            if plant < 0:
                continue
            if plant not in result:
                result[plant] = {}
            lot_id: str = assignment.lot
            lot_idx: int = assignment.lot_idx
            if lot_id not in result[plant]:
                result[plant][lot_id] = {}
            lot_orders: dict[int, str] = result[plant][lot_id]
            lot_orders[lot_idx] = order
        result_sorted: dict[int, list[Lot]] = {}
        for plant_id, lots in result.items():
            lots_sorted: list[str] = sorted(lots)
            plant_lots: list[Lot] = []
            for lot_id in lots_sorted:  # TODO test
                order_data: dict[int, str] = lots[lot_id]
                lot_indices: list[int] = sorted(order_data)
                lot = Lot(id=lot_id, equipment=plant_id, active=True, status=0, orders=[order_data[idx] for idx in lot_indices])
                plant_lots.append(lot)
            result_sorted[plant_id] = plant_lots
        return result_sorted

    def get_num_lots(self) -> int:
        return sum(status.planning.lots_count for status in self.equipment_status.values() if status.planning is not None)

    def get_targets(self) -> ProductionTargets:
        if len(self.equipment_status) == 0:
            return None  # ?
        period: tuple[datetime, datetime] = next(iter(self.equipment_status.values())).planning_period
        targets: dict[int, EquipmentProduction] = {plant: status.targets for plant, status in self.equipment_status.items()}
        return ProductionTargets(process=self.process, target_weight=targets, period=period, material_weights=self.target_structure)


# LTP WIP

class MaterialClass(Model):

    id: str
    "A unique material class id"
    name: str | None = None
    name_de: str | None = None
    category: str
    "A reference to the material category this class belongs to."
    description: str|None = None
    allowed_equipment: dict[str, list[int]] | None = None
    "Keys: process ids, values: equipment ids. "
    is_default: bool = False
    "A class can be assigned the default role within a material category."
    default_share: float|None = None
    mapping: str|None = None


class MaterialCategory(Model):

    id: str
    "A unique material category id"
    name: str|None = None
    name_de: str | None = None
    description: str|None = None
    classes: list[MaterialClass]
    """
    Mutually exclusive material classes. It is assumed
    that every material and order can be assigned to exactly one class within the category.
    """
    process_steps: list[str]|None = None
    "Optional list of process steps for which the category is potentially relevant in the mid-term planning."


class LotCreationStructureSettings(Model):
    """
    Defines a hierarchy for structure categories in the mid term planning;
    """
    primary_category: str
    "Reference to a MaterialCategory"
    primary_classes: list[str]
    "References to the MaterialClasses in primary_category.classes. For the time being only a single entry is supported."


class LotCreationOrderBacklogSettings(Model):
    default_select_predecessors_lot: list[str]|None=None
    "A list of process steps at which scheduled orders are usually included in the order backlog for lot creation"
    default_select_predecessors_all: list[str]|None=None
    "A list of process steps at which all orders (scheduled or not) are usually included in the order backlog for lot creation"


class ProcessLotCreationSettings(Model):
    plannable: bool|None = None
    "Default: true"
    structure: LotCreationStructureSettings|None=None
    order_backlog: LotCreationOrderBacklogSettings|None=None


class LotCreationSettings(Model):
    processes: dict[str, ProcessLotCreationSettings]
    "Settings per process step"


class Site(LabeledItem):
    processes: list[Process]
    equipment: list[Equipment]
    storages: list[Storage]
    material_categories: list[MaterialCategory]
    logistic_costs: dict[int, dict[int, float]]|None = None
    """
    Logistic costs for transfer of a complete order(?) from one plant to another (only within a single process stage, not considering
    transfer costs between processes)
    """
    #structure_planning: dict[str, StructurePlanningSettings]|None = None
    lot_creation: LotCreationSettings|None=None


    def get_process(self, process: str, do_raise: bool=False) -> Process|None:
        if process is None:
            return None
        proc = next((p for p in self.processes if p.name_short == process or p.synonyms is not None and process in p.synonyms), None)
        if proc is None and do_raise:
            raise Exception("Process not found: " + str(process))
        return proc

    def get_process_by_id(self, process_id: int, do_raise: bool=False) -> Process|None:
        if process_id is None:
            return None
        proc = next((p for p in self.processes if process_id in p.process_ids), None)
        if proc is None and do_raise:
            raise Exception("Process not found: " + str(process_id))
        return proc

    def get_equipment(self, plant_id: int, do_raise: bool=False) -> Equipment|None:
        if plant_id is None:
            return None
        plant = next((p for p in self.equipment if p.id == plant_id), None)
        if plant is None and do_raise:
            raise Exception("Plant not found: " + str(plant_id))
        return plant

    def get_equipment_by_name(self, plant_name: str, do_raise: bool=False) -> Equipment|None:
        if plant_name is None:
            return None
        plant = next((p for p in self.equipment if p.name_short == plant_name), None)
        if plant is None and do_raise:
            raise Exception("Plant not found by name: " + str(plant_name))
        return plant

    def get_process_equipment(self, process: str) -> list[Equipment]:
        return [p for p in self.equipment if p.process == process]

    def get_storage(self, storage: str, do_raise: bool=False) -> Storage|None:
        if storage is None:
            return None
        stg = next((s for s in self.storages if s.name_short == storage), None)
        if stg is None and do_raise:
            raise Exception("Storage not found " + str(storage))
        return stg

# Some changes in methods made by JOM / UPM)
    def get_process_all_equipment(self) -> list[Equipment]:
        return [p for p in self.equipment]


# Some changes in methods made by JOM / UPM)
class Snapshot(Model, Generic[MATERIAL_PROPERTIES]):
    timestamp: datetime
    "The timestamp serves as the unique snapshot id"
    orders: list[Order[MATERIAL_PROPERTIES]]
    material: list[Material]
    inline_material: dict[int, list[MaterialOrderData]]
    "Material ids currently being processed. Keys: plant ids, values: list of materials references."
    lots: dict[int, list[Lot]] = Field(..., examples=[{1: [{"id": "PLANT1.01", "equipment": 1, "active": True, "status": 1, "orders": ["1", "2", "3"]}]}])
    "Lots by plant ids. Keys: plant id, values: Lots"

    def get_order(self, order_id: str, do_raise: bool=False) -> Order[MATERIAL_PROPERTIES]|None:
        order = next((o for o in self.orders if o.id == order_id), None)
        if order is None and do_raise:
            raise Exception("Order " + str(order_id) + " not found")
        return order

    def get_material(self, material_id: str, do_raise: bool=False) -> Material | None:
        material = next((c for c in self.material if c.id == material_id), None)
        if material is None and do_raise:
            raise Exception("Material " + str(material_id) + " not found")
        return material

    def get_order_lot(self, site: Site, order_id: str, process: str) -> Lot|None:
        if self.lots is None:
            return None
        plant_ids: list[int] = [p.id for p in site.get_process_equipment(process)]
        for plant in plant_ids:
            if plant not in self.lots:
                continue
            lots: list[Lot] = self.lots[plant]
            lot: Lot|None = next((l for l in lots if order_id in l.orders), None)
            if lot is not None:
                return lot
        return None

    def get_material_equipment(self, site: Site, equipment_name: str, storage:str, assigned: int=-1) -> list[str]:
        if assigned < 0:
            return([coil.id for coil in self.material if \
                        equipment_name in [site.get_equipment(ieq).name_short \
                                for ieq in self.get_order(coil.order).allowed_equipment] \
                        and coil.current_storage == storage and \
                        coil.current_equipment is None])
        else:
            return([coil.id for coil in self.material if \
                        equipment_name in [site.get_equipment(ieq).name_short \
                                for ieq in self.get_order(coil.order).allowed_equipment] \
                            and coil.current_storage == storage and \
                                coil.current_equipment is not None and \
                                coil.current_equipment_name != equipment_name])

    def get_orders_equipment(self, site: Site, equipment_name: str, \
                             storage:str, assigned:int=-1) -> list[str]:
        """
        Get a list of orders when all the materials in the order have as 
        current_eqipment_name equal to tje equipment_name.

        :param site: The site containing plant details.
        :param equipment_name: targeted the name of the equipment.
        :param storage: Useless since the latest input from BFI (2025-02-25).
        :param assigned: Useless and kept because of OSS_Plantform compatiiity 
        :return: A list of order IDs representing the selected orders.
        """
        # Modified by JOM 2025-02-24
        # For RAS there is not current_equipment involving Not assigned Materials.
        # Then, assigned is useless and code gets simplified.
        # if assigned < 0:
        # else:
        #     return(list(set([coil.order for coil in self.material if \
        #                     equipment_name in [site.get_equipment(ieq).name_short \
        #                         for ieq in self.get_order(coil.order).allowed_equipment] \
        #                     and coil.current_storage == storage and \
        #                         coil.current_equipment is not None and \
        #                         coil.current_equipment_name != equipment_name] )) )
        #
        # Retrieve a list of orders based on current equipment name
        unique_orders = {coil.order for coil in self.material 
                        if coil.current_equipment_name == site.get_equipment_by_name(\
                            equipment_name).name_short}
        result_list = []
        for order in unique_orders:
            belongs_to_equipment = all(
                coil.current_equipment_name == equipment_name 
                for coil in self.material if coil.order == order
            )
            if belongs_to_equipment:
                result_list.append(order)

        return result_list
    #
    def get_material_selected_orders(self, orders: list[str], plant_names: list[str], \
                                    site: Site) -> list[str]:
        """
        Get a list of selected materials (coils) based on the specified orders and plant names.
        Since the requirement from RAS a single coil represents the whole order.
        Therefore, only one coil/material is extracted from each order.
        ** Storage constraints were removed from BFI 2025-02-22, then site param is useless
        ** coil.current_equipment_name in plant_names  was removed from the selection if,
        enabling orders from other equipments. Then plant_names is useless as well

        :param orders: A list of order IDs to filter.
        :param plant_names: A list of plant names to filter.
        :param site: The site containing plant details.
        :return: A list of coil IDs representing the selected orders (one coil.id per order).
        """
        #
        # Diccionario para almacenar solo un coil.id por coil.order
        selected_coils = {}
        for coil in self.material:
            if coil.order in orders:
                if coil.order not in selected_coils:
                    selected_coils[coil.order] = coil.id
        return list(selected_coils.values())


class LongTermTargets(Model):
    """
    Long term production targets for different product categories, as input for the long-term
    planning component.
    The source of this could be user input, an order backlog, etc.
    """
    source: str|None = None
    "Identifier specifying the source of the long-term targets."
    comment: str|None = None
    "Optional description"
    period: tuple[datetime, datetime]
    production_targets: dict[str, float]
    """
    Production targets for the planning period by material class. Note that the material classes are not disjoint, 
    only those belonging to a single material category are. Keys: material class ids, values: tons
    """
    total_production: float
    "Total production target in tons."


class MidTermTargets(LongTermTargets):
    """
    Production targets assigned to shorter periods such as days or shifts.
    Note: this class extends LongTermTargets in order to retain information about its source.
    """
    scheduler: str|None = None
    "Identifier specifying the source of the mid-term targets."
    sub_periods: list[tuple[datetime, datetime]]
    """
    A chronological list of non-overlapping time intervals within the larger planning period,
    typically corresponding to production shifts.
    """
    production_sub_targets: dict[str, list[ProductionTargets]]
    "Production targets for the planning sub periods. Keys: process ids, values: list of production targets, covering all planning sub periods chronologically."


class AggregatedMaterial(Model):
    total_weight: float
    material_weights: dict[str, float] | None = None


class AggregatedProduction(AggregatedMaterial):
    """
    total_weight refers to the total production in the time interval (finished material), and
    material_weights to finished material by material class id in the time interval
    """
    aggregation_interval: tuple[datetime, datetime]
    "The aggregation interval"
    closed: bool = True
    "Indicated whether the aggregation result is final or still subject to change in the future (interval in the past or still ongoing)"


class AggregatedStorageContent(Model):

    content_by_storage: dict[str, AggregatedMaterial]
    content_by_process: dict[str, AggregatedMaterial]
    content_by_equipment: dict[int, AggregatedMaterial]


class ServiceHealth(Model):

    status: int
    "0: ok"
    running_since: datetime|None=None

