import types
import typing
from datetime import datetime, date, timedelta
from typing import Sequence, Any
from zoneinfo import ZoneInfo

from dash import html, callback_context
from pydantic import BaseModel

from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Equipment, Order, Snapshot, Site, Lot, Process, TransportTimes
from dynreact.state import DynReActSrvState


class GuiUtils:

    @staticmethod
    def plant_element(plant: Equipment) -> html.Div:
        if plant is None:
            return None
        title = ""
        if plant.name is not None:
            title += plant.name + " ("
        title += "plant id: " + str(plant.id)
        if plant.name is not None:
            title += ")"
        return html.Div(plant.name_short, title=title)

    @staticmethod
    def changed_ids(excluded_ids: Sequence[str]|None=None):
        "To be called from a callback"
        return [cid for cid in (p['prop_id'].split(".")[0] for p in callback_context.triggered) if excluded_ids is None or cid not in excluded_ids]

    @staticmethod
    def format_snapshot(snapshot: datetime|str|None, tz: str|None, state: DynReActSrvState|None=None) -> str:
        snapshot = DatetimeUtils.parse_date(snapshot)
        if snapshot is None:
            return ""
        if tz is not None or state is None:
            zi = None
            try:
                zi = ZoneInfo(tz)
            except:
                pass
            return DatetimeUtils.format(snapshot.astimezone(zi))
        return DatetimeUtils.format(state.as_timezone(snapshot))

    @staticmethod
    def is_numeric(s: str|float|int|None, allow_negative: bool=False) -> bool:
        if isinstance(s, float|int):
            return True
        if s is None or s == "":
            return False
        s = s.strip()
        if allow_negative and s[0] == "-" and len(s) > 1:
            s = s[1:]
        if s.isnumeric():
            return True
        if "." not in s or len(s) - len(s.replace(".", "")) != 1:
            return False
        if s[0] == "." or s[-1] == ".":
            return False
        return GuiUtils.is_numeric(s.replace(".", ""))

    @staticmethod
    def orders_table(orders: Sequence[Order], site: Site,
                     process: str | None = None,
                     snapshot: Snapshot|None=None,
                     snapshot_provider: SnapshotProvider|None=None,
                     relevant_fields: list[str] | None=None,
                     skip_selection_checkbox: bool=False):
        """Generate column definitions and row data"""
        from pydantic.fields import FieldInfo
        import json
        _none_type = type(None)
        transport_times = site.transport_times.transport_times if site.transport_times is not None else None

        def _lot_info(lot: Lot) -> str:
            result = f"{lot.id} [status={lot.status}, active={lot.active}"
            if lot.status > 1 and lot.end_time is not None:
                result += f", ends={DatetimeUtils.format(lot.end_time.astimezone(), use_zone=False)}"
            if hasattr(lot, "priority"):
                result += f", priority={getattr(lot, 'priority')}"
            if lot.weight is not None:
                result += f", weight={lot.weight:.2f} t"
            if lot.comment is not None:
                result += f", comment={lot.comment}"
            result += "]"
            return result

        def _is_numeric(tp: type | None):
            if tp == float or tp == int:
                return True
            if tp == str or tp == bool or tp == _none_type:
                return False
            if isinstance(tp, types.UnionType):
                args: tuple[Any, ...] = typing.get_args(tp)
                return float in args or int in args
            return False

        _availability_by_order: dict[str, datetime | None] = {}
        order_ids = {o.id: o for o in orders}
        all_procs = site.processes
        procs_by_id: dict[int, Process] = {}
        for proc in all_procs:
            for p_id in proc.process_ids:
                procs_by_id[p_id] = proc
        processes_by_ids = {p.name_short: p for p in site.processes}
        all_processes = list(processes_by_ids.keys())
        proc_idx = all_processes.index(process) if process is not None else None
        prev_processes = [p.name_short for p in site.processes if p.next_steps is not None and process in p.next_steps]
        previous_processes = all_processes[:proc_idx] if proc_idx is not None else None
        if previous_processes:
            previous_processes.reverse()
        all_lots: dict[str, Lot] = {lot.id: lot for lots in snapshot.lots.values() for lot in lots} if snapshot is not None else {}
        current_process_plants = [p.id for p in site.equipment if p.process == process] if process is not None else []

        def availability_for_order(order: str) -> datetime | None:  # requires snapshot and snapshot_provider and process
            if order in _availability_by_order:
                return _availability_by_order[order]
            o = order_ids[order]
            if o.lots is None:
                return None
            prev_lot_proc = next((p for p in prev_processes if p in o.lots), None)
            prev_lot_id = o.lots.get(prev_lot_proc)
            prev_lot = all_lots.get(prev_lot_id)
            if prev_lot is None or prev_lot.end_time is None or not prev_lot.active:  # or not snapshot_provider.is_lot_complete(prev_lot):
                _availability_by_order[order] = None
                return None
            lt_times = snapshot_provider.get_order_lot_times(snapshot.timestamp, o.id)
            end_time = None
            if lt_times is not None and len(lt_times) > 0 and prev_lot_proc in lt_times[o.id]:
                end_time = lt_times[o.id][prev_lot_proc].end
                if transport_times is not None:
                    previous_lot = o.lots[prev_lot_proc]
                    start_equipment = next((e for e in site.equipment if e.process == prev_lot_proc and e.id in snapshot.lots and
                            any(lt.id == previous_lot for lt in snapshot.lots[e.id])), None)
                    if start_equipment is not None and transport_times is not None:
                        t_times = [t for t in (transport_times(start_equipment.id, eq) for eq in current_process_plants if eq in o.allowed_equipment) if t is not None]
                        max_transport: timedelta = max(t_times) if len(t_times) > 0 else timedelta()
                        end_time = end_time + max_transport
            _availability_by_order[order] = end_time
            return end_time

        def column_def_for_field(field: str, info: FieldInfo):
            filter_id = "agNumberColumnFilter" if _is_numeric(
                info.annotation) else "agDateColumnFilter" if info.annotation == datetime or info.annotation == date else "agTextColumnFilter"
            col_def = {"field": field, "filter": filter_id, "filterParams": {"buttons": ["reset"]}}
            if field == "lots":
                col_def["filterParams"]["maxNumConditions"] = 50
            return col_def

        if len(orders) > 0:
            fields = [column_def_for_field(key, info) for key, info in orders[0].model_fields.items() if
                    (key not in ["material_properties", "lot", "lot_position", "material_status", "follow_up_processes"])] + \
                    ([column_def_for_field(key, info) for key, info in orders[0].material_properties.model_fields.items()] if isinstance(orders[0].material_properties, BaseModel) else [])
        else:
            fields = [{"field": "id"}]

        value_formatter_object = {"function": "formatCell(params.value)"}
        for field in fields:
            if field["field"] == "id":
                field["pinned"] = True
                field["headerName"] = "Id"
                if not skip_selection_checkbox:
                    field["checkboxSelection"] = True
                # field["headerCheckboxSelection"] = True # This option is difficult to understand: it also selects rows which are currently hidden
            if field["field"] in ["active_processes", "coil_status", "follow_up_processes", "material_status", "actual_weight", "material_classes"]:
                field["valueFormatter"] = value_formatter_object
            if field["field"] == "current_equipment":
                field["headerName"] = "Equipment"
        # FIXME tooltipField not working?
        if process and snapshot:
            fields.append({"field": "lot_info", "headerName": "Lot", "tooltipField": "lot_info",
                           "headerTooltip": "Lot of the selected processing stage", "filter": "agTextColumnFilter"})
            fields.append({"field": "prev_lot_info", "headerName": "Lot: previous", "tooltipField": "prev_lot_info",
                           "headerTooltip": "Lot of the previous processing stage", "filter": "agTextColumnFilter"})
            fields.append({"field": "availability", "headerTooltip": "Order availability", "filter": "agDateColumnFilter"})

        plants = {p.id: p for p in site.equipment}

        def order_to_json(o: Order):
            as_dict = o.model_dump(exclude_none=True, exclude_unset=True)
            for key in ["lots", "lot_positions"]:
                if key in as_dict:
                    as_dict[key] = json.dumps(as_dict[key])
            if o.allowed_equipment is not None:
                as_dict["allowed_equipment"] = [plants[p].name_short if p in plants else str(p) for p in o.allowed_equipment]
            if o.current_equipment is not None:
                as_dict["current_equipment"] = [plants[p].name_short if p in plants else str(p) for p in o.current_equipment]
            if isinstance(o.material_properties, BaseModel):
                as_dict.update(o.material_properties.model_dump(exclude_none=True, exclude_unset=True))
            elif isinstance(o.material_properties, dict):
                as_dict.update(o.material_properties)
            if process is not None and o.lots is not None:
                lot = snapshot.get_order_lot(site, o.id, process)
                if lot is not None:
                    as_dict["lot_info"] = _lot_info(lot)
                if snapshot_provider is not None and snapshot is not None:
                    prev_lot_proc = next((p for p in previous_processes if p in o.lots), None)
                    prev_lot_id = o.lots.get(prev_lot_proc)
                    prev_lot = all_lots.get(prev_lot_id)
                    if prev_lot is not None:
                        as_dict["prev_lot_info"] = _lot_info(prev_lot)
                        availability = availability_for_order(o.id)
                        if availability is not None:
                            as_dict["availability"] = DatetimeUtils.format(availability.astimezone(), use_zone=False).replace("T", " ")
            return as_dict

        orders_filtered = [order for order in orders if any(plant in current_process_plants for plant in order.allowed_equipment)] if process is not None else orders
        #orders_sorted = sorted(orders_filtered, key=process_index_for_order)  # TODO
        orders_sorted = orders_filtered
        sorted_orders = [order_to_json(order) for order in orders_sorted]
        first_orders = sorted_orders[0:min(50, len(sorted_orders))]
        try:
            def field_sort_id(f: dict[str, any]) -> int:
                _id = f.get("field")
                if not _id:
                    return 1000
                is_material_prop = False
                field_id = _id
                if relevant_fields is not None:
                    if _id not in relevant_fields:
                        mat_id = "material_properties." + _id
                        is_material_prop = mat_id in relevant_fields
                        if is_material_prop:
                            field_id = mat_id
                    if field_id in relevant_fields and any(o.get(_id) is not None for o in first_orders):
                        return relevant_fields.index(field_id)
                if field_id == "current_equipment":
                    return -4
                if field_id == "lot_info":
                    return -3
                if field_id == "prev_lot_info":
                    return -2
                if field_id == "availability":
                    return -1
                return 1000

            fields.sort(key=field_sort_id)
        except:
            pass

        return fields, sorted_orders
