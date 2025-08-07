"""
Module snapshot_imports_page
"""
import threading
from datetime import datetime

import dash
from dash import html, callback, Output, Input, dcc

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.base.SnapshotImporter import SnapshotImporter
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.gui.gui_utils import GuiUtils

dash.register_page(__name__, path="/imports")
translations_key = "snapimp"

import_thread_name = "snapshot_import"
import_thread: threading.Thread|None = None
last_result: datetime|Exception|None = None


def layout(*args, **kwargs):
    prov = state.get_snapshot_provider()
    if not hasattr(prov, "next_scheduled_import"):
        return html.H1("Not found")
    return html.Div([
        html.H1("Snapshot imports", id=translations_key + "-title"),
        html.Div([
            html.Div("Latest snapshot:"), html.Div(id=translations_key + "-lastsnap"),
            html.Div("Upcoming snapshot:"), html.Div(id=translations_key + "-nextsnap"),
            html.Div("Imports active:"), html.Div(id=translations_key + "-importactive"),
            html.Div("Import running:"), html.Div(id=translations_key + "-importrunning"),
        ], className="snapimp-infogrid"),
        html.Div([
            html.Div("Pause imports:"), html.Div(html.Button("Pause", id="snapimp-pause", className="dynreact-button dynreact-button-small", title="Pause snapshot imports")),
            html.Div("New snapshot:", title="Trigger new snapshot import"),
                html.Div(html.Button("Import", id="snapimp-trigger", className="dynreact-button dynreact-button-small", title="Trigger new snapshot import"))
        ], className="snapimp-ctrl-grid"),
        html.Div([
            html.Div(id=translations_key + "-alert"),
            html.Div("✖", id=translations_key + "-alert-close", role="button", title="Close", className="snapimp-close"),
        ], id=translations_key + "-alert-container", className="snapimp-infobox snapimp-hidden"),
        dcc.Interval(id=translations_key + "-interval", interval=30_000),
    ])


@callback(
    Output("snapimp-lastsnap", "children"),
    Output("snapimp-nextsnap", "children"),
    Output("snapimp-importactive", "children"),
    Output("snapimp-importrunning", "children"),
    Output("snapimp-pause", "children"),
    Output("snapimp-pause", "title"),
    Output("snapimp-pause", "disabled"),
    Output("snapimp-trigger", "disabled"),
    Output("snapimp-interval", "interval"),
    Output("snapimp-alert", "children"),
    Output("snapimp-alert-container", "className"),
    Input("snapimp-interval", "n_intervals"),
    Input("snapimp-pause", "n_clicks"),
    Input("snapimp-trigger", "n_clicks"),
    Input("snapimp-alert-close", "n_clicks"),
)
def status(_, __, ___, ____):
    if not dash_authenticated(config):
        return None, None, None, None, None, None, True, True, dash.no_update, None, "snapimp-infobox snapimp-hidden"
    prov = state.get_snapshot_provider()
    if not hasattr(prov, "next_scheduled_import"):
        return "", "", "", "", "", "", True, True, 3_600_000, None, "snapimp-infobox snapimp-hidden"
    global import_thread
    prov2: SnapshotImporter = prov
    last_snap: datetime | None = prov2.previous()
    next_scheduled_import: datetime | None = prov2.next_scheduled_import()
    is_paused: bool = prov2.is_paused()
    is_running: bool = prov2.import_running()
    last_snap_str = DatetimeUtils.format(last_snap) if last_snap is not None else ""
    next_snap_str = DatetimeUtils.format(next_scheduled_import) if next_scheduled_import is not None else ""
    result: datetime|Exception|None = None
    if not is_running:
        result = _thread_clean_up()
    msg: str = dash.no_update
    info_class: str = dash.no_update
    changed_ids = GuiUtils.changed_ids()
    if result is None and "snapimp-alert-close" in changed_ids:
        msg = ""
        info_class = "snapimp-infobox snapimp-hidden"
    elif "snapimp-pause" in changed_ids:
        if is_paused:
            prov2.resume()
            scheduled = prov2.next_scheduled_import()
            msg = "Snapshot imports resumed. Next scheduled import: " + (
                str(DatetimeUtils.format(scheduled)) if scheduled is not None else "None")
        else:
            prov2.pause()
            msg = "Snapshot imports paused."
        is_paused = prov2.is_paused()
        info_class = "snapimp-infobox"
    elif "snapimp-trigger" in changed_ids:
        if prov2.import_running():
            msg = "Import is already running"
        else:
            _start_import(prov2)
            msg = "Import started"
        is_running = True
        info_class = "snapimp-infobox"
    elif result is not None:
        success = isinstance(result, datetime)
        if success:
            msg = f"New snapshot {DatetimeUtils.format(result)}"
            info_class = "snapimp-infobox"
        elif isinstance(result, Exception):
            msg = f"Error importing snapshot: {result}"
            info_class = "snapimp-infobox snapimp-alert"
    btn_label = "Pause" if not is_paused else "Restart"
    btn_title = "Pause snapshot imports" if not is_paused else "Restart snapshot imports"
    update_interval: int = 30_000 if not is_running else 5_000
    return last_snap_str, next_snap_str, str(not is_paused), str(is_running), btn_label, btn_title, False, is_running, update_interval, msg, info_class


def _start_import(prov: SnapshotImporter):
    global import_thread
    global import_thread_name

    def run():
        global last_result
        try:
            last_result = prov.trigger_import()
        except Exception as e:
            last_result = e
    t = threading.Thread(name=import_thread_name, target=run)
    import_thread = t
    t.start()


def _thread_clean_up():
    """must only be called when import is not running"""
    global import_thread
    global last_result
    if import_thread is not None:
        t = import_thread
        import_thread = None
        t.join()    # it is important to join all finished threads for resource cleanup
        return last_result
    return None

