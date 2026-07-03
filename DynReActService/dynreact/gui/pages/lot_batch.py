"""
Module lot_batch
"""
from datetime import datetime

import dash
from dash import html, callback, Output, Input, dcc, State

from dynreact.app import state, config
from dynreact.auth.authentication import dash_authenticated
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.monitoring import LotsBatchJobStatistics
from dynreact.gui.gui_utils import GuiUtils

dash.register_page(__name__, path="/lots/batch")
translations_key = "lotbatch"


def layout(*args, **kwargs):
    if not state.has_batch_mtp():
        return html.H1("Not found")
    return html.Div([
        html.H1("Lot creation batch execution"),
        html.H2("Batch job status"),
        html.Div([
            html.Span("Batch lot creation active:"), html.Span(id="lotbatch-active"), html.Span(),
            html.Span("Trigger::"), html.Div([html.Button("Run", id="lotbatch-trigger", className="dynreact-button", disabled=True, title="Run the batch lot creation.")]), html.Span(),
            html.Span("Previous execution:"), html.Span(id="lotbatch-prev-exec"), html.Span(),
            html.Span("Previous snapshot:"), html.Span(id="lotbatch-prev-snap"), html.Span(),
            html.Span("Next planned execution:"), html.Span(id="lotbatch-next-exec"), html.Span(),
            html.Span("Solution:"), dcc.Dropdown(id="lotbatch-sol-select", style={"min-width": "12em"}), html.Span()
        ], className="lotbatch-prev-grid"),
        html.H2("Processes"),
        html.Div(id="lotbatch-processes-table", className="lotbatch-proc-table"),
        dcc.Interval(id="lotbatch-interval", interval=30_000),
    ])


@callback(
    Output("lotbatch-active", "children"),
          Output("lotbatch-trigger", "disabled"),
          Output("lotbatch-prev-exec", "children"),
          Output("lotbatch-prev-snap", "children"),
          Output("lotbatch-next-exec", "children"),
          Output("lotbatch-sol-select", "options"),
          Output("lotbatch-sol-select", "value"),
          #Output("lotbatch-processes-table", "children"),
          Output("lotbatch-interval", "interval"),
          Input("lotbatch-interval", "n_intervals"),
          Input("lotbatch-trigger", "n_clicks"),
          State("lotbatch-sol-select", "value"),)
def set_stats(_, clicks: int|None, selected_solution: datetime|None):
    if not dash_authenticated(config):
        return None, True, None, None, None, None, None, 3_600_000
    stats: LotsBatchJobStatistics = state.get_batch_mtp_data()
    prev = DatetimeUtils.format(state.as_timezone(stats.previous_invocation), use_zone=False) if stats.previous_invocation is not None else None
    nxt = DatetimeUtils.format(state.as_timezone(stats.next_invocation), use_zone=False) if stats.next_invocation is not None else None
    snap = DatetimeUtils.format(state.as_timezone(stats.previous_snapshot), use_zone=False) if stats.previous_snapshot is not None else None
    active = stats.is_active
    proc_results = stats.previous_process_results
    sol_options = None
    trigger_run = "lotbatch-trigger" in GuiUtils.changed_ids() and clicks is not None and clicks > 0 and not active
    if proc_results:
        solutions = sorted(list(proc_results.keys()), reverse=True)
        sol_options = [{"value": sol, "label": DatetimeUtils.format(sol, use_zone=False).replace("T", " ")} for sol in solutions]
        selected_solution = selected_solution if selected_solution is not None and any(opt["value"] == selected_solution for opt in sol_options) else sol_options[0]["value"]
    else:
        selected_solution = None
    if trigger_run:
        active = state.run_batch_mtp()
    return str(active), active, prev, snap, nxt, sol_options, selected_solution, 5_000 if active else 30_000

@callback(
   Output("lotbatch-processes-table", "children"),
          Input("lotbatch-sol-select", "value"))
def set_process_table(solution: str|None):
    stats: LotsBatchJobStatistics = state.get_batch_mtp_data()
    if not dash_authenticated(config) or not solution or not stats:
        return None
    proc_results = stats.previous_process_results.get(datetime.fromisoformat(solution))
    if not proc_results:
        return None
    children = []
    site = state.get_site()
    if proc_results is not None and len(proc_results) > 0:
        children.extend([html.Span("Process"), html.Span("Lots created"), html.Span("Link"), html.Span("Equipment"), html.Span("Backlog orders"), html.Span("Orders assigned"),
                         html.Span("Backlog tons"), html.Span("Tons assigned"), html.Span("Objective value", title="Also known as \"virtual costs\""), html.Span("Duration/min"), html.Span("Reason")])
        for proc, results in proc_results.items():
            proc_obj = site.get_process(proc, do_raise=True)
            equipment = [site.get_equipment(eq, do_raise=True) for eq in results.equipment]
            equipment_names = [eq.name or eq.name_short or str(eq.id) for eq in equipment]
            reason = "An error occurred" if results.errors > 0 else "Not enough material for lot creation" if results.missing_material \
                    else "Existing lots exceed planning horizon" if results.lots_exceed_planning_horizon else ""
            href = f"/dash/lots/planned?snapshot={DatetimeUtils.format(state.as_timezone(stats.previous_snapshot), use_zone=True)}&process={proc}&solution={results.solution_id}"
            link = dcc.Link("Results", href=href, target="_blank", title="Open results in new tab") if results.lots_created > 0 else html.Span()
            children.extend([html.Span(proc, title=proc_obj.name or proc_obj.name_short),
                 html.Span(f"{results.lots_created}"), link, html.Span(f"{equipment_names}"), html.Span(f"{results.order_backlog_count}"),
                 html.Span(f"{results.orders_assigned}"), html.Span(f"{results.order_backlog_tons:.4g}"), html.Span(f"{results.tons_assigned:.4g}"),
                 html.Span(f"{results.objective_value:.4g}"), html.Span(round(results.duration.total_seconds()/60)), html.Span(reason)])
    return children


