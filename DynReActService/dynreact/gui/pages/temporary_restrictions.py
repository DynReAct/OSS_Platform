import itertools
import json
import logging
import traceback
from typing import Sequence, Any, Iterator

from dash import html, callback, Output, ALL, Input, dcc, State, clientside_callback, ClientsideFunction, MATCH, \
    callback_context
import dash
import dash_ag_grid as dash_ag

from dynreact.app import config, state
from dynreact.auth.authentication import dash_authenticated
from dynreact.base.TemporaryRestrictionsProvider import EquipmentRestriction, RestrictionUtils, RuleSettings
from dynreact.base.conditions import MaterialCondition, PropertyCondition, ThresholdCondition, ListCondition, \
    RangeCondition, Condition, CompositeCondition, NotCondition, ConditionUtils, LeafCondition, ParameterValue
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
        active = settings and len(settings) > 0
        material_filter = "" if not isinstance(rst.condition, MaterialCondition) else rst.condition.material_class
        parameter_values = list(settings[0].parameters) if active and settings[0].parameters else None
        try:
            order_attribute, counter = _print_rule_condition(rst.condition, parameter_values, rst.id)
        except:
            logging.getLogger(__name__).exception(f"Failed to display rule settings for rule {rst} with settings {settings}")
            continue
        num_params = next(counter)   #  starts at 0
        equipment = rst.equipment
        is_rule_configurable: bool = (rst.equipment_selectable and isinstance(rst.equipment, Sequence)) or ConditionUtils.condition_has_parameters(rst.condition)
        equipment_as_list = [rst.equipment] if not isinstance(rst.equipment, Sequence) else list(rst.equipment)
        #dummy_selector = equipment_selector if equipment_selector is not None and not rst.equipment_selectable else None
        # TODO check: is this really required for receiving the callbacks?
        dummy_parameters = html.Div(dcc.Input(id={"role": "temprest-parameter-control", "id": rst.id, "count": 0}), hidden=True) if num_params == 0 and is_rule_configurable else None
        #if dummy_selector:
        #    dummy_selector.children.value = equipment_as_list
        if is_rule_configurable:
            equipment_selector = html.Div(dcc.Dropdown(options=[{"value": e, "label": _equipment_text(e, site)[0]} for e in equipment_as_list], value=[], multi=True, style={"min-width": "12em", "max-width": "20em"},
                                              id={"role": "temprest-equipment-selector", "id": rst.id}))
            equipment_text = equipment_selector
            equipment_title = "Select equipment"
            if len(settings) > 0:
                equipment_selector.children.value = settings[0].active_equipment
            elif not active:
                equipment_selector.children.value = rst.equipment
        elif isinstance(equipment, Sequence):
            equipment_texts = [_equipment_text(e, site) for e in equipment]
            equipment_text = ", ".join([label for label, title in equipment_texts])
            equipment_title = ", ".join([title for label, title in equipment_texts if title is not None])
        else:
            equipment_text, equipment_title = _equipment_text(equipment, site)
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
                        dummy_parameters
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
         Input({"role": "temprest-error-msg", "id": ALL}, "data"),
         Input({"role": "temprest-cfg-error-msg", "id": ALL}, "data"))
def error_msg_changed(messages0, messages1):
    changed = GuiUtils.changed_ids(excluded_ids=("",))
    if len(changed) == 0:
        return None
    message_inputs0: Sequence[dict[str, dict[str, str]]] = callback_context.inputs_list[0]
    message_inputs1: Sequence[dict[str, dict[str, str]]] = callback_context.inputs_list[1]
    changed_id = json.loads(changed[0])["id"]
    changed_idx0 = next((idx for idx, inp in enumerate(message_inputs0) if
                        inp is not None and "id" in inp and inp["id"].get("id") == changed_id), None)
    changed_idx1 = next((idx for idx, inp in enumerate(message_inputs1) if
                         inp is not None and "id" in inp and inp["id"].get("id") == changed_id), None)
    return messages0[changed_idx0] if changed_idx0 is not None else messages1[changed_idx1] if changed_idx1 is not None else None


