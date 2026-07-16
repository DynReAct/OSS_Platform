import json
import logging
import os
from datetime import timedelta
from typing import Sequence

import dash
from dash import dcc, html, Output, Input, State, clientside_callback, ClientsideFunction, callback, ALL, \
    callback_context
from flask import Flask


from dynreact.app import config, state
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Snapshot, Lot
from dynreact.gui.gui_utils import GuiUtils
from dynreact.gui.pages.session_state import language, site, selected_snapshot, selected_process, selected_snapshot_obj, \
    selected_snapshot_next, selected_snapshot_prev, snapshot_update_active

server = Flask(__name__)

# requests_pathname_prefix required for operation with FastAPI
app = dash.Dash(__name__, server=server, routes_pathname_prefix="/", requests_pathname_prefix="/dash/",
                assets_folder="assets", assets_ignore=r".*dynreactviz/.*",
                suppress_callback_exceptions=True, title="DynReAct",
                # dynreactviz contains ES modules that should not be auto-injected as classic Dash assets.
                # external_scripts=[{"src": "/dash/assets/dynreactviz/ltp-viz.js", "type": "module"}],
                use_pages=True, pages_folder="pages")
# app = dash.Dash(__name__, server=server,  url_base_pathname="/dash/",
#                 assets_folder="assets", suppress_callback_exceptions=False, title="DynReAct",
#                 use_pages=True, pages_folder="pages")

if config.auth_method is not None:
    secret_key = os.getenv("FLASK_SESSION_KEY")
    if secret_key is None:
        raise Exception("Session key not set")
    # Updating the Flask Server configuration with Secret Key to encrypt the user session cookie
    server.config.update(SECRET_KEY=secret_key)

    # Login manager object will be used to login / logout users
    from flask_login import LoginManager, current_user
    from dynreact.gui.pages.session_state import User
    login_manager = LoginManager()
    login_manager.init_app(server)
    login_manager.login_view = "/dash/login"


    @login_manager.user_loader
    def load_user(username):
        return User(username)

DYNREACT_LOGO = "img/dynreact_logo2.png"
DYNREACT_LOGO_SMALL = "img/dynreact_cropped.jpg"
DYNREACT_BACKGROUND = "img/dynreact.png"
translations_key = "menu"


