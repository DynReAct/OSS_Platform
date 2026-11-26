import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import TypeVar, Generic, Iterator, Literal, Sequence, Self, Mapping

import pandas as pd
from pydantic import BaseModel, model_validator

DATA_TYPE = TypeVar("DATA_TYPE", bound=float|int|bool)


@dataclass(frozen=True)
class DataPoint(BaseModel, Generic[DATA_TYPE]):


    validity: tuple[datetime, datetime]
    value: DATA_TYPE


class Timeseries(Generic[DATA_TYPE]):

    _DAY0 = datetime(year=1, month=1, day=1)
    _LAST_DAY = datetime(year=9999, month=1, day=1)
    _NAN = float("nan")
    _MAX = float("inf")
    _MIN = -float("inf")
    _ZERO_DUR = timedelta()

    def values(self, start: datetime|None=None, end: datetime|None=None, direction: Literal["asc", "desc"]="asc") -> Iterator[DataPoint[DATA_TYPE]]:
        raise NotImplementedError

    def stats(self, start: datetime|None=None, end: datetime|None=None, skip_nan: bool=True) -> tuple[int, float, float, float, float]:
        """
        Returns:
            count, mean, std, min, max
        """
        cnt = 0
        mean = 0.
        squared_diff = 0.
        min_v = Timeseries._MAX
        max_v = Timeseries._MIN
        for entry in self.values(start, end):
            val = entry.value
            if skip_nan and val != val:
                continue
            if val > max_v:
                max_v = val
            if val < min_v:
                min_v = val
            cnt += 1
            delta = val - mean
            mean += delta/cnt
            delta2 = val - mean
            squared_diff += delta * delta2
        if cnt == 0:
            return 0, Timeseries._NAN, Timeseries._NAN, Timeseries._MAX, Timeseries._MIN
        return cnt, mean, math.sqrt(squared_diff/cnt), min_v, max_v

    def avg(self, start: datetime | None = None, end: datetime | None = None, skip_nan: bool=True) -> tuple[float, timedelta]:
        """
        Returns:
            mean based on validity durations, duration
        """
        total_duration: timedelta = Timeseries._ZERO_DUR
        total_value: timedelta = Timeseries._ZERO_DUR
        for entry in self.values(start=start, end=end):
            val = entry.value
            if skip_nan and val != val:
                continue
            validity = entry.validity
            if start > validity[0]:
                if end <= validity[1]:
                    return val, end - start
                delta = validity[1] - start
            elif end <= validity[1]:
                if end > validity[0]:
                    delta = end - validity[0]
                    total_duration += delta
                    total_value += val * delta
                break
            else:
                delta = validity[1] - validity[0]
            total_duration += delta
            total_value += val * delta
        if total_duration == Timeseries._ZERO_DUR:
            return Timeseries._NAN, Timeseries._ZERO_DUR
        return total_value / total_duration, total_duration

    def next(self, start: datetime|None = None) -> DataPoint[DATA_TYPE]|None:
        try:
            return next(self.values(start=start, direction="asc"))
        except StopIteration:
            return None

    def previous(self, start: datetime|None = None) -> DataPoint[DATA_TYPE]|None:
        try:
            return next(self.values(end=start, direction="desc"))
        except StopIteration:
            return None

    def is_non_negative(self, start: datetime | None = None, end: datetime | None = None):
        return all(val.value >= 0 for val in self.values(start, end))

    def size(self, start: datetime|None=None, end: datetime|None=None) -> int:
        cnt = 0
        for _ in self.values(start, end):
            cnt += 1
        return cnt

    def __len__(self):
        return self.size()

    def __bool__(self):
        return True


