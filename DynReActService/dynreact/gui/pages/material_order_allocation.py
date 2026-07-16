from typing import Callable

import dash
from dash import html
from dynreact.app import config, state

dash.register_page(__name__, path="/moa")
translations_key = "moa"

# Preload the configured MOA frontend once during page module import so any
# callbacks declared in that module are registered before Dash serves `/_dash-dependencies`.
if config.material_order_allocation_frontend:
    state.get_material_order_allocation_page()


def layout(*args, **kwargs):
    pg = state.get_material_order_allocation_page()
    if pg is None:
        return html.H1("Page not found")
    if isinstance(pg, Callable):
        return pg(*args, **kwargs)
    return pg

