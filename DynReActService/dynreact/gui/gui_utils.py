from datetime import datetime
from zoneinfo import ZoneInfo

from dash import html, callback_context

from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Equipment
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
    def changed_ids(excluded_ids: list[str]|None=None):
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
