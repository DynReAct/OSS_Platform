import dash
from dynreact.gui.perf_energy import layout as delegate_layout

dash.register_page(__name__, path="/perfmodels/energy")


def layout(*args, **kwargs):
    """Render the configured energy page for the active profile."""
    return delegate_layout(*args, **kwargs)
