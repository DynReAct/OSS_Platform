"""
Module stp_page

This is a proxy to the actual short term planning frontend, which is loaded dynamically.
If not specified otherwise, the delegate is taken from dynreact.gui_stp.agentsPage.py, but if
the environment variable STP_FRONTEND is set to a module name, such as "dynreact.stp_gui.my_module"
(expecting a file "my_module.py"), then the proxy will try to load this module and retrieve a contained layout
field or function to which it delegates its own layout call.
"""

from typing import Callable

import dash
from dash import html

from dynreact.app import state

dash.register_page(__name__, path="/stp")
pg = state.get_stp_page()


def layout(*args, **kwargs):
    if pg is None:
        return html.H1("Not found")
    if isinstance(pg, Callable):
        return pg(*args, **kwargs)
    return pg

