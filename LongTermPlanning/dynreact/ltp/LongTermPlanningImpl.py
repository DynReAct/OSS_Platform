from datetime import datetime

from dynreact.base.LongTermPlanning import LongTermPlanning
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.model import Site, LongTermTargets, StorageLevel, EquipmentAvailability, MidTermTargets
from dynreact.ltp.LtpInstance import LtpInstance


class LongTermPlanningImpl(LongTermPlanning):

    def __init__(self, uri: str, site: Site):
        super().__init__(uri, site)
        if not uri.startswith("default:"):
            raise NotApplicableException()
        self._runs: dict[str, LtpInstance] = {}

    def run(self, id0: str,
            structure: LongTermTargets,
            initial_storage_levels: dict[str, StorageLevel]|None=None,
            shifts: list[tuple[datetime, datetime]]|None=None,
            plant_availabilities: dict[int, EquipmentAvailability] | None=None) -> tuple[MidTermTargets, list[dict[str, StorageLevel]]]:
        if id0 in self._runs:
            raise Exception(f"An optimization with the same id {id0} is already running")
        instance = LtpInstance(id0, self._site, structure, initial_storage_levels, shifts, plant_availabilities)
        self._runs[id0] = instance
        result = instance.start()
        self._runs.pop(id0, None)
        return result

    def interrupt(self, id0: str) -> bool:
        instance = self._runs.pop(id0, None)
        return instance.interrupt() if instance is not None else False



