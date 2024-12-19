import dash
from dash import html, dcc, callback, Input, Output, State
import dash_cytoscape as cyto
from dynreact.base.model import Site, Equipment, Storage, Process

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.gui.pages.plants_graph import plants_graph
from dynreact.gui.pages.session_state import language

dash.register_page(__name__, path="/site")
translations_key = "site"


# TODO processes graph and plants/storages graph

def layout(*args, **kwargs):
    #lang = language.data if hasattr(language, "data") else "en"
    if not dash_authenticated(config):
        return None
    return html.Div([
        dcc.Location(id="site-url", refresh=False),
        html.H1("Site", id="site-header"),
        html.Div(id="mouseover-content"),
        plants_graph("site-plants_graph", *args, **kwargs)
    ], id="site")


# TODO make this a clientside callback, to be able to position a tooltip
@callback(Output("mouseover-content", "children"),
              Input("site-plants_graph", "mouseoverNodeData"))
def mouse_over(data):
    if data:
        return "You recently hovered over the plant: " + data["label"]

