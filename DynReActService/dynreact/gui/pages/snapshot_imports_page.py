"""
Module snapshot_imports_page
"""
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
        html.Div(id=translations_key + "-alert", className="snapimp-infobox snapimp-hidden"),
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
    Input("snapimp-interval", "n_intervals"),
    Input("snapimp-alert", "children"),  # triggered itself by buttons in function below
)
def status(_, __):
    if not dash_authenticated(config):
        return None, None, None, None, None, None, True, True, dash.no_update
    prov = state.get_snapshot_provider()
    if not hasattr(prov, "next_scheduled_import"):
        return "", "", "", "", "", "", True, True, 3_600_000
    prov2: SnapshotImporter = prov
    last_snap: datetime | None = prov2.previous()
    next_scheduled_import: datetime | None = prov2.next_scheduled_import()
    is_paused: bool = prov2.is_paused()
    is_running: bool = prov2.import_running()
    last_snap_str = DatetimeUtils.format(last_snap) if last_snap is not None else ""
    next_snap_str = DatetimeUtils.format(next_scheduled_import) if next_scheduled_import is not None else ""
    btn_label = "Pause" if not is_paused else "Restart"
    btn_title = "Pause snapshot imports" if not is_paused else "Restart snapshot imports"
    update_interval: int = 30_000 if not is_running else 5_000
    return last_snap_str, next_snap_str, str(not is_paused), str(is_running), btn_label, btn_title, False, is_running, update_interval



@callback(
    Output("snapimp-alert", "children"),
    Output("snapimp-alert", "className"),
    Input("snapimp-pause", "n_clicks"),
    Input("snapimp-trigger", "n_clicks"),
    config_prevent_initial_callbacks=True
)
def toggle_active(_, __):
    prov = state.get_snapshot_provider()
    if not dash_authenticated(config) or not hasattr(prov, "next_scheduled_import"):
        return None, "snapimp-infobox snapimp-hidden"
    prov2: SnapshotImporter = prov
    is_paused: bool = prov2.is_paused()
    msg: str = ""
    changed_ids = GuiUtils.changed_ids()
    if "snapimp-pause" in changed_ids:
        if is_paused:
            prov2.resume()
            scheduled = prov2.next_scheduled_import()
            msg = "Snapshot imports resumed. Next scheduled import: " + (str(DatetimeUtils.format(scheduled)) if scheduled is not None else "None")
        else:
            prov2.pause()
            msg = "Snapshot imports paused."
    elif "snapimp-trigger" in changed_ids:
        if prov2.import_running():
            msg = "Import is already running"
        else:
            # TODO this must run in a separate thread!
            prov2.trigger_import()
            msg = "Import started"
    return msg, "snapimp-infobox"


