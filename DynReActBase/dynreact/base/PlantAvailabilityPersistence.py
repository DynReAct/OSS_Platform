from datetime import date, timedelta
from typing import Sequence

from dynreact.base.model import Site, EquipmentAvailability, PlannedWorkingShift


class PlantAvailabilityPersistence:
    """
    A service to load and store plant availability information
    Implementation expected in dynreact.availability.AvailabilityPersistenceImpl
    """

    def __init__(self, url: str, site: Site):
        self._url = url
        self._site = site

    def store(self, availability: EquipmentAvailability):
        raise Exception("not implemented")

    def delete(self, plant: int, start: date, end: date) -> bool:
        raise Exception("not implemented")

    def load(self, plant: int, start: date, end: date) -> list[EquipmentAvailability]:
        raise Exception("not implemented")

    def plant_data(self, start: date, end: date) -> list[int]:
        """
        Provides information about which plants have availability information
        :param start:
        :param end:
        :return:
        """
        raise Exception("not implemented")

    def load_all(self, start: date, end: date) -> dict[int, list[EquipmentAvailability]]:
        """
        :param start:
        :param end:
        :return: a dictionary with keys = plant ids, values = availability data
        """
        raise Exception("not implemented")

    @staticmethod
    def aggregate(equipment: list[int], start: date, end: date, availabilities: dict[int, list[EquipmentAvailability]],
                  shifts: dict[int, Sequence[PlannedWorkingShift]]|None=None,
                  default_daily_baseline: timedelta = timedelta(days=1)) -> dict[int, EquipmentAvailability]:
        result = {}
        if end <= start:
            return {}
        days = (end-start).days
        period = (start, end)
        zero = timedelta()
        one_day = timedelta(days=1)
        for plant in equipment:
            avs: list[EquipmentAvailability] = availabilities.get(plant, [])
            baselines = {av.daily_baseline for av in avs if av.daily_baseline is not None}
            daily_baseline: timedelta = next(b for b in baselines) if len(baselines) == 1 else default_daily_baseline
            all_deltas = {}
            start_cr = start
            for av in avs:
                deltas = av.deltas
                if av.daily_baseline != daily_baseline:
                    delta_base = av.daily_baseline - daily_baseline
                    start0 = max(start, av.period[0])
                    end0 = min(end, av.period[1])
                    deltas2 = {}
                    while start0 < end0:
                        end1 = start0 + one_day
                        delta = delta_base + deltas.get(start0, zero)
                        if delta != zero:
                            deltas2[start0] = delta
                        start0 = end1
                    deltas = deltas2
                if default_daily_baseline != daily_baseline and start_cr < av.period[0]:  # gap in plant availabilities
                    delta_base = default_daily_baseline - daily_baseline
                    while start_cr < av.period[0]:
                        end1 = start_cr + one_day
                        all_deltas[start_cr] = delta_base
                        start_cr = end1
                if deltas is not None:
                    all_deltas.update(deltas)
                start_cr = av.period[1]
            if start_cr < end and default_daily_baseline != daily_baseline:  # gap at the end
                delta_base = default_daily_baseline - daily_baseline
                while start_cr < end:
                    end1 = start_cr + one_day
                    all_deltas[start_cr] = delta_base
                    start_cr = end1
            if shifts is not None and plant in shifts:
                shifts0 = shifts[plant]
                shift_deltas = {}
                for sh in shifts0:
                    delta = sh.worktime - (sh.period[1] - sh.period[0])
                    if delta.total_seconds() != 0:
                        dt = sh.period[0].date()
                        if dt not in shift_deltas:
                            shift_deltas[dt] = timedelta()
                        shift_deltas[dt] += delta
                for dt, delta in shift_deltas.items():
                    if delta.total_seconds() == 0 or dt in all_deltas:
                        continue
                    all_deltas[dt] = delta
            result[plant] = EquipmentAvailability(equipment=plant, period=period, daily_baseline=daily_baseline, deltas=all_deltas if len(all_deltas) > 0 else None)
        return result