def _layout():
    # init_stores(*args, **kwargs)  # it seems that arguments are not passed to the global layout function
    prov = state.get_snapshot_provider()
    is_importer = hasattr(prov, "next_scheduled_import")
    #if is_importer:  # add a submenu for snapshot imports
    snap_links = [dcc.Link("Snapshot", id="menu-snaps_header-1", className="menu-link login-required", href="/dash/", title="Open snapshots tab"),
                  dcc.Link("Lots", id="menu-snaps_gantt_header", className="menu-link login-required", href="/dash/lots-gantt", title="Open lots tab")
                            #dcc.Link("Imports", id="menu-snaps-import_header", className="menu-link", href="/dash/imports", title="Snapshot imports")
                ]
    if is_importer:
        snap_links.append(dcc.Link("Imports", id="menu-snaps-import_header", className="menu-link", href="/dash/imports", title="Snapshot imports"))
    snapshot_link = html.Div([
                    html.Div([
                        html.Div("Snapshot", id="menu-snaps_header"),
                        html.Div(snap_links, className="submenu-content")
                    ])
                ], className="menu-link login-required", title="Open snapshots tab")
    mtp_links = [dcc.Link("Lots planned", id="menu-lots-planned_header", className="menu-link", href="/dash/lots/planned", title="Lots planned"),
                dcc.Link("Lot creation", id="menu-lots2-creation_header", className="menu-link", href="/dash/lots/create2", title="Lots creation (new)")]
    if state.has_batch_mtp():
        mtp_links.append(dcc.Link("Batch job", id="menu-snaps-batch_header", className="menu-link", href="/dash/lots/batch", title="Lot creation batch jobs"))
    if config.temporary_restrictions is not None:
        mtp_links.append(dcc.Link("Temporary restrictions", id="menu-temp-rest-header", className="menu-link", href="/dash/lots/temprest", title="Temporary equipment restrictions"))
    mtp_links.append(dcc.Link("Order backlog", id="menu-lots-backlog-header", className="menu-link", href="/dash/lots/backlog", title="Order backlog view"))
    mtp_links.append(dcc.Link("Timeseries plot", id="menu-tsplot-header", className="menu-link", href="/dash/lots/ts-plots", title="Timeseries plots"))
    moa_link = None
    if state.has_material_order_allocation_page():
        moa_link = dcc.Link("Material-order allocation", id="menu-moa_header", className="menu-link login-required", href="/dash/moa", title="Open material order allocation tab")

    performance_pages = [dcc.Link("Equipment models", id="menu-perf-equipment_header", className="menu-link", href="/dash/perfmodels", title="Open equipment performance models tab"),
                    dcc.Link("Energy", id="menu-perf-energy_header", className="menu-link", href="/dash/perfmodels/energy", title="Open energy performance models tab")]
    if len(state.energy_prediction_types()) > 0:
        performance_pages.append(dcc.Link("Energy2", id="menu-perf-energy2_header", className="menu-link", href="/dash/perfmodels/energy2", title="Open energy performance models tab"))
    menu_entries = [
        dcc.Link("Site", id="menu-site_header", className="menu-link login-required", href="/dash/site", title="Site"),
        #dcc.Link("Long term planning", id="menu-ltp_header", className="menu-link login-required", href="/dash/ltp", title="Open long term planning tab"),
        html.Div([
            html.Div([
                html.Div("Long term planning", id="menu-ltp_header"),
                html.Div([
                    dcc.Link("Results", id="menu-ltp-planned_header", className="menu-link", href="/dash/ltp/planned", title="Long term planning results"),
                    dcc.Link("Long term planning", id="menu-ltp-new_header", className="menu-link", href="/dash/ltp", title="Open long term planning tab"),
                    dcc.Link("Equipment performance", id="menu-ltp-perf_header", className="menu-link", href="/dash/ltp/performance", title="Open equipment performance tab")
                ], className="submenu-content")
            ]),
        ], className="menu-link login-required", title="Open long term planning tab"),
        moa_link,
        #dcc.Link("Lot creation", id="menu-lots_header", className=["menu-link"], href="/dash/lots", title="Open lot creation tab"),
        html.Div([
                html.Div([
                    html.Div("Lot creation", id="menu-lots_header"),
                    html.Div(mtp_links, className="submenu-content")
                ]),

                #html.Select([
                #  html.Option(label="test", value="test", selected=False)
                #], id="menu-lots-selector")
            ], className="menu-link login-required", title="Open lot creation tab"),
        dcc.Link("Short term planning", id="menu-agents_header", className="menu-link login-required",
                 href="/dash/stp", title="Open short term planning tab"),
        snapshot_link,
        html.Div([
            html.Div([
                html.Div("Performance models", id="menu-perf_header"),
                html.Div(performance_pages, className="submenu-content")
            ]),
        ], className="menu-link login-required", title="Open plant performance models tabs"),
        html.Div(id="menu-user_header"),
        html.Div([
            html.Img(src="/dash/assets/icons/globe.svg", role="img"),
            dcc.Dropdown(id="menu-lang-select", options=[{"label": "English", "value": "en"},
                                                                     {"label": "Deutsch", "value": "de"},
                                                                     {"label": "Español", "value": "es"}],
                                     persistence=True)],  # , persisted_props="value"
            className="lang-selector", title="Select the language"),
    ]
    menu_container = html.Div([
        dcc.Location(id="menu-url"),
        language,
        snapshot_update_active,
        #dcc.Store(id="lang2", storage_type="memory"),
        dcc.Store(id="lang3", storage_type="memory"),  # dummy output for client side callbacks?
        # dcc.Store(id="client-tz", storage_type="memory", data="UTC"),  # Initialize with UTC, will be overridden by client
        site, selected_snapshot, selected_process, selected_snapshot_obj, selected_snapshot_prev, selected_snapshot_next,
        #html.Div("DynReAct", className="dynreact-header"),
        html.Img(src=app.get_asset_url(DYNREACT_LOGO), className="menu-logo"),
        html.Img(src=app.get_asset_url(DYNREACT_LOGO_SMALL), className="menu-logo menu-logo-small"),
        html.Img(src=app.get_asset_url(DYNREACT_BACKGROUND), className="menu-background"),
        html.Div(menu_entries, id="main-menu", className="main-menu")
    ],
    className="menu-container", id="menu")  # id should match outer key in translation file
    # see https://dash.plotly.com/urls#query-strings
    page_container = dash.page_container
    layout_menu = html.Div([menu_container, page_container], className="main-container")
    return layout_menu


app.layout = _layout()


