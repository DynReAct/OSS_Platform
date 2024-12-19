import dash
from dash import html

dash.register_page(__name__, path="/coa")
translations_key = "coa"


def layout(*args, **kwargs):
    return html.Div([
        html.H1("Coil-order allocation", id="coa-title"),
    ], id="coa")

