from datetime import datetime

from dash import dcc
from dynreact.base.impl.DatetimeUtils import DatetimeUtils

from dynreact.app import state

# Type: string ("en", "de")
language = dcc.Store(id="lang", storage_type="local")

# Type: datetime (the snapshot id)
site: dcc.Store = dcc.Store(id="site-store", storage_type="memory")
selected_snapshot: dcc.Store = dcc.Store(id="selected-snapshot", storage_type="memory")
selected_snapshot_obj: dcc.Store = dcc.Store(id="selected-snapshot-obj", storage_type="memory")
selected_process: dcc.Store = dcc.Store(id="selected-process", storage_type="memory")


def init_stores(*args, **kwargs) -> tuple[dcc.Store, dcc.Store, dcc.Store, dcc.Store]:
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


try:
    from flask_login import UserMixin
    class User(UserMixin):
        # User data model. It has to have at least self.id as a minimum
        def __init__(self, username):
            self.id = username
except ModuleNotFoundError:
    pass
