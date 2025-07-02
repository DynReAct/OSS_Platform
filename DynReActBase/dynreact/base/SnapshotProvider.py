"""
The SnapshotProvider module defines the SnapshotProvider interface. The FileSnapshotProvider implementation
is provided as part of the software, which can parse CSV files. Custom implementations can be used
for more complex use cases.
"""

import enum
from datetime import datetime, timezone
from typing import Iterator, Literal, Iterable, Any

from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Snapshot, Site, Lot, Process, Material, Order, MaterialCategory, MaterialClass


# Note: requires Python >= 3.11
class OrderInitMethod(enum.StrEnum):
    """
    Specifies different methods to initialize the order backlog for the planning optimization.
    TODO implement new specifiers.
    """

    CURRENT_PLANNING = "current_planning"
    """
    Include orders from planned lots of the active snapshot as input for the planning optimization.
    This can be further refined by means of the OMIT_CURRENT_LOT and OMIT_SUBSEQUENT_LOT specifiers. 
    It is incompatible with OMIT_PLANNED_LOTS; 
    if CURRENT_PLANNING and OMIT_PLANNED_LOTS are both active then an error is thrown.
    """
    INACTIVE_LOTS = "inactive_lots"
    """
    Include orders from inactive lots of the currently active snapshot as input for the planning optimization.
    Active by default.
    """
    OMIT_CURRENT_LOT = "omit_current_lot"
    """
    Used in conjunction with CURRENT_PLANNING to exclude the currently processed lot.
    Has no effect if CURRENT_PLANNING is not active. 
    Active by default. 
    """
    #OMIT_CURRENT_ORDER = "omit_current_order"  # Always active, does not make sense
    """
    Like OMIT_CURRENT_LOT, but only exclude orders currently being processed
    """
    OMIT_SUBSEQUENT_LOT = "omit_subsequent_lot"
    """
    Used in conjunction with CURRENT_PLANNING and OMIT_CURRENT_LOT to exclude the subsequent lot.
    Has no effect if CURRENT_PLANNING or OMIT_CURRENT_LOT are not active. 
    Inactive by default. 
    """
    OMIT_ACTIVE_LOTS = "omit_active_lots"
    """
    The opposite of CURRENT_PLANNING: ensure orders from currently planned lots are not added to the order backlog.
    Incompatible with CURRENT_PLANNING; if CURRENT_PLANNING and OMIT_ACTIVE_LOTS are both active an error is thrown.
    """
    OMIT_INACTIVE_LOTS = "omit_inactive_lots"
    """
    The opposite of INACTIVE_LOTS: ensure orders from current inactive lots are not added to the order backlog.
    Incompatible with INACTIVE_LOTS; if INACTIVE_LOTS and OMIT_INACTIVE_LOTS are both active an error is thrown.
    """
    OMIT_RELEASED_LOTS = "omit_released_lots"
    """
    Omit lots with status >= 3.
    """

    ACTIVE_PROCESS = "active_process"
    """
    Include all orders in the backlog whose active process matches the planning process. 
    """
    ACTIVE_PLANT = "active_plant"
    """
    Include all orders located at an applicable plant for the planning process stage. 
    """