@callback(
        Output("main-menu", "className"),
          Output("menu-user_header", "children"),
          Output("menu-user_header", "className"),
          Input("menu-url", "pathname"))
def update_user_tab(path: str):
    user_header = None
    user_class_name = "menu-link"
    main_menu_class = "main-menu"
    links_class_name = "menu-link"
    if config.auth_method is None:
        user_class_name = "hidden"
    elif current_user.is_authenticated:
        user_title = "Show user information and logout button"
        user_value = "User"
        user_header = dcc.Link(user_value, href="/dash/user", title=user_title)
    else:
        user_title = "Open login page"
        login_value = "Login"
        user_header = dcc.Link(login_value, href="/dash/login", title=user_title)
        main_menu_class = "main-menu logged-out"
    return main_menu_class, user_header, user_class_name


clientside_callback(
    ClientsideFunction(
        namespace="dynreact",
        function_name="setSnapshot"
    ),
    Output("menu", "title"),
    # XXX this is a workaround, otherwise the callback does not trigger for pages other than snapshot page
    # This is likely a Dash bug
    Input("menu-lots_header", "children"),
    Input("selected-snapshot-obj", "data"),
    State("site-store", "data"),
)



@callback(
    Output("selected-snapshot", "data"),
    Output("selected-snapshot-obj", "data"),
    Input("menu-url", "search"),
    # interestingly, missing input elements are not a problem
    Input({"role": "snapshot-selector", "page": ALL}, "data"),
    State("selected-snapshot", "data"),
    ## would be really useful, but breaks pages without these snapshot selectors => need workaround with store snapshot-update-active
    #running=[
    #    (Output({"role": "snapshot-prev-selector", "page": ALL}, "disabled"), True, False),
    #    (Output({"role": "snapshot-next-selector", "page": ALL}, "disabled"), True, False),
    #]
    running=[(Output("snapshot-update-active", "data"), True, False)]
)
def snapshot_params_changed(params: str|None, user_set_snapshots: Sequence[str|None]|None, old_snapshot: str|None):
    """
    Setting shared state between pages
    """
    changed = GuiUtils.changed_ids()
    user_snapshot_selection = next((_id for _id in changed if "\"snapshot-selector\"" in _id), None)
    user_selected_snapshot = user_snapshot_selection is not None
    if user_selected_snapshot:
        changed_id = json.loads(user_snapshot_selection)
        changed_page = changed_id.get("page")
        user_snap_inputs: Sequence[dict[str, dict[str, str]]] = callback_context.inputs_list[1]
        changed_idx = next((idx for idx, inp in enumerate(user_snap_inputs) if inp is not None and "id" in inp and inp["id"].get("page") == changed_page), None)
        if changed_idx is not None and changed_idx < len(user_set_snapshots):
            snapshot = user_set_snapshots[changed_idx]
            if snapshot == old_snapshot and snapshot is not None:
                return dash.no_update, dash.no_update
        else:
            return dash.no_update, dash.no_update
    elif params is None or len(params) == 0:
        snapshot = dash.no_update
    else:
        params = params[1:]
        params_dict: dict[str, str] = {arr[0].lower(): arr[1] for arr in (val.split("=") for val in params.split("&")) if len(arr) == 2 and len(arr[0]) > 0}
        snapshot = params_dict.get("snapshot") or dash.no_update
    if snapshot == old_snapshot:
        snapshot = dash.no_update
    snap = dash.no_update
    if snapshot == dash.no_update and old_snapshot is None:
        ## init snapshot
        snap = state.get_snapshot()
        snapshot = GuiUtils.format_snapshot(snap.timestamp, None, state=state) if snap is not None else None
    elif snapshot != dash.no_update:
        snap = state.get_snapshot(DatetimeUtils.parse_date(snapshot))
        snapshot = GuiUtils.format_snapshot(snap.timestamp, None, state=state) if snap is not None else None
    if snap != dash.no_update and snap is not None:
        lots: dict[int, Sequence[Lot]] = snap.lots
        snap = snap.model_dump(mode="json", exclude_none=True, exclude_unset=True)
        lots_copy = {}
        snap_provider = state.get_snapshot_provider()
        for eq, eq_lots in lots.items():
            new_lots = []
            lots_copy[eq] = new_lots
            for lot in eq_lots:
                dump = lot.model_dump(mode="json", exclude_unset=True, exclude_none=True)
                dump["lot_complete"] = snap_provider.is_lot_complete(lot)
                new_lots.append(dump)
            lots_copy[eq] = new_lots
        snap["lots"] = lots_copy
    return snapshot, snap


