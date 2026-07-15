import json
from typing import Sequence

from dash import html, callback, Output, ALL, Input, dcc, State, clientside_callback, ClientsideFunction, MATCH, \
    callback_context
import dash
import dash_ag_grid as dash_ag

from dynreact.app import config, state
from dynreact.auth.authentication import dash_authenticated
from dynreact.base.TemporaryRestrictionsProvider import EquipmentRestriction, RestrictionUtils, RuleSettings
from dynreact.base.conditions import MaterialCondition, PropertyCondition, ThresholdCondition, ListCondition, \
    RangeCondition, Condition, CompositeCondition, NotCondition, ConditionUtils
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
    restrictions: Sequence[tuple[EquipmentRestriction, Sequence[RuleSettings]]] = temp_rest.equipment_restrictions()
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
    for rst, settings in restrictions:
        material_filter = "" if not isinstance(rst.condition, MaterialCondition) else rst.condition.material_class
        order_attribute = _print_order_attribute(rst.condition)
        equipment = rst.equipment
        is_rule_configurable: bool = (rst.equipment_selectable and isinstance(rst.equipment, Sequence)) or ConditionUtils.condition_has_parameters(rst.condition)
        equipment_as_list = [rst.equipment] if not isinstance(rst.equipment, Sequence) else rst.equipment
        equipment_selector = html.Div(dcc.Dropdown(options=[{"value": e, "label": _equipment_text(e, site)[0]} for e in equipment_as_list], value=[], multi=True, style={"min-width": "12em"},
                                              id={"role": "temprest-equipment-selector", "id": rst.id}), hidden=not rst.equipment_selectable) if is_rule_configurable else None
        dummy_selector = equipment_selector if equipment_selector is not None and not rst.equipment_selectable else None
        if isinstance(equipment, Sequence):
            if rst.equipment_selectable:
                equipment_text = equipment_selector
                equipment_title="Select equipment"
                if len(settings) > 0:
                    equipment_selector.children.value = settings[0].active_equipment
            else:
                equipment_texts = [_equipment_text(e, site) for e in equipment]
                equipment_text = ", ".join([label for label, title in equipment_texts])
                equipment_title = ", ".join([title for label, title in equipment_texts if title is not None])
        else:
            equipment_text, equipment_title = _equipment_text(equipment, site)
        active = settings and len(settings) > 0
        active_text = "✔" if active else "✖"
        active_status = "active" if active else "inactive"
        active_role = "temprest-active" if not is_rule_configurable else "temprest-cfg-active"
        msg_role = "temprest-error-msg" if not is_rule_configurable else "temprest-cfg-error-msg"

        grid_body.append(html.Tr([
                    html.Th(rst.label or rst.id, title=f"Id: {rst.id}", scope="row", className="temprest-cell"),
                    html.Td(rst.description, className="temprest-cell"),
                    html.Td(equipment_text, title="Id: " + equipment_title, className="temprest-cell"),
                    html.Td(material_filter, className="temprest-cell"),
                    html.Td(order_attribute, className="temprest-cell"),
                    html.Td(active_text, id={"role": active_role, "id": rst.id}, className="temprest-cell temprest-" + active_status, title=f"Rule is {active_status}"),
                    html.Td([
                        html.Button("Toggle" if not is_rule_configurable else "Save", className="dynreact-button",
                                    id={"role": "temprest-toggle" if not is_rule_configurable else "temprest-save", "id": rst.id},
                                    title=f"Toggle active status of rule: {rst.label or rst.id}" if not is_rule_configurable else "Save changes"),
                        dcc.Store(id={"role": msg_role, "id": rst.id},),
                        dummy_selector
                    ], className="temprest-cell")
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



@callback(Output({"role": "temprest-active", "id": MATCH}, "children"),
         Output({"role": "temprest-active", "id": MATCH}, "className"),
         Output({"role": "temprest-active", "id": MATCH}, "title"),
         Output({"role": "temprest-error-msg", "id": MATCH}, "data"),   # could be a problem with MATCH? Need one per entry?
         Input({"role": "temprest-toggle", "id": MATCH}, "n_clicks"),
         running=[  # TODO here we could enable ALL by using an intermediate store maybe
              (Output({"role": "temprest-toggle", "id": MATCH}, "disabled"), True, False),
         ],
         config_prevent_initial_callbacks=True)
def toggle_rule_nonconfigurable(clicks):
    changed = GuiUtils.changed_ids(excluded_ids=("",))
    if len(changed) == 0 or not dash_authenticated(config):
        return None, None, None, None
    triggered = json.loads(changed[0])["id"]
    restrictions = state.get_temporary_restrictions()
    rule, settings = restrictions.get_restriction(triggered)
    if not rule:
        msg = {"type": "error", "msg": f"Rule {triggered} unknown"}
    else:
        active = settings and len(settings) > 0
        msg = None
        try:
            if not active:
                restrictions.activate(triggered, RuleSettings(active=True))
            else:
                restrictions.deactivate(triggered)
        except Exception as e:
            msg = {"type": "error", "msg": f"Failed to toggle status: {e}"}
    rule_active = restrictions.is_active(triggered)
    status = "✔" if rule_active else "✖"
    clazz = "temprest-cell " + ("temprest-active" if rule_active else "temprest-inactive")
    title = "Rule is " + ("active" if rule_active else "inactive")
    return status, clazz, title, msg

@callback(
         Output("temprest-error-msg", "data"),
         Input({"role": "temprest-error-msg", "id": ALL}, "data"))
def error_msg_changed(messages):
    changed = GuiUtils.changed_ids(excluded_ids=("",))
    if len(changed) == 0:
        return None
    message_inputs: Sequence[dict[str, dict[str, str]]] = callback_context.inputs_list[0]
    changed_id = json.loads(changed[0])["id"]
    changed_idx = next((idx for idx, inp in enumerate(message_inputs) if
                        inp is not None and "id" in inp and inp["id"].get("id") == changed_id), None)
    return None if changed_idx is None else messages[changed_idx]


@callback(Output({"role": "temprest-cfg-active", "id": MATCH}, "children"),
         Output({"role": "temprest-cfg-active", "id": MATCH}, "className"),
         Output({"role": "temprest-cfg-active", "id": MATCH}, "title"),
         Output({"role": "temprest-cfg-error-msg", "id": MATCH}, "data"),
         Input({"role": "temprest-save", "id": MATCH}, "n_clicks"),
         State({"role": "temprest-equipment-selector", "id": MATCH}, "value"),
         running=[  # TODO here we could enable ALL by using an intermediate store maybe
              (Output({"role": "temprest-save", "id": MATCH}, "disabled"), True, False),
         ],
         config_prevent_initial_callbacks=True)
def save_rule_configurable(clicks, selected_equipment: list[int]|None):
    changed = GuiUtils.changed_ids(excluded_ids=("",))
    # FIXME
    print("   SAVING configurable rule", changed)
    if len(changed) == 0 or not dash_authenticated(config):
        return None, None, None, None
    # FIXME
    print("   EQUIPMENT selected", selected_equipment)
    triggered = json.loads(changed[0])["id"]
    restrictions = state.get_temporary_restrictions()
    rule, settings = restrictions.get_restriction(triggered)
    if not rule:
        msg = {"type": "error", "msg": f"Rule {triggered} unknown"}
    else:
        active = settings and len(settings) > 0
        equipment_configurable: bool = rule.equipment_selectable and isinstance(rule.equipment, Sequence) and len(rule.equipment) > 1
        has_parameters: bool = ConditionUtils.condition_has_parameters(rule.condition)
        msg = None
        active = len(selected_equipment) > 0
        new_settings = RuleSettings(active=active, active_equipment=selected_equipment)
        try:
            restrictions.activate(triggered, new_settings, rule_index=0)
            # msg = {"type": "success", "msg": f"Status toggled: {triggered} = {not active}"}  # the alert is too ugly here
        except Exception as e:
            msg = {"type": "error", "msg": f"Failed to toggle status: {e}"}
    rule_active = restrictions.is_active(triggered)
    status = "✔" if rule_active else "✖"
    clazz = "temprest-cell " + ("temprest-active" if rule_active else "temprest-inactive")
    title = "Rule is " + ("active" if rule_active else "inactive")
    return status, clazz, title, msg

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
         Input("temprest-selected-rule", "value"),
        Input("lang", "data"))
def snapshot_changed(snapshot: str|None, rule_id: str|None, lang: str|None):
    snap = DatetimeUtils.parse_date(snapshot)
    snap_obj = state.get_snapshot(time=snap)
    if not snap_obj or not dash_authenticated(config):
        return None
    orders = snap_obj.orders
    temporary_restrictions = state.get_temporary_restrictions()
    rule, settings = temporary_restrictions.get_restriction(rule_id)
    relevant_fields = None
    orders_affected: Sequence[str] = tuple()
    if rule is not None:
        relevant_fields = _relevant_fields_for_condition(rule.condition)
        equipment = rule.equipment
        if isinstance(equipment, int):
            equipment = (equipment, )

        def order_affected(order: Order) -> bool:
            return any(not RestrictionUtils.equipment_allowed(rule, e, order) for e in equipment)
        # sort orders: affected ones first
        orders_affected = [o.id for o in orders if order_affected(o)]
        orders = sorted(orders, key=lambda order: -1 if order.id in orders_affected else 1)
    cols, rows = GuiUtils.orders_table(orders, state.get_site(), relevant_fields=relevant_fields, skip_selection_checkbox=True, lang=lang)
    if len(orders_affected) > 0:
        for row in rows:
            if row.get("id") in orders_affected:  # set row color
                row["affectedOrder"] = True
    return cols, rows

def _print_order_attribute(condition: Condition):
    if isinstance(condition, CompositeCondition):
        return html.Div([html.Span(condition.type.upper() + ":")] +
                 [html.Div(_print_order_attribute(c), style={"padding-left": "1em"}) for c in condition.conditions],
                 style={"display": "flex", "flex-direction": "column"})
    if isinstance(condition, NotCondition):
        return html.Div([html.Span("!("), _print_order_attribute(condition.base), html.Span(")")])
    order_attribute = ""
    if isinstance(condition, PropertyCondition):
        order_attribute = condition.attribute + " "
        if isinstance(condition, ThresholdCondition):
            order_attribute += condition.operator + " " + str(condition.value)
        elif isinstance(condition, ListCondition):
            order_attribute += condition.operator + " [" + ", ".join(condition.values) + "]"
        elif isinstance(condition, RangeCondition):
            order_attribute += str(condition.value_range[0]) + " " + condition.operators[0] + \
                               " x " + condition.operators[1] + str(condition.value_range[1])
    return order_attribute


def _relevant_fields_for_condition(condition: Condition) -> list[str]|None:
    relevant_fields = None
    if isinstance(condition, PropertyCondition):
        relevant_fields = [condition.attribute]
    elif isinstance(condition, MaterialCondition):
        if condition.relevant_attributes is not None:
            relevant_fields = list(condition.relevant_attributes) + ["material_classes"]
        else:
            relevant_fields = ("material_classes", )
    elif isinstance(condition, CompositeCondition):
        relevant_fields = list(set(rf for rfs in (_relevant_fields_for_condition(c) for c in condition.conditions) if rfs is not None for rf in rfs))
    elif isinstance(condition, NotCondition):
        relevant_fields = _relevant_fields_for_condition(condition.base)
    return relevant_fields



