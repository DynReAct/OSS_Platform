from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

from dash import dcc

from dynreact.auth.authentication import dash_authenticated
from dynreact.base.impl.DatetimeUtils import DatetimeUtils

from dynreact.app import state, config

# Type: string ("en", "de")
language = dcc.Store(id="lang", storage_type="local")

# Those ones must not be changed from the pages, only from within dash_app
site: dcc.Store = dcc.Store(id="site-store", storage_type="memory", data=state.get_site().model_dump(exclude_none=True, exclude_unset=True))
# Type: datetime (the snapshot id)
# FIXME session persistence is not working; but neither does local, it only stores the initial value, no updates
selected_snapshot: dcc.Store = dcc.Store(id="selected-snapshot", storage_type="session")
selected_snapshot_obj: dcc.Store = dcc.Store(id="selected-snapshot-obj", storage_type="session")
selected_process: dcc.Store = dcc.Store(id="selected-process", storage_type="session")

# XXX this one is a bit ugly, but to be able to set the value of selected_snapshot from the snapshot page
# and also from url params we need an intermediate second global store which is only manipulated by the snapshot page
snapshot_page_selector: dcc.Store = dcc.Store(id="snapshot_selected-snapshot", storage_type="memory")
# These are updated from the respective pages via the dropdown, and they update the global process selector
lotcreation_process_selector: dcc.Store = dcc.Store(id="create_process-selector", storage_type="memory")
lotplanning_process_selector: dcc.Store = dcc.Store(id="lotplanning_process-selector", storage_type="memory")

# Type: str
#selected_process = dcc.Store(id="selected-process", storage_type="session")

def get_date_range(current_snapshot: str|datetime|None, zi: ZoneInfo|None = None) -> tuple[date, date, list[datetime], str]:  # list[options] not list[datetime]
    if not dash_authenticated(config):
        return None, None, [], None
    # 1) snapshot already selected
    current: datetime | None = DatetimeUtils.parse_date(current_snapshot)
    current_initial = current
    if current is None:
        # 3) use current snapshot
        current = state.get_snapshot_provider().current_snapshot_id()
    if current is None:  # should not really happen
        now = DatetimeUtils.now().astimezone(zi)
        return (now - timedelta(days=30)).date(), (now + timedelta(days=1)).date(), [], None
    dates: list[datetime] = []
    cnt = 0
    iterator = state.get_snapshot_provider().snapshots(start_time=current - timedelta(days=90), end_time=current + timedelta(days=3), order="desc") #if current_snapshot is None \
        #else state.get_snapshot_provider().snapshots(start_time=current - timedelta(hours=2), end_time=current + timedelta(days=90), order="asc")
    for dt in iterator:
        dates.append(dt)
        if cnt > 100:  # ?
            break
        cnt += 1
    dates = sorted(dates, reverse=True)
    if len(dates) == 0:
        if current_snapshot is not None:
            return get_date_range(None, zi=zi)
        return None, None, [], None
    if current_initial is not None:
        if dates[0] < current_initial - timedelta(minutes=1):
            dates.insert(0, current_initial)
        elif dates[-1] > current_initial + timedelta(minutes=1):
            dates.append(current_initial)
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