@callback(Output({"role": "temprest-cfg-active", "id": MATCH}, "children"),
         Output({"role": "temprest-cfg-active", "id": MATCH}, "className"),
         Output({"role": "temprest-cfg-active", "id": MATCH}, "title"),
         Output({"role": "temprest-cfg-error-msg", "id": MATCH}, "data"),
         Input({"role": "temprest-save", "id": MATCH}, "n_clicks"),
         State({"role": "temprest-equipment-selector", "id": MATCH}, "value"),
         State({"role": "temprest-parameter-control", "id": MATCH, "count": ALL}, "value"),
         #State({"role": "parameter-control", "rule": MATCH}, "value"),
         running=[
              (Output({"role": "temprest-save", "id": MATCH}, "disabled"), True, False),
         ],
         config_prevent_initial_callbacks=True)
def save_rule_configurable(clicks, selected_equipment: list[int], parameters):
    changed = GuiUtils.changed_ids(excluded_ids=("",))
    if len(changed) == 0 or not dash_authenticated(config):
        return None, None, None, None
    triggered = json.loads(changed[0])["id"]
    restrictions = state.get_temporary_restrictions()
    rule, settings = restrictions.get_restriction(triggered)
    if not rule:
        msg = {"type": "error", "msg": f"Rule {triggered} unknown"}
    elif parameters is not None and any(p is None for p in parameters):
        msg = {"type": "error", "msg": f"Invalid parameter(s) passed."}
    else:
        if isinstance(selected_equipment, int):
            selected_equipment = [selected_equipment]
        try:
            has_parameters: bool = ConditionUtils.condition_has_parameters(rule.condition)
            msg = None
            if has_parameters and isinstance(rule.condition, ListCondition) and parameters is not None and len(parameters) > 0:  # TODO recursive...
                param_value = next(v for v in rule.condition.values if isinstance(v, ParameterValue))
                params0: str = parameters[0]
                parameters = [ConditionUtils.convert_to_parameter_type(param_value.parameter_type, p) for p in (p.strip() for p in params0.split(";")) if p]
            active = len(selected_equipment) > 0 and (not has_parameters or (parameters is not None and len(parameters) > 0))
            params = None if not has_parameters else parameters
            if has_parameters:  # TODO validate appropriate number of parameters
                pass
            new_settings = RuleSettings(active=active, active_equipment=selected_equipment, parameters=params)
            restrictions.activate(triggered, new_settings, rule_index=0)
            # msg = {"type": "success", "msg": f"Status toggled: {triggered} = {not active}"}  # the alert is too ugly here
        except Exception as e:
            traceback.print_exc()
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
    active = settings is not None and any(s.active for s in settings)
    if not active and ConditionUtils.condition_has_parameters(rule.condition):
        rules = []  # we need to specify the parameters in this case (TODO apply default params, if possible)
    else:
        rules = [r for r in (RestrictionUtils.apply_settings(rule, setting) for setting in settings) if r is not None] if active else [rule]
    relevant_fields = None
    orders_affected: Sequence[str] = tuple()
    if rule is not None:
        relevant_fields = _relevant_fields_for_condition(rule.condition)
        equipment = set([eq for rl in rules for eq in (rl.equipment if isinstance(rl.equipment, Sequence) else [rl.equipment])])

        def order_affected(order: Order) -> bool:
            if not any(e in equipment for e in order.allowed_equipment):
                return False
            return not all(RestrictionUtils.equipment_allowed(rl, None, e, order) for e in equipment for rl in rules)
        # sort orders: affected ones first
        orders_affected = [o.id for o in orders if order_affected(o)]
        orders = sorted(orders, key=lambda order: -1 if order.id in orders_affected else 1)
    cols, rows = GuiUtils.orders_table(orders, state.get_site(), relevant_fields=relevant_fields, skip_selection_checkbox=True, lang=lang)
    if len(orders_affected) > 0:
        for row in rows:
            if row.get("id") in orders_affected:  # set row color
                row["affectedOrder"] = True
    return cols, rows


def _parameter_control(param: ParameterValue[Any], parameter: Any|None, rule_id: str, counter: Iterator[int]):
    cnt = next(counter)
    el_id = {"role": "temprest-parameter-control", "id": rule_id, "count": cnt}
    value = parameter if parameter is not None else param.default_value
    if param.parameter_type == "bool":
        return dcc.Checklist(options=[""], value=[""] if value else [], id=el_id)
    if param.parameter_type == "string":
        return dcc.Input(value=value, id=el_id, style={"max-width": "5em"})
    if param.parameter_type in ("float", "int", "date", "datetime"):
        is_date = param.parameter_type in ("date", "datetime")
        inp = dcc.Input(value=value, id=el_id, type="number" if not is_date else "datetime-local", style={"max-width": "5em"} if not is_date else None)
        if param.allowed_range:
            if param.allowed_range[0] is not None:
                inp.min = param.allowed_range[0]
            if param.allowed_range[1] is not None:
                inp.max = param.allowed_range[1]
        return inp
    logging.getLogger(__name__).warning(f"Unknown parameter type for temporary restrictions {param.parameter_type} in rule {rule_id}")
    return None


