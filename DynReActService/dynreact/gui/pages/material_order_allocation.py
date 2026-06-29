from typing import Callable

import dash
from dash import html#
from dynreact.app import state

dash.register_page(__name__, path="/moa")
translations_key = "moa"


def layout(*args, **kwargs):
    pg = state.get_material_order_allocation_page()
    if pg is None:
        return html.H1("Page not found")
    if isinstance(pg, Callable):
        return pg(*args, **kwargs)
    return pg

