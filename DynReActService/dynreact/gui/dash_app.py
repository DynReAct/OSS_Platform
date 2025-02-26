import os

import dash
from dash import dcc, html, Output, Input, State, clientside_callback, ClientsideFunction, callback
from flask import Flask


from dynreact.app import config
from dynreact.gui.pages.session_state import language, init_stores, site, selected_snapshot, \
    selected_snapshot_obj, selected_process

server = Flask(__name__)

# requests_pathname_prefix required for operation with FastAPI
app = dash.Dash(__name__, server=server, routes_pathname_prefix="/", requests_pathname_prefix="/dash/",
                assets_folder="assets", suppress_callback_exceptions=False, title="DynReAct",
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
DYNREACT_BACKGROUND = "img/dynreact.png"
translations_key = "menu"


def layout(*args, **kwargs):
    init_stores(*args, **kwargs)
    menu_container = html.Div([
        dcc.Location(id="menu-url"),
        language,
        #dcc.Store(id="lang2", storage_type="memory"),
        dcc.Store(id="lang3", storage_type="memory"),  # dummy output for client side callbacks?
        site, selected_snapshot, selected_snapshot_obj, selected_process,
        #html.Div("DynReAct", className="dynreact-header"),
        html.Img(src=app.get_asset_url(DYNREACT_LOGO), className="menu-logo"),
        html.Img(src=app.get_asset_url(DYNREACT_BACKGROUND), className="menu-background"),
        html.Div([
            dcc.Link("Site", id="menu-site_header", className="menu-link login-required", href="/dash/site", title="Site"),
            #dcc.Link("Long term planning", id="menu-ltp_header", className="menu-link login-required", href="/dash/ltp", title="Open long term planning tab"),
            html.Div([
                html.Div([
                    html.Div("Long term planning", id="menu-ltp_header"),
                    html.Div([
                        dcc.Link("Results", id="menu-ltp-planned_header", className="menu-link", href="/dash/ltp/planned", title="Long term planning results"),
                        dcc.Link("Long term planning", id="menu-ltp-new_header", className="menu-link", href="/dash/ltp", title="Open long term planning tab")
                    ], className="submenu-content")
                ]),
            ], className="menu-link login-required", title="Open long term planning tab"),
            dcc.Link("Coil-order allocation", id="menu-coa_header", className="menu-link login-required", href="/dash/coa", title="Open coil order allocation tab"),
            #dcc.Link("Lot creation", id="menu-lots_header", className=["menu-link"], href="/dash/lots", title="Open lot creation tab"),
            html.Div([
                    html.Div([
                        html.Div("Lot creation", id="menu-lots_header"),
                        html.Div([
                            dcc.Link("Lots planned", id="menu-lots-planned_header", className="menu-link", href="/dash/lots/planned", title="Lots planned"),
                            #dcc.Link("Lot creation", id="menu-lots-creation_header", className="menu-link", href="/dash/lots/create", title="Lots creation"),
                            dcc.Link("Lot creation", id="menu-lots2-creation_header", className="menu-link", href="/dash/lots/create2", title="Lots creation (new)")
                        ], className="submenu-content")
                    ]),

                    #html.Select([
                    #  html.Option(label="test", value="test", selected=False)
                    #], id="menu-lots-selector")
                ], className="menu-link login-required", title="Open lot creation tab"),
            dcc.Link("Short term planning", id="menu-agents_header", className="menu-link login-required", href="/dash/stp", title="Open short term planning tab"),
            dcc.Link("Snapshot", id="menu-snaps_header", className="menu-link login-required", href="/dash/", title="Open snapshots tab"),
            dcc.Link("Performance models", id="menu-perf_header", className="menu-link login-required", href="/dash/perfmodels",
                     title="Open plant performance models tab"),
            html.Div(id="menu-user_header"),
            html.Div([
                html.Img(src="/dash/assets/icons/globe.svg", role="img"),
                dcc.Dropdown(id="menu-lang-select", options=[{"label": "English", "value": "en"}, {"label": "Deutsch", "value": "de"}, {"label": "Español", "value": "es"}])],
                    className="lang-selector", title="Select the language"),
        ], id="main-menu", className="main-menu")
    ],
    className="menu-container", id="menu")  # id should match outer key in translation file
    # see https://dash.plotly.com/urls#query-strings
    page_container = dash.page_container
    layout_menu = html.Div([menu_container, page_container], className="main-container")
    return layout_menu


app.layout = layout


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



# Looks circular, but apparently it is possible...
"""
@callback(Output("lang", "data"), Output("lang-select", "value"), State("menu-url", "search"), Input("lang-select", "value"))
def set_lang(search: str, value: str):
    if value is not None and len(value) > 0:
        return value, value
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
    Input("menu-url", "href")   # problem: this triggers the callback before the new page is loaded
)


if __name__ == "__main__":
    app.run(debug=True, dev_tools_ui=True)