def _print_rule_leaf_condition_with_parameters(condition: Condition, parameter_values: list[Any]|None, rule_id: str, counter: Iterator[int]):
    children = []
    if isinstance(condition, RangeCondition):
        val0 = condition.value_range[0]
        val1 = condition.value_range[1]
        param_value0 = parameter_values.pop(0) if isinstance(val0, ParameterValue) and parameter_values is not None else None
        param_value1 = parameter_values.pop(0) if isinstance(val1, ParameterValue) and parameter_values is not None else None
        val0_el = _parameter_control(val0, param_value0, rule_id, counter) if isinstance(val0, ParameterValue) else html.Span(str(val0))
        val1_el = _parameter_control(val1, param_value1, rule_id, counter) if isinstance(val1, ParameterValue) else html.Span(str(val1))
        children.extend([val0_el, html.Span(condition.operators[0]), html.Span(condition.attribute), html.Span(condition.operators[1]), val1_el])
    elif isinstance(condition, PropertyCondition):
        children.append(html.Span(condition.attribute))
        if isinstance(condition, ThresholdCondition):
            children.append(condition.operator)
            value = condition.value
            if isinstance(value, ParameterValue):
                param_value = parameter_values.pop(0) if parameter_values is not None else None
                children.append(_parameter_control(value, param_value, rule_id, counter))
            else:
                children.append(html.Span(str(value)))
        elif isinstance(condition, ListCondition):
            param_value = next(v for v in condition.values if isinstance(v, ParameterValue))
            values = None
            if parameter_values:
                values = [str(v) for v in parameter_values] if parameter_values is not None else None
                values = "; ".join(values)
                parameter_values.clear()
            ctrl = _parameter_control(param_value, values, rule_id, counter)
            ctrl.type = "string"
            ctrl.style = {"min-width": "12em"}
            ctrl.placeholder = "3; 1; 5; 17; ..." if param_value.parameter_type == "int" else "2.12; 34.6; ..." if param_value.parameter_type == "float" else \
                    "true; false; false; ..." if param_value.parameter_type.startswith("bool") else "value1; value2; ..."
            ctrl.title = "Separate multiple values by a semi-colon: ;"
            children.append(html.Span(" " + condition.operator + " "))
            children.append(ctrl)
    return html.Div(children, style={"display": "flex", "column-gap": "0.3em", "row-gap": "0.5em", "flex-wrap": "wrap"})


def _print_rule_condition(condition: Condition, parameter_values: list[Any]|None, rule_id: str, counter: Iterator[int]|None=None) -> tuple[Any, Iterator[int]]:
    if counter is None:
        counter = itertools.count()
    if isinstance(condition, CompositeCondition):
        return html.Div([html.Span(condition.type.upper() + ":")] +
                        [html.Div(_print_rule_condition(c, parameter_values, rule_id, counter=counter)[0], style={"padding-left": "1em"}) for c in condition.conditions],
                        style={"display": "flex", "flex-direction": "column"}), counter
    if isinstance(condition, NotCondition):
        return html.Div([html.Span("!("), _print_rule_condition(condition.base, parameter_values, rule_id, counter=counter)[0], html.Span(")")]), counter
    return _print_rule_leaf_condition(condition, parameter_values, rule_id, counter), counter


def _print_rule_leaf_condition(condition: LeafCondition, parameter_values: list[Any]|None, rule_id: str, counter: Iterator[int]):
    if ConditionUtils.condition_has_parameters(condition):
        return _print_rule_leaf_condition_with_parameters(condition, parameter_values, rule_id, counter)
    order_attribute = ""
    if isinstance(condition, RangeCondition):
        order_attribute += str(condition.value_range[0]) + " " + condition.operators[0] + " " + condition.attribute + " " + condition.operators[1] + str(condition.value_range[1])
    elif isinstance(condition, PropertyCondition):
        order_attribute = condition.attribute + " "
        if isinstance(condition, ThresholdCondition):
            order_attribute += condition.operator + " " + str(condition.value)
        elif isinstance(condition, ListCondition):
            order_attribute += condition.operator + " [" + ", ".join(condition.values) + "]"
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