@callback(
    Output("selected-process", "data"),
    Input("menu-url", "search"),
    Input({"role": "process-selector", "page": ALL}, "value"),
    State("selected-process", "data"),
)
def process_params_changed(params: str|None, user_set_processes: Sequence[str|None]|None, old_process: str|None):
    """
    Setting shared state between pages
    """
    changed = GuiUtils.changed_ids()
    user_proc_selection = next((_id for _id in changed if "\"process-selector\"" in _id), None)
    user_selected_procs = user_proc_selection is not None
    explicitly_set = False
    process = old_process
    if user_selected_procs:
        changed_id = json.loads(user_proc_selection)
        changed_page = changed_id.get("page")
        user_proc_inputs: Sequence[dict[str, dict[str, str]]] = callback_context.inputs_list[1]
        changed_idx = next((idx for idx, inp in enumerate(user_proc_inputs) if inp is not None and "id" in inp and inp["id"].get("page") == changed_page), None)
        if changed_idx is not None and changed_idx < len(user_set_processes):
            process = user_set_processes[changed_idx]
            explicitly_set = process is not None
    if not explicitly_set and params is not None and len(params) > 0:
        params = params[1:]
        params_dict: dict[str, str] = {arr[0].lower(): arr[1] for arr in (val.split("=") for val in params.split("&")) if len(arr) == 2 and len(arr[0]) > 0}
        process = params_dict.get("process") or old_process
    if process is None:
        process = old_process or state.get_site().processes[0].name_short
    return dash.no_update if process == old_process else process


@callback(
    Output({"role": "snapshot-prev-selector", "page": ALL}, "disabled"),
    Output({"role": "snapshot-next-selector", "page": ALL}, "disabled"),
    Input("snapshot-update-active", "data"),
    State({"role": "snapshot-prev-selector", "page": ALL}, "id"),)
def update_running(running: bool, ids: Sequence[str]):
    return [running for _id in ids], [running for _id in ids]


@callback(
    Output("selected-snapshot-next", "data"),
    Output("selected-snapshot-prev", "data"),
    Input("selected-snapshot", "data"),
)
def set_next_prev_snaps(snapshot: str|None):
    snapshot = DatetimeUtils.parse_date(snapshot)
    if snapshot is None:
        return None, None
    sp = state.get_snapshot_provider()
    delta = timedelta(minutes=1)
    next_t = snapshot + delta
    next_snap = sp.next(next_t)
    while next_snap is not None and next_snap <= snapshot:
        next_t = next_t + delta
        next_snap = sp.next(next_t)
    prev_t = snapshot - delta
    prev_snap = sp.previous(prev_t)
    while prev_snap is not None and prev_snap >= snapshot:
        prev_t = prev_t - delta
        prev_snap = sp.previous(prev_t)
    if next_snap is not None:
        next_snap = state.as_timezone(next_snap)
    if prev_snap is not None:
        prev_snap = state.as_timezone(prev_snap)
    return next_snap, prev_snap


def _get_snapshot(snapshot_id: str|None) -> Snapshot|None:
    time = DatetimeUtils.parse_date(snapshot_id)
    return state.get_snapshot(time)


# Looks circular, but apparently it is possible...
"""
@callback(Output("lang", "data"),
          Output("lang-select", "value"),
          State("menu-url", "search"),
          Input("lang-select", "value"))
def set_lang(search: str, value: str):
    if value is not None and len(value) > 0:
        return value, dash.no_update
    if search is not None and search.startswith("?"):
        search = search[1:]
        for params in search.split("&"):
            key_val = params.split("=")
            if len(key_val) != 2 or key_val[0].lower() != "lang":
                continue
            value = key_val[1].strip().lower()
            return value, value
    return "en", "en"
"""

clientside_callback(
    ClientsideFunction(
        namespace="locale",
        function_name="setLocale"
    ),
    Output("lang", "data"),
    Output("menu-lang-select", "value"),
    Input("menu-lang-select", "value"),
    Input("menu-url", "href"),
    State("lang", "data")
)

# Set client timezone once on page load
#@app.callback(
#    Output("client-tz", "data"),
#    Input("menu-url", "pathname"),
#    prevent_initial_call=False
#)
#def init_timezone(pathname):
#    # Return default timezone - client will override via JavaScript if needed
#    return "UTC"


if __name__ == "__main__":
    app.run(debug=True, dev_tools_ui=True)
