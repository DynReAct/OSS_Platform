from datetime import datetime, timedelta

from dynreact.base.LongTermPlanning import LongTermPlanning
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import LongTermTargets, MidTermTargets, Site, Equipment, ProductionTargets, EquipmentProduction, \
    StorageLevel, EquipmentAvailability


class SimpleLongTermPlanning(LongTermPlanning):
    """
    A dummy implementation of the long term planning algorithm that ignores storage levels, material classes,
    availabilities, throughput capacity, etc.,
    and simply tries to divide the total production target equally to shifts and plants
    """

    def __init__(self, uri: str, site: Site):
        super().__init__(uri, site)
        if not uri.startswith("default:"):
            raise NotApplicableException("Unexpected URI for simple long term planning provider: " + str(uri))
        props: dict[str, str] = {pair[0]: pair[1] for pair in (prop.split("=") for prop in uri[len("default:"):].split(",")) if len(pair) == 2}
        self._shift_duration: str = props.get("shiftDuration", "8h")
        duration: timedelta | None = DatetimeUtils.parse_duration(self._shift_duration)
        if duration is None:
            raise Exception("Invalid shift duration " + str(props.get("shiftDuration", "8h")))
        self._duration = duration

    def run(self, id0: str,
            structure: LongTermTargets,
            initial_storage_levels: dict[str, StorageLevel]|None=None,
            shifts: list[tuple[datetime, datetime]]|None=None,
            plant_availabilities: dict[int, EquipmentAvailability] | None=None) -> tuple[MidTermTargets, list[dict[str, StorageLevel]]]:
        shifts = shifts if shifts is not None else SimpleLongTermPlanning._default_shifts(structure.period, self._duration)
        if len(shifts) == 0:
            raise ValueError("No shifts provided/possible")
        total_weight: float = structure.total_production
        for category in self._site.material_categories:
            category_weight: float = sum(structure.production_targets.get(cl.id, 0) for cl in category.classes)
            if abs((category_weight - total_weight) / total_weight) > 0.01:
                raise ValueError(f"Total weight assigned to material category ({category.id}t) deviates from specified total weight ({total_weight}t)")

        start_time: datetime = structure.period[0]
        # start with half filled storages if not specified
        if initial_storage_levels is None:
            initial_storage_levels = {s.name_short: StorageLevel(storage=s.name_short, filling_level=0.5, timestamp=start_time) for s in self._site.storages}

        total_production = structure.total_production
        per_shift_production = total_production / len(shifts)
        targets_by_process: dict[str, list[ProductionTargets]] = {}
        for process in self._site.processes:  # TODO only schedulable processes
            plants: list[Equipment] = self._site.get_process_equipment(process.name_short)
            per_plant_prod = per_shift_production / len(plants)
            target_weight = {plant.id: EquipmentProduction(equipment=plant.id, total_weight=per_plant_prod) for plant in plants}
            process_targets: list[ProductionTargets] = []
            for shift in shifts:
                process_targets.append(ProductionTargets(process=process.name_short, period=shift, target_weight=target_weight))
            targets_by_process[process.name_short] = process_targets
        mid_term_targets = MidTermTargets(scheduler=f"SimpleLongTermPlanning({self._shift_duration})", sub_periods=shifts,
                              production_sub_targets=targets_by_process, source=structure.source,
                              comment=structure.comment, period=structure.period,
                              production_targets=structure.production_targets, total_production=structure.total_production)
        # assuming equilibrium... input tons = output tons, there is not going to be any changes in the storage levels
        storage_evolution = [initial_storage_levels for _ in shifts]
        return mid_term_targets, storage_evolution

    @staticmethod
    def _default_shifts(period: tuple[datetime, datetime], duration: timedelta) -> list[tuple[datetime, datetime]]:
        start = period[0]
        end = period[1]
        next_end = start + duration
        shifts: list[tuple[datetime, datetime]] = []
        while next_end <= end:
            shifts.append((start, next_end))
            start = next_end
            next_end = start + duration
        return shifts

