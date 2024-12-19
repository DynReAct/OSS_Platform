from datetime import datetime, timezone, timedelta, date
from typing import Dict, Any, Union, Optional, List

_FORMATS_WITH_ZONE: List[str] = [
    "%Y-%m-%dT%H:%M:%S.%f%z",
    "%Y-%m-%dT%H:%M:%S%z",
    "%Y-%m-%dT%H:%M%z",
    "%Y-%m-%dT%H%z",
    "%Y-%m-%d%z",
    "%Y-%m%z"
]

_FORMATS_NO_ZONE: List[str] = [
    "%Y-%m-%dT%H:%M:%S.%f",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%dT%H",
    "%Y-%m-%d",
    "%Y-%m"
]


class DatetimeUtils:

    @staticmethod
    def now() -> datetime:
        return datetime.now(tz=timezone.utc)

    @staticmethod
    def parse_datetime_str(dt: str) -> datetime|None:
        """
        examples:
        "now": Current timestamp,
        "now-1d": Yesterday's timestamp,
        "2023-12-04T23:59Z"
        :param dt:
        :return:
        """
        attempt = DatetimeUtils.parse_date(dt)
        if attempt is not None:
            return attempt
        dt = dt.strip()
        if not dt.lower().startswith("now"):
            return None
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
            return None
        dur: timedelta = DatetimeUtils.parse_duration((dt[len("now") + cnt:]).strip())
        if dur is None:
            return None
        return now - dur if is_minus else now + dur

    @staticmethod
    def parse_duration(d: str) -> timedelta|None:
        num: str = ""
        unit: str = ""
        for char in d:
            if len(unit) > 0:
                return None
            if not char.isdigit():
                unit = char
            else:
                num += char
        if len(num) == 0 or len(unit) == 0:
            return None
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
        return None

    @staticmethod
    def timestamp(data_point: Dict[str, Any], time_field: str = "time") -> datetime:
        if time_field not in data_point:
            raise TypeError("Data point does not contain a \"" + time_field + "\" entry: " + str(data_point))
        tm: Union[str, int] = data_point.get(time_field)
        if not isinstance(tm, str):
            return DatetimeUtils.to_datetime(tm)
        try:
            return datetime.strptime(tm, "%Y-%m-%dT%H:%M:%S.%f%z").astimezone(tz=timezone.utc)
        except ValueError:
            return datetime.strptime(tm, "%Y-%m-%d %H:%M:%S").astimezone(tz=timezone.utc)

    @staticmethod
    def to_millis(dt: Union[int, float, datetime]) -> int:
        if isinstance(dt, int):
            return dt
        if isinstance(dt, float):
            return int(round(dt))
        return int(dt.timestamp() * 1000)

    @staticmethod
    def to_datetime(millis: Union[float, int, datetime]) -> datetime:
        if isinstance(millis, datetime):
            return millis
        return datetime.fromtimestamp(millis / 1000, timezone.utc).replace(tzinfo=timezone.utc)

    @staticmethod
    def date_to_datetime(dt: date) -> datetime:
        return datetime(year=dt.year, month=dt.month, day=dt.day)

    @staticmethod
    def parse_date(input0: Union[float, str, datetime]) -> Optional[datetime]:
        """
        May return None
        :param input0: either millis since Unix epoch (1st Jan 1970), or a formatted datetime, such as
            "2020-10-12", "2020-10-12T12:15Z", "2020-10-12T12:15:43+01:00", or the like
        :return: datetime object in UTC timezone
        """
        if input0 is None:
            return None
        if isinstance(input0, datetime):
            return input0
        try:
            millis = int(input0)
            return DatetimeUtils.to_datetime(millis)
        except (ValueError, TypeError):
            pass
        for f in _FORMATS_WITH_ZONE:
            try:
                return datetime.strptime(input0, f).astimezone(tz=timezone.utc)
            except ValueError:
                pass
        for f in _FORMATS_NO_ZONE:
            try:
                return datetime.strptime(input0, f).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        return None

    @staticmethod
    def format(dt: datetime, use_zone: bool=True) -> str:
        return dt.strftime(_FORMATS_WITH_ZONE[2] if use_zone else _FORMATS_NO_ZONE[2])
