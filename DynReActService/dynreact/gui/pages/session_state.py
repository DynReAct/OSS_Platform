from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from dash import dcc

from dynreact.auth.authentication import dash_authenticated
from dynreact.base.impl.DatetimeUtils import DatetimeUtils

from dynreact.app import state, config

# Type: string ("en", "de")
language = dcc.Store(id="lang", storage_type="local")

# Type: datetime (the snapshot id)
site: dcc.Store = dcc.Store(id="site-store", storage_type="memory")
selected_snapshot: dcc.Store = dcc.Store(id="selected-snapshot", storage_type="memory")
selected_snapshot_obj: dcc.Store = dcc.Store(id="selected-snapshot-obj", storage_type="memory")
selected_process: dcc.Store = dcc.Store(id="selected-process", storage_type="memory")


def init_stores(*args, **kwargs):   #-> tuple[dcc.Store, dcc.Store, dcc.Store, dcc.Store]:
    global site
    global selected_snapshot
    global selected_snapshot_obj
    global selected_process
    if hasattr(site, "data") and site.data is not None:
        return
    site_obj = state.get_site().model_dump(exclude_none=True, exclude_unset=True)
    process: str | None = kwargs.get("process")  # TODO alternatively, use store?
    snapshot: datetime|None = DatetimeUtils.parse_date(kwargs.get("snapshot"))
    snapshot_obj = state.get_snapshot(snapshot)
    snapshot_serialized = snapshot_obj.model_dump(exclude_unset=True, exclude_none=True) if snapshot_obj is not None else None
    site.data = site_obj
    # Note: this implies dropping the seconds part!
    selected_snapshot.data = DatetimeUtils.format(snapshot_obj.timestamp) if snapshot_obj is not None else None
    selected_snapshot_obj.data = snapshot_serialized
    selected_process.data=process


# Type: str
#selected_process = dcc.Store(id="selected-process", storage_type="session")

def get_date_range(current_snapshot: str|datetime|None, zi: ZoneInfo|None = None) -> tuple[date, date, list[datetime], str]:  # list[options] not list[datetime]
    if not dash_authenticated(config):
        return None, None, [], None
    # 1) snapshot already selected
    current: datetime | None = DatetimeUtils.parse_date(current_snapshot)
    if current is None:
        # 3) use current snapshot
        current = state.get_snapshot_provider().current_snapshot_id()
    if current is None:  # should not really happen
        now = DatetimeUtils.now().astimezone(zi)
        return (now - timedelta(days=30)).date(), (now + timedelta(days=1)).date(), [], None
    dates: list[datetime] = []
    cnt = 0
    iterator = state.get_snapshot_provider().snapshots(start_time=current - timedelta(days=90), end_time=current + timedelta(minutes=1), order="desc") #if current_snapshot is None \
        #else state.get_snapshot_provider().snapshots(start_time=current - timedelta(hours=2), end_time=current + timedelta(days=90), order="asc")
    for dt in iterator:
        dates.append(dt)
        if cnt > 100:  # ?
            break
        cnt += 1
    dates = sorted(dates, reverse=True)
    if len(dates) == 0:
        return None, None, [], None
    to_be_selected = dates[0]
    min_dist = abs(to_be_selected - current)
    for dt in dates:
        distance = abs(dt - current)
        if distance < min_dist:
            to_be_selected = dt
            min_dist = distance
    options = [{"label": DatetimeUtils.format(dt.astimezone(zi)), "value": DatetimeUtils.format(dt), "selected": selected} for dt, selected in ((d, d == to_be_selected) for d in dates)]
    if len(options) == 1:
        dt = dates[0].astimezone(zi).date()
        return dt - timedelta(days=1), dt + timedelta(days=1), options, DatetimeUtils.format(to_be_selected)
    return dates[-1].date(), dates[0].date(), options, DatetimeUtils.format(to_be_selected)


try:
    from flask_login import UserMixin
    class User(UserMixin):
        # User data model. It has to have at least self.id as a minimum
        def __init__(self, username):
            self.id = username
except ModuleNotFoundError:
    pass