class SnapshotProvider:
    """
    A snapshot provider loads snapshots of the current production status, e.g. from an MES.
    Implementation expected in module dynreact.snapshot.SnapshotProviderImpl
    """

    def __init__(self, url: str, site: Site):
        self._url = url
        self._site = site
        self._has_class_mapping: bool = any(cl.mapping is not None for cat in site.material_categories for cl in cat.classes)

    def store(self, snapshot: Snapshot, *args, **kwargs):
        """
        Optional method, may not be implemented
        """
        raise Exception("not implemented")

    def snapshots(self, start_time: datetime, end_time: datetime, order: Literal["asc", "desc"] = "asc") -> Iterator[datetime]:
        """
        Retrieve snapshot ids.

        Parameters:
            start_time:
            end_time:
            order:
        """
        raise Exception("not implemented")

    def size(self, start_time: datetime, end_time:datetime) -> int:
        """
        Retrieve estimated number of available snapshots in the specified time interval.

        Parameters:
            start_time:
            end_time:
        """
        return len([self.snapshots(start_time, end_time)])

    def previous(self, time: datetime|None=None) -> datetime|None:
        """
        Get the timestamp of the previous snapshot.

        Parameters:
            time:
        """
        if time is None:
            time = DatetimeUtils.now()
        try:
            return next(self.snapshots(start_time=datetime.fromtimestamp(0, tz=timezone.utc), end_time=time, order="desc"))
        except StopIteration:
            return None

    def next(self, time: datetime) -> datetime|None:
        """
        Get the id of the next snapshot

        Parameters:
            time:

        Returns:
            snapshot id
        """
        try:
            return next(self.snapshots(start_time=time, end_time=datetime(year=3000, month=1, day=1, tzinfo=timezone.utc), order="asc"))
        except StopIteration:
            return None

    def load(self, *args, time: datetime|None=None, **kwargs) -> Snapshot|None:
        """
        Load the snapshot for a specific timestamp.

        Parameters:
            time:

        Returns:
             the snapshot object, if there is a snapshot for the specified timestamp, else None.
        """
        raise Exception("not implemented")

    # tbd
    def current_snapshot_id(self) -> datetime:
        return self.previous()

    def is_lot_reschedulable(self, lot: Lot) -> bool:
        """
        This method is used to check if orders assigned to some lot may be rescheduled.
        It can be overwritten by subclasses; by default, lots with status <= 1 are considered reschedulable.
        :param lot:
        :return:
        """
        return lot.status <= 1

    def material_class_for_order(self, order: Order, category: MaterialCategory) -> MaterialClass|None:
        """
        Overwrite this method in derived class to provide a custom material class mapping
        :param order:
        :param category:
        :return:
        """
        if not self._has_class_mapping:
            raise Exception("Material class for order not implemented")
        for cl in category.classes:
            if not cl.mapping:
                continue
            field, operator, cond_value = SnapshotProvider._parse_expression(cl.mapping)
            if field is None:
                continue
            value = SnapshotProvider._get_field_value(order, field)
            if value is None:
                continue
            if isinstance(value, float):
                cond_value = float(cond_value)
            elif isinstance(value, bool):
                cond_value = bool(cond_value)
            if SnapshotProvider._check_expression(value, operator, cond_value):
                return cl
        return None

    @staticmethod
    def _get_field_value(order: Any, field: str):
        if order is None:
            return None
        if "." in field:
            first_dot = field.index(".")
            first_field = field[0:first_dot]
            last_fields = field[first_dot+1:]
            return SnapshotProvider._get_field_value(order.get(field) if isinstance(order, dict) else getattr(order, first_field, None), last_fields)
        return order.get(field) if isinstance(order, dict) else getattr(order, field, None)

    @staticmethod
    def _check_expression(actual_value: str|float|bool, operator: Literal["=", ">=", ">", "<", "<="], cond_value: str|float|bool):
        if operator == "=":
            return actual_value == cond_value
        if operator == ">":
            return actual_value > cond_value
        if operator == ">=":
            return actual_value >= cond_value
        if operator == "<":
            return actual_value < cond_value
        if operator == "<=":
            return actual_value <= cond_value
        raise Exception(f"Invalid operator {operator}")

    @staticmethod
    def _parse_expression(exp: str) -> tuple[str | None, Literal["=", ">=", ">", "<", "<="] | None, str | None]:
        operator = next((op for op in [">=", "<=", "=", ">", "<"] if op in exp), None)
        if operator is None:
            return None, None, None
        idx = exp.index(operator)
        return exp[0: idx].strip(), operator, exp[idx+len(operator):].strip()

    def order_plant_assignment_from_snapshot(self, snapshot: Snapshot, process: str, include_inactive_lots: bool=False) -> dict[str, int]:
        """
        :param snapshot:
        :param process:
        :return: keys: order ids, values: plant ids
        """
        result: dict[str, int] = {}
        for plant_id, lots in snapshot.lots.items():
            plant = next((p for p in self._site.equipment if p.plant_id == plant_id), None)
            if plant is None or plant.process != process:
                continue
            for lot in lots:
                if not include_inactive_lots and not lot.active:
                    continue
                for order in lot.orders:
                    result[order] = plant_id
        return result

    def target_weights_from_snapshot(self, snapshot: Snapshot, process: str, include_inactive_lots: bool=False) -> dict[int, float]:
        """
        :param snapshot:
        :param process:
        :return: keys: plant ids, values: target weights
        """
        target_weights: dict[int, float] = {}
        for plant in self._site.equipment:
            if plant.process != process:
                continue
            plant_id = plant.id
            if plant_id not in snapshot.lots:
                target_weights[plant_id] = 0
                continue
            order_ids = [order for lot in snapshot.lots[plant_id] for order in lot.orders if lot.active or include_inactive_lots]
            orders: dict[str, Order | None] = {order_id: next((o for o in snapshot.orders if o.id == order_id), None) for order_id in order_ids}
            none_orders = [order_id for order_id, order in orders.items() if order is None]
            if len(none_orders) > 0:
                # may happen for instance for dummies
                # raise Exception("A lot for plant " + str(plant_id) + " contains unknown orders " + str(none_orders))
                orders = {oid: order for oid, order in orders.items() if order is not None}
            total_weight = sum(o.target_weight for o in orders.values())
            target_weights[plant_id] = total_weight
        return target_weights

    def eligible_orders(self,
                        snapshot: Snapshot,
                        process: str,
                        planning_horizon: tuple[datetime, datetime],
                        method: OrderInitMethod|Iterable[OrderInitMethod]=(
                            OrderInitMethod.ACTIVE_PROCESS, 
                            OrderInitMethod.CURRENT_PLANNING,
                            OrderInitMethod.INACTIVE_LOTS,
                            OrderInitMethod.OMIT_CURRENT_LOT,
                            OrderInitMethod.OMIT_RELEASED_LOTS
                        ),
                        include_previous_processes_planned: list[str]|None = None,
                        include_previous_processes_all: list[str] | None = None,
                        ) -> list[str]:
        """
        Determine the orders eligible for planning/lot creation for a specific process.
        This method can be overridden in a derived implementation.
        TODO this is unfinished, will need more input data, such as predecessor stage planning, etc
        :param snapshot:
        :param process:
        :param planning_horizon:
        :param method:
            * current_planning: based on the lots already in the snapshot
            * active_process (default): based on the current process ids of the coils
            * active_plant: based on the current plant (location) of the coils
        :param include_previous_processes_planned: include all orders scheduled for the specified predecessor stages
        :param include_previous_processes_all: include all orders currently at the specified predecessor stages
        :return:
        """
        method = list(method) if isinstance(method, Iterable) else [method]
        if OrderInitMethod.CURRENT_PLANNING in method and OrderInitMethod.OMIT_ACTIVE_LOTS in method:
            raise ValueError("Cannot simultaneously include and exclude planned lots; "
                             "both CURRENT_PLANNING and OMIT_ACTIVE_LOTS order init specifiers are set.")
        if OrderInitMethod.INACTIVE_LOTS in method and OrderInitMethod.OMIT_INACTIVE_LOTS in method:
            raise ValueError("Cannot simultaneously include and exclude inactive lots; "
                             "both INACTIVE_LOTS and OMIT_INACTIVE_LOTS order init specifiers are set.")
        eligible_plants: list[int] = [p.id for p in self._site.get_process_equipment(process)]
        proc: Process = self._site.get_process(process, do_raise=True)
        applicable_orders0: set[str] = set()
        current_planning_included: bool = OrderInitMethod.CURRENT_PLANNING in method
        inactive_lots_included: bool = OrderInitMethod.INACTIVE_LOTS in method
        if current_planning_included or inactive_lots_included:
            # active: bool = m == OrderInitMethod.CURRENT_PLANNING
            current_and_inactive: bool = current_planning_included and inactive_lots_included
            omit_first: bool = OrderInitMethod.OMIT_CURRENT_LOT in method   # and active
            # TODO not implemented
            omit_next = omit_first and OrderInitMethod.OMIT_SUBSEQUENT_LOT in method
            eligible_lots: Iterator[list[Lot]] = (lots for plant, lots in snapshot.lots.items() if plant in eligible_plants)
            lots_for_removal: Iterator[Lot] = (lot for lots in eligible_lots for lot in lots if (current_and_inactive or lot.active == current_planning_included))
            if omit_first:
                lots_for_removal = (lot for lot in lots_for_removal if lot.processing_status is None or lot.processing_status == "PENDING")
            applicable_orders0.update(order for lot in lots_for_removal for order in lot.orders)
        if OrderInitMethod.ACTIVE_PLANT in method:
            # TODO filter out coils in process?
            applicable_coils: list[Material] = [coil for coil in snapshot.material if coil.current_equipment is not None and coil.current_equipment in eligible_plants]
            applicable_orders0.update(coil.order for coil in applicable_coils)
        if OrderInitMethod.ACTIVE_PROCESS in method:
            proc_ids: list[int] = proc.process_ids
            for o in snapshot.orders:
                if o.id in applicable_orders0:
                    continue
                applicable_proc_ids = [p_id for p_id, status in o.active_processes.items() if p_id in proc_ids and status == "PENDING"]
                if len(applicable_proc_ids) == 0:
                    continue
                applicable_orders0.add(o.id)
        add_prev_all = include_previous_processes_all is not None and len(include_previous_processes_all) > 0
        add_prev_lot = include_previous_processes_planned is not None and len(include_previous_processes_planned) > 0
        if add_prev_all and add_prev_lot and len(include_previous_processes_planned) == len(include_previous_processes_all) and \
                    all(p in include_previous_processes_all for p in include_previous_processes_planned):
            add_prev_lot = False
        if add_prev_all or add_prev_lot:
            prev_eligible_lots: list[Lot] = []
            if not add_prev_all:
                proc_ids_all = []
            else:
                procs_all: list[Process] = [self._site.get_process(p, do_raise=True) for p in include_previous_processes_all]
                procs_all.append(proc)  # also accept those that are already partially at the current process step
                proc_ids_all: list[int] = [proc_id for prc in procs_all for proc_id in prc.process_ids]
            if not add_prev_lot:
                proc_ids_lot = []
            else:
                procs_lot: list[Process] = [self._site.get_process(p, do_raise=True) for p in include_previous_processes_planned]
                prev_eligible_plants = [p.id for prev_proc in procs_lot for p in self._site.get_process_equipment(prev_proc.name_short)]
                procs_lot.append(proc)  # also accept those that are already partially at the current process step
                proc_ids_lot: list[int] = [proc_id for prc in procs_lot for proc_id in prc.process_ids]
                prev_eligible_lots = [lot for plant, lots in snapshot.lots.items() for lot in lots if plant in prev_eligible_plants]
            proc_ids = list(set(proc_ids_all + proc_ids_lot))
            for o in snapshot.orders:
                oid = o.id
                if oid in applicable_orders0 or len(o.current_processes) == 0:
                    continue
                if not all(p in proc_ids for p in o.current_processes):
                    continue
                if add_prev_lot and not all(p in proc_ids_all for p in o.current_processes) and \
                                                not any(oid in lot.orders and lot.active for lot in prev_eligible_lots):
                    continue
                applicable_orders0.add(o.id)

        omit_active_lots: bool = OrderInitMethod.OMIT_ACTIVE_LOTS in method
        omit_inactive_lots: bool = OrderInitMethod.OMIT_INACTIVE_LOTS in method
        omit_released_lots: bool = OrderInitMethod.OMIT_RELEASED_LOTS in method
        do_adapt: bool = omit_active_lots or omit_inactive_lots or omit_released_lots
        if do_adapt:
            eligible_lots: Iterator[list[Lot]] = (lots for plant, lots in snapshot.lots.items() if plant in eligible_plants)
            lots_for_removal: Iterator[Lot] = (lot for lots in eligible_lots for lot in lots)
            omit_all_lots: bool = omit_active_lots and omit_inactive_lots
            if not omit_all_lots:
                lots_for_removal = (lot for lot in lots_for_removal if ((omit_active_lots and lot.active) or (omit_inactive_lots and not lot.active) or (omit_released_lots and lot.status > 1)))
            orders: Iterator[str] = (order for lot in lots_for_removal for order in lot.orders)
            for order in orders:
                if order in applicable_orders0:
                    applicable_orders0.remove(order)
        return list(applicable_orders0)




