import json
from typing import Sequence

from dash import html, callback, Output, ALL, Input, dcc, State, clientside_callback, ClientsideFunction
import dash
import dash_ag_grid as dash_ag

from dynreact.app import config, state
from dynreact.auth.authentication import dash_authenticated
from dynreact.base.TemporaryRestrictionsProvider import EquipmentRestriction, RestrictionUtils
from dynreact.base.conditions import MaterialCondition, PropertyCondition, ThresholdCondition, ListCondition, \
    RangeCondition
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Site, Order
from dynreact.gui.gui_utils import GuiUtils

if config.temporary_restrictions:
    dash.register_page(__name__, path="/lots/temprest")
translations_key = "temprest"


def layout(*args, **kwargs):
    temp_rest = state.get_temporary_restrictions()
    if not temp_rest:
        return html.Div(html.H1("404 - Temporary restrictions not found"))
    site = state.get_site()
    restrictions: Sequence[tuple[EquipmentRestriction, bool]] = temp_rest.equipment_restrictions()
    grid_body = []
    grid = [ # html.Caption("Temporary equipment restrictions"),
            html.Thead(html.Tr([
                html.Th("Rule", scope="col", title="Name of the rule", id="temprest-grid-rule"),
                html.Th("Explanation", scope="col", title="Explanation of the rule", style={"min-width": "25em"}, id="temprest-grid-explanation"),
                html.Th("Equipment", scope="col", title="Equipment affected by the rule", id="temprest-grid-equipment"),
                html.Th("Material filter", scope="col", title="Does the rule apply to a specific material class?", id="temprest-grid-mat"),
                html.Th("Property filter", scope="col", title="Does the rule apply to specific order properties?", id="temprest-grid-prop"),
                html.Th("Active", scope="col", title="Is the rule currently active?", id="temprest-grid-active"),
                html.Th("Toggle", scope="col", title="Toggle the active status of the rule", id="temprest-grid-toggle")
            ])),
            html.Tbody(grid_body)
    ]
    rule_options = []
    for rst, active in restrictions:
        material_filter = "" if not isinstance(rst.condition, MaterialCondition) else rst.condition.material_class
        order_attribute = ""
        if isinstance(rst.condition, PropertyCondition):
            order_attribute = rst.condition.attribute + " "
            if isinstance(rst.condition, ThresholdCondition):
                order_attribute += rst.condition.operator + " " + str(rst.condition.value)
            elif isinstance(rst.condition, ListCondition):
                order_attribute += rst.condition.operator + " [" + ", ".join(rst.condition.values) + "]"
            elif isinstance(rst.condition, RangeCondition):
                order_attribute += str(rst.condition.value_range[0]) + " " + rst.condition.operators[0] + \
                    " x " + rst.condition.operators[1] + str(rst.condition.value_range[1])
        equipment = rst.equipment
        if isinstance(equipment, Sequence):
            equipment_texts = [_equipment_text(e, site) for e in equipment]
            equipment_text = ", ".join([label for label, title in equipment_texts])
            equipment_title = ", ".join([title for label, title in equipment_texts if title is not None])
        else:
            equipment_text, equipment_title = _equipment_text(equipment, site)
        active_text = "✔" if active else "✖"
        active_status = "active" if active else "inactive"
        grid_body.append(html.Tr([
                    html.Th(rst.label or rst.id, title=f"Id: {rst.id}", scope="row", className="temprest-cell"),
                    html.Td(rst.description, className="temprest-cell"),
                    html.Td(equipment_text, title="Id: " + equipment_title, className="temprest-cell"),
                    html.Td(material_filter, className="temprest-cell"),
                    html.Td(f"{order_attribute}", className="temprest-cell"),
                    html.Td(active_text, id={"role": "temprest-active", "id": rst.id}, className="temprest-cell temprest-" + active_status, title=f"Rule is {active_status}"),
                    html.Td(html.Button("Toggle", id={"role": "temprest-toggle", "id": rst.id}, className="dynreact-button",
                                        title=f"Toggle active status of rule: {rst.label or rst.id}"), className="temprest-cell")
        ]))
        rule_options.append({"value": rst.id, "label": rst.label or rst.id})
    orders_table = dash_ag.AgGrid(
            id="temprest-orders-table",
            columnDefs=[{"field": "id", "pinned": True}],
            rowData=[],
            getRowId="params.data.id",
            className="ag-theme-alpine",  # ag-theme-alpine-dark
            style={"height": "50vh", "width": "95vw", "margin-bottom": "5em"},
            columnSizeOptions={"defaultMinWidth": 125, "defaultMaxWidth": 150},  # important to set, since the sizeToFit is applied the first time when the grid is not visible yet
            columnSize="sizeToFit",   # need to reset this whenever the column definitions change
            #defaultColDef={"tooltipComponent": "CoilsTooltip", "tooltipField": "id"},
            dashGridOptions={"animateRows": False,},
                             #"tooltipShowDelay": 2_000, "tooltipInteraction": True,
                             #"popupParent": {"function": "setCoilPopupParent()"}},
            # "autoSize"  # "responsiveSizeToFit" => this leads to essentially vanishing column size
            getRowStyle = {
                "styleConditions": [{
                    "condition": "params.data.affectedOrder",
                    "style": {"backgroundColor": "sandybrown"},
                }
                #, {
                #    "condition": "params.data.lotStart",
                #    "style": {"backgroundColor": "lightblue"},
                #}, {
                #    "condition": "params.data.unassigned",
                #    "style": {"backgroundColor": "rgba(230, 230, 230)"},
                #}
                ]
            }
        )
    return html.Div([
        html.H1("Temporary restrictions", id="temprest-title"),
        html.H2("Equipment restrictions", id="temprest-header-eq-rest"),
        html.Table(grid, className="temprest-rules-table"),
        html.H2("Orders affected", id="temprest-header-orders"),
        html.Div([
            html.Div([
                html.Span("Rule", title="Select the rule to evaluate on orders", id="temprest-selected-rule-label"),
                dcc.Dropdown(id="temprest-selected-rule", options=rule_options, value=rule_options[0]["value"] if len(rule_options) > 0 else None, style={"min-width": "15em"}),
            ], style={"display": "flex", "column-gap": "1em", "align-items": "center"}),
            html.Br(),
            orders_table
        ]),
        html.Dialog(id="temprest-error-dialog", className="dialog-filled temprest-dialog", open=False),
        dcc.Store(id="temprest-error-msg", storage_type="memory")   # {type: ...,  msg: ...}
    ], id="temprest")


