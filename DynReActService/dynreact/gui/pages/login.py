import dash
from dash import html, dcc, callback, Input, Output, State

from dynreact.app import config
from dynreact.auth.authentication import authenticate
from dynreact.gui.localization import Localization

dash.register_page(__name__, path="/login")
translations_key = "login"


def layout(*args, **kwargs):
    return html.Div(
    [
        dcc.Location(id="login-url"),
        html.H2("Please log in:", id="login-title"),
        html.Div([
            dcc.Input(placeholder="Enter your username", type="text", id="login-username"),
            dcc.Input(placeholder="Enter your password", type="password", id="login-password"),
            html.Button(children="Login", type="submit", id="login-button"),
        ], className="login-row"),
        html.Div(id="login-success-indicator"),
    ], id="login"
)

@callback(
    Output("login-success-indicator", "children"),
    Output("login-url", "pathname"),
    Input("login-button", "n_clicks"),
    State("login-username", "value"),
    State("login-password", "value"),
    State("lang", "data"),  # TODO!
    prevent_initial_call=True,  # is this a problem maybe?
)
def login_button_click(n_clicks, username: str, password: str, lang: str):
    if username is not None and authenticate(config, username, password):
        from flask_login import login_user
        from dynreact.gui.pages.session_state import User
        login_user(User(username))
        # redirect
        return None, "/dash"  # "Login successful", "/dash"
    translation: dict[str, str] | None = Localization.get_translation(lang, translations_key)
    login_failed_msg = Localization.get_value(translation, "login_failed", "Login failed")
    return login_failed_msg, None

