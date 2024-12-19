import dash
from dash import html, dcc, callback, Input, Output, State

from dynreact.gui.localization import Localization
from dynreact.gui.pages.session_state import language

dash.register_page(__name__, path="/user")
translations_key = "user"


def layout(*args, **kwargs):
    return html.Div(
    [
        dcc.Location(id="url-user"),
        html.H2("User information", id="logout-title"),
        html.Div([
            html.Div("User: "),
            html.Div("", id="current-user"),
            html.Div(html.Button(children="Logout", type="submit", id="logout-button", title="Click to logout")),
        ], className="logout-row"),
        html.Div(id="success-indicator-logout"),
        language
    ]
)

@callback(
    Output("current-user", "children"),
    Input("url-user", "pathname")
)
def login_button_click(_):
    from flask_login import current_user
    if current_user.is_authenticated:
        return current_user.id
    return None


@callback(
    Output("url-user", "pathname"),
    Input("logout-button", "n_clicks"),
    prevent_initial_call=True,
)
def logout_button_click(n_clicks):
    from flask_login import logout_user
    logout_user()
    # TODO maintain language selection(?)
    return "/dash/login"


# Localization
@callback(Output("logout-title", "children"), Output("logout-button", "title"), Input("lang", "data"))
def update_locale(lang: str):
    translation: dict[str, str]|None = Localization.get_translation(lang, translations_key)
    title = Localization.get_value(translation, "title", "User information")
    logout_btn_title = Localization.get_value(translation, "logout_title", "Click to logout")
    return title, logout_btn_title

