import random
from datetime import datetime, timedelta
from functools import lru_cache
from typing import Sequence

from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.ShiftsProvider import ShiftsProvider
from dynreact.base.model import Site, PlannedWorkingShift


class DummyShiftsProvider(ShiftsProvider):
    """
    A dummy implementation that assumes all equipments are available all the time.
    But a random chance for non-availabilities can be configured, as well (only complete shifts)
    """

    def __init__(self, url: str, site: Site):
        super().__init__(url, site)
        if not url.startswith("dummy:"):
            raise NotApplicableException(f"URL {url} not applicable to dummy shifts provider")
        use_random: bool = url[len("dummy:"):].startswith("rand")
        seed = None
        if use_random and "(" in url and ")" in url:
            seed = int(url[url.index("(")+1:url.index(")")+1])
        self._rand: random.Random|None = random.Random(x=seed) if use_random else None
        self._url = url
        self._site = site
        self._start_hours: tuple[int, ...] = (0, 8, 16)  # TODO configurable
        self._delta: timedelta = timedelta(hours=self._start_hours[1] - self._start_hours[0])

    def load_all(self, start: datetime, end: datetime|None=None, limit: int|None=100, equipments: Sequence[int]|None=None) -> dict[int, Sequence[PlannedWorkingShift]]:
        start_of_day = start.replace(hour=0, minute=0, second=0, microsecond=0)
        shift_starts = [start_of_day.replace(hour=s) for s in self._start_hours]
        #first_shift = max(s for s in shift_starts if s <= start)
        cnt: int = 0
        if limit is None and end is None:
            end = (start_of_day.replace(day=1) + timedelta(days=32)).replace(day=1)
        if equipments is None:
            equipments = [e.id for e in self._site.equipment]
        result = {e: [] for e in equipments}
        one_day = timedelta(days=1)
        start_of_day = start_of_day-one_day
        done: bool = False
        while not done:
            start_of_day = start_of_day + one_day
            for hour in self._start_hours:
                shift0 = start_of_day.replace(hour=hour)
                if shift0 < start:
                    continue
                if (end is not None and shift0 >= end) or (limit is not None and cnt >= limit):
                    done = True
                    break
                shift1 = shift0 + self._delta
                for e in equipments:
                    worktime = self._delta if self._rand is None else self._working_hours_for_shift(e, shift0, shift1)
                    result[e].append(PlannedWorkingShift(equipment=e, period=(shift0, shift1), worktime=worktime))
                cnt += 1
        return result

    # need to cache to ensure consistent results, at least for some time
    @lru_cache(maxsize=8192)
    def _working_hours_for_shift(self, equipment: int, start: datetime, end: datetime) -> timedelta:
        return self._delta if self._rand.random() < 0.9 else timedelta()