class MemoryTimeseries(BaseModel, Timeseries[DATA_TYPE], use_attribute_docstrings=True):

    entries: Sequence[DataPoint]
    "Ordered list of entries for consecutive time intervals"
    unit: str|None=None
    # internally used fields below; set in model validator
    start_end: tuple[datetime, datetime] | None
    start_times: tuple[datetime, ...]
    empty: bool
    nonnegative: bool

    @model_validator(mode="before")
    def validate(self) -> Self:
        is_dict = isinstance(self, dict)
        start_end = self.get("start_end") if is_dict else self.start_end
        entries = self.get("entries") if is_dict else self.entries
        is_entry_dict = isinstance(entries[0], Mapping) if len(entries) > 0 else False
        start_times = self.get("start_times") if is_dict else self.start_times
        if not start_end and len(entries) > 0:
            start_end = (entries[0].validity[0], entries[-1].validity[1]) if not is_entry_dict else \
                (entries[0].get("validity")[0], entries[-1].get("validity")[1])
        if not start_times:
            start_times = tuple([e.validity[0] for e in entries]) if not is_entry_dict else \
                tuple([e.get("validity")[0] for e in entries])
        nonnegative = all(e.value >= 0 for e in entries) if not is_entry_dict else \
                all(e.get("costs_per_mwh") >= 0 for e in entries)
        empty = len(entries) == 0
        if is_dict:
            self["start_end"] = start_end
            self["start_times"] = start_times
            self["nonnegative"] = nonnegative
            self["empty"] = empty
        else:
            self.start_end = start_end
            self.start_times = start_times
            self.nonnegative = nonnegative
            self.empty = empty
        return self

    def values(self, start: datetime|None=None, end: datetime|None=None, direction: Literal["asc", "desc"]="asc") -> Iterator[DataPoint[DATA_TYPE]]:
        start = start or Timeseries._DAY0
        end = end or Timeseries._LAST_DAY
        if self.empty or start >= self.start_end[1] or end <= self.start_end[0]:
            return iter(tuple())
        start_idx = 0
        end_idx = len(self.entries)
        if start >= self.start_end[0]:
            start_idx = bisect_left(self.start_times, start)
            if start_idx > 0 and self.entries[start_idx-1].validity[1] > start:
                start_idx = start_idx - 1
        if end < self.start_end[1]:
            end_idx = bisect_right(self.start_times, end)
            if end_idx < len(self.entries) and self.entries[end_idx].validity[1] > end:
                end_idx += 1
        return iter(self.entries[start_idx:end_idx])

    def next(self, start: datetime | None = None) -> DataPoint[DATA_TYPE] | None:
        start = start or Timeseries._DAY0
        if self.empty or start > self.start_end[1]:
            return None
        idx = bisect_left(self.start_times, start)
        return self.entries[idx]

    def previous(self, start: datetime | None = None) -> DataPoint[DATA_TYPE] | None:
        start = start or Timeseries._LAST_DAY
        if self.empty or start < self.start_end[0]:
            return None
        idx = bisect_right(self.start_times, start)
        return self.entries[idx-1]

    def is_non_negative(self, start: datetime | None = None, end: datetime | None = None):
        if self.nonnegative or (start is None and end is None):
            return self.nonnegative
        return all(val.value >= 0 for val in self.values(start, end))

    def __len__(self):
        return len(self.entries)


class PandasTimeseries(Timeseries):

    import pandas as pd

    def __init__(self, df: pd.DataFrame, col_idx: int|str=1):
        """Assuming that the index column is of datetime type"""
        self._df = df
        self._index = df.index
        self._data_col = col_idx if isinstance(col_idx, int) else list(df.columns).index(col_idx)

    def values(self, start: datetime|None=None, end: datetime|None=None, direction: Literal["asc", "desc"]="asc") -> Iterator[DataPoint[DATA_TYPE]]:
        df = self._df
        asc = direction != "desc"
        if asc and start is not None:
            df = df[self._index >= start]
        elif not asc and end is not None:
            df = df[self._index < end]
        if direction == "desc":
            df = df[::-1]
        return PandasIterator(iter(df.itertuples(index=True)), self._data_col, desc=not asc)


class PandasIterator(Iterator[DataPoint]):

    def __init__(self, it: Iterator[DataPoint], data_col: int, desc: bool=False):
        self._it = it
        self._data_col = data_col
        self._desc = desc
        self._last_row = None
        self._previous_delta: timedelta|None = None
        try:
            self._last_row = next(it)
        except StopIteration:
            pass

    def __iter__(self):
        return self

    def __next__(self):
        last_row = self._last_row
        if last_row is None:
            raise StopIteration
        next_row = None
        try:
            next_row = next(self._it)
        except StopIteration:
            pass
        ts0 = last_row[0]
        ts1 = next_row[0] if next_row is not None else ts0 + self._previous_delta if self._previous_delta is not None else ts0 + timedelta(days=365)  # ?
        if self._desc:
            ts0, ts1 = (ts1, ts0)
        self._previous_delta = ts1 - ts0
        value = last_row[self._data_col]
        self._last_row = next_row
        return DataPoint(validity=(ts0, ts1), value=value)


# Read a CSV file into memory, as a pandas dataframe
# A more efficient version iterating the rows on demand could be created, as well
def csv_memory_timeseries(file: str, col_idx: int|str = 1, separator: str=",", index_col: str|None=None, skiprows: int|Sequence[int]|None=None) -> PandasTimeseries:
    df = pd.read_csv(file, sep=separator, index_col=index_col, skiprows=skiprows)
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)
    return PandasTimeseries(df, col_idx=col_idx)