@callback(Output({"role": "temprest-active", "id": ALL}, "children"),
         Output({"role": "temprest-active", "id": ALL}, "className"),
         Output({"role": "temprest-active", "id": ALL}, "title"),
         Output("temprest-error-msg", "data"),
         Input({"role": "temprest-toggle", "id": ALL}, "n_clicks"),
         running=[
              (Output({"role": "temprest-toggle", "id": ALL}, "disabled"), True, False),
         ],
         config_prevent_initial_callbacks=True)
def toggle(clicks):
    changed = GuiUtils.changed_ids(excluded_ids=("",))
    if len(changed) == 0 or not dash_authenticated(config):
        return None, None, None, None
    triggered = json.loads(changed[0])["id"]
    restrictions = state.get_temporary_restrictions()
    active = restrictions.is_active(triggered)
    msg = None
    try:
        restrictions.set_active_status(triggered, not active)
        # msg = {"type": "success", "msg": f"Status toggled: {triggered} = {not active}"}  # the alert is too ugly here
    except Exception as e:
        msg = {"type": "error", "msg": f"Failed to toggle status: {e}"}
    rules_active = [active for _, active in restrictions.equipment_restrictions()]
    status = ["✔" if active else "✖" for active in rules_active]
    classes = ["temprest-cell " + ("temprest-active" if active else "temprest-inactive") for active in rules_active]
    titles = ["Rule is " + ("active" if active else "inactive") for active in rules_active]
    return status, classes, titles, msg

# clientside arguments: msg, type, siblingId, dummyReturnValue
clientside_callback(
    ClientsideFunction(
        namespace="alert",
        function_name="showAlertObj"
    ),
    Output("temprest-title", "title"),
    Input("temprest-error-msg", "data"),
    State("temprest-error-dialog", "id"),
)


def _equipment_text(e: int, site: Site) -> tuple[str, str|None]:
    eq_ob = site.get_equipment(e, do_raise=True)
    label = eq_ob.name or eq_ob.name_short or str(eq_ob.id)
    return label, str(eq_ob.id)


##### Orders ###########

@callback(Output("temprest-orders-table", "columnDefs"),
         Output("temprest-orders-table", "rowData"),
         Input("selected-snapshot", "data"),
         Input("temprest-selected-rule", "value"))
def snapshot_changed(snapshot: str|None, rule_id: str|None):
    snap = DatetimeUtils.parse_date(snapshot)
    snap_obj = state.get_snapshot(time=snap)
    if not snap_obj or not dash_authenticated(config):
        return None
    orders = snap_obj.orders
    temporary_restrictions = state.get_temporary_restrictions()
    rule, active = temporary_restrictions.get_restriction(rule_id)
    relevant_fields = None
    orders_affected: Sequence[str] = tuple()
    if rule is not None:
        if isinstance(rule.condition, PropertyCondition):
            relevant_fields = rule.condition.attribute
        elif isinstance(rule.condition, MaterialCondition):
            if rule.condition.relevant_attributes is not None:
                relevant_fields = list(rule.condition.relevant_attributes) + ["material_classes"]
            else:
                relevant_fields = ("material_classes", )
        equipment = rule.equipment
        if isinstance(equipment, int):
            equipment = (equipment, )

        def order_affected(order: Order) -> bool:
            return any(not RestrictionUtils.equipment_allowed(rule, e, order) for e in equipment)
        # sort orders: affected ones first
        orders_affected = [o.id for o in orders if order_affected(o)]
        orders = sorted(orders, key=lambda order: -1 if order.id in orders_affected else 1)
    cols, rows = GuiUtils.orders_table(orders, state.get_site(), relevant_fields=relevant_fields, skip_selection_checkbox=True)
    if len(orders_affected) > 0:
        for row in rows:
            if row.get("id") in orders_affected:  # set row color
                row["affectedOrder"] = True
    return cols, rows



