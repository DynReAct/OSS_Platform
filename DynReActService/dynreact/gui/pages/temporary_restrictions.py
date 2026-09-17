import itertools
import json
import logging
import traceback
from typing import Sequence, Any, Iterator, Mapping, Literal

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


# TODO option to store a short comment with each rule?
def layout(*args, **kwargs):
    temp_rest = state.get_temporary_restrictions()
    if not temp_rest:
        return html.Div(html.H1("404 - Temporary restrictions not found"))
    #site = state.get_site()
    restrictions: Sequence[tuple[EquipmentRestriction, Sequence[RuleSettings]]] = temp_rest.equipment_restrictions()
    #grid_body = []
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
            html.Tbody(id="temprest-grid-body")  #grid_body, id="temprest-grid-body")
    ]
    rule_options = [{"value": rst.id, "label": rst.label or rst.id} for rst, _ in restrictions]
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


# TODO Save button etc need setting_idx parameter
@callback(Output("temprest-grid-body", "children"),
          Input({"role": "temprest-add-row", "id": ALL}, "n_clicks"),
          Input({"role": "temprest-delete-row", "id": ALL, "setting": ALL}, "n_clicks"),
          )
def set_table_content(_, __):
    temp_rest = state.get_temporary_restrictions()
    if not temp_rest or not dash_authenticated(config):
        return []
    site = state.get_site()
    trigger_id = callback_context.triggered_id
    add_btn_triggered = trigger_id is not None and isinstance(trigger_id, Mapping) and trigger_id.get("role") == "temprest-add-row"
    delete_btn_triggered = trigger_id is not None and isinstance(trigger_id, Mapping) and trigger_id.get("role") == "temprest-delete-row"
    triggered_id: str|None = trigger_id.get("id") if add_btn_triggered or delete_btn_triggered else None
    triggered_setting: int|None = trigger_id.get("setting") if delete_btn_triggered else None
    if add_btn_triggered:   # TODO catch errors, show alert; or show success msg
        temp_rest.add(triggered_id)
    elif delete_btn_triggered and triggered_setting is not None:
        temp_rest.delete(triggered_id, triggered_setting)
    restrictions: Sequence[tuple[EquipmentRestriction, Sequence[RuleSettings]]] = temp_rest.equipment_restrictions()
    grid_body = []
    rule_options = []
    inactive_setting = (RuleSettings(active=False),)
    for rst, settings in restrictions:
        material_filter = "" if not isinstance(rst.condition, MaterialCondition) else rst.condition.material_class
        equipment = rst.equipment
        equipment_selectable = rst.equipment_selectable and isinstance(rst.equipment, Sequence) and len(rst.equipment) > 1
        has_params = ConditionUtils.condition_has_parameters(rst.condition)
        is_rule_configurable: bool = equipment_selectable or has_params
        equipment_as_list = [rst.equipment] if not isinstance(rst.equipment, Sequence) else list(rst.equipment)
        if not settings:
            settings = inactive_setting
        num_settings = len(settings)
        for setting_idx, setting in enumerate(settings):
            active = setting.active
            parameter_values = list(setting.parameters) if setting.parameters else None
            try:
                order_attribute, counter = _print_rule_condition(rst.condition, parameter_values, rst.id, setting.setting_id)
            except:
                logging.getLogger(__name__).exception(
                    f"Failed to display rule settings for rule {rst} with settings {setting}")
                continue
            num_params = next(counter)  # starts at 0
            # dummy_selector = equipment_selector if equipment_selector is not None and not rst.equipment_selectable else None
            # TODO check: is this really required for receiving the callbacks?
            dummy_parameters = html.Div(dcc.Input(id={"role": "temprest-parameter-control", "id": rst.id, "setting": setting.setting_id}),
                                        hidden=True) if num_params == 0 and is_rule_configurable else None
            # if dummy_selector:
            #    dummy_selector.children.value = equipment_as_list
            equipment_selector = None
            if is_rule_configurable:
                equipment_selector = html.Div(dcc.Dropdown(
                    options=[{"value": e, "label": _equipment_text(e, site)[0]} for e in equipment_as_list], value=[],
                    multi=True, style={"min-width": "12em", "max-width": "20em"},
                    id={"role": "temprest-equipment-selector", "id": rst.id, "setting": setting.setting_id}))
                equipment_text = equipment_selector
                equipment_title = "Select equipment"
                if setting.active_equipment:
                    equipment_selector.children.value = setting.active_equipment
                else:
                    equipment_selector.children.value = rst.equipment
            if not equipment_selectable:
                if isinstance(equipment, Sequence):
                    equipment_texts = [_equipment_text(e, site) for e in equipment]
                    equipment_text = ", ".join([label for label, title in equipment_texts])
                    equipment_title = ", ".join([title for label, title in equipment_texts if title is not None])
                else:
                    equipment_text, equipment_title = _equipment_text(equipment, site)
                if equipment_selector is not None:  # in this case we still need the equipment selector for the callback logic, but do not want to show it
                    equipment_text = html.Div([equipment_text, html.Div(equipment_selector, hidden=True)])
            active_text = "✔" if active else "✖"

            active_status = "active" if active else "inactive"
            # we use different roles depending on whether the rule is configurable or not
            active_role = "temprest-active" if not is_rule_configurable else "temprest-cfg-active"
            msg_role = "temprest-error-msg" if not is_rule_configurable else "temprest-cfg-error-msg"
            btn_new_instance = None
            btn_delete = None
            if setting_idx == 0 and equipment_selectable and has_params:
                btn_new_instance = html.Button("New instance", className="dynreact-button",
                                               id={"role": "temprest-add-row", "id": rst.id},  title=f"Add a new instance of rule: {rst.label or rst.id}")
            if not active and setting_idx > 0:
                btn_delete = html.Button("Delete", className="dynreact-button", id={"role": "temprest-delete-row", "id": rst.id, "setting": setting.setting_id},
                                               title=f"Delete inactive rule instance: {rst.label or rst.id}")

            label = rst.label or rst.id
            if setting_idx > 0:
                label += f" ({setting_idx+1})"
            rule_label = html.Span(label)
            label_cell = html.Div([rule_label, btn_new_instance]) if btn_new_instance is not None else html.Div([rule_label, btn_delete]) if btn_delete else rule_label
            header = html.Th(label_cell, title=f"Id: {rst.id}", scope="row", className="temprest-cell") if setting_idx == 0 else \
                        html.Td(label_cell, title=f"Id: {rst.id}", className="temprest-cell temprest-cell-sub-header")
            check_id = {"role": active_role, "id": rst.id}
            msg_id = {"role": msg_role, "id": rst.id}
            if is_rule_configurable:
                check_id["setting"] = setting.setting_id
                msg_id["setting"] = setting.setting_id
            grid_body.append(html.Tr([
                header,
                html.Td(rst.description, className="temprest-cell"),
                html.Td(equipment_text, title="Id: " + equipment_title, className="temprest-cell"),
                html.Td(material_filter, className="temprest-cell"),
                html.Td(order_attribute, className="temprest-cell"),
                html.Td(html.Div(dcc.Checklist(options=("", ), value=("", ) if active else (), id=check_id),
                        className="temprest-cell temprest-" + active_status, title=f"Rule is {active_status}")),
                html.Td([
                    html.Button("Toggle" if not is_rule_configurable else "Save", className="dynreact-button",
                                id={"role": "temprest-toggle" if not is_rule_configurable else "temprest-save", "id": rst.id},
                                title=f"Toggle active status of rule: {rst.label or rst.id}" if not is_rule_configurable else "Save changes"),
                    dcc.Store(id=msg_id, ),
                    dummy_parameters
                ], className="temprest-cell")
            ]))
        rule_options.append({"value": rst.id, "label": rst.label or rst.id})
    return grid_body

@callback(Output({"role": "temprest-active", "id": MATCH}, "value"),
         #Output({"role": "temprest-active", "id": MATCH}, "className"),
         Output({"role": "temprest-active", "id": MATCH}, "title"),
         Output({"role": "temprest-error-msg", "id": MATCH}, "data"),
         Input({"role": "temprest-active", "id": MATCH}, "value"),      #
         # TODO enable once we can drop support for dash<=2.17.1: https://github.com/plotly/dash/issues/2863
         #running=[  # TODO here we could enable ALL by using an intermediate store maybe
         #     (Output({"role": "temprest-toggle", "id": MATCH}, "disabled"), True, False),
         #],
         config_prevent_initial_callbacks=True)
def toggle_rule(value: Sequence[Literal[""]]|None):
    trigger_id = callback_context.triggered_id
    if value is None or not isinstance(trigger_id, Mapping) or not dash_authenticated(config):
        return None, None, None
    triggered = trigger_id.get("id")
    activating = len(value) > 0
    restrictions = state.get_temporary_restrictions()
    rule, settings = restrictions.get_restriction(triggered)
    msg = None
    if not rule:
        msg = {"type": "error", "msg": f"Rule {triggered} unknown"}
    else:
        active = settings and len(settings) > 0 and settings[0].active
        if active != activating:
            try:
                restrictions.store(triggered, RuleSettings(active=activating))
            except Exception as e:
                msg = {"type": "error", "msg": f"Failed to toggle status: {e}"}
    rule_active = restrictions.is_active(triggered)
    status = "✔" if rule_active else "✖"
    value = [""] if rule_active else []
    clazz = "temprest-cell " + ("temprest-active" if rule_active else "temprest-inactive")
    title = "Rule is " + ("active" if rule_active else "inactive")
    return value, title, msg

@callback(
         Output("temprest-error-msg", "data"),
         Input({"role": "temprest-error-msg", "id": ALL}, "data"),
         Input({"role": "temprest-cfg-error-msg", "id": ALL, "setting": ALL}, "data"))
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


@callback(Output({"role": "temprest-cfg-active", "id": MATCH, "setting": MATCH}, "value"),
         #Output({"role": "temprest-cfg-active", "id": MATCH, "setting": MATCH}, "className"),
         Output({"role": "temprest-cfg-active", "id": MATCH, "setting": MATCH}, "title"),
         Output({"role": "temprest-cfg-error-msg", "id": MATCH, "setting": MATCH}, "data"),
         Input({"role": "temprest-cfg-active", "id": MATCH, "setting": MATCH}, "value"),
         State({"role": "temprest-equipment-selector", "id": MATCH, "setting": MATCH}, "value"),
         State({"role": "temprest-parameter-control", "id": MATCH, "setting": MATCH, "count": ALL}, "value"),
         #State({"role": "parameter-control", "rule": MATCH}, "value"),
         # TODO enable once we can drop support for dash<=2.17.1: https://github.com/plotly/dash/issues/2863
         #running=[
         #     (Output({"role": "temprest-save", "id": MATCH}, "disabled"), True, False),
         #],
         config_prevent_initial_callbacks=True)
def save_rule_configurable(value: Sequence[Literal[""]]|None, selected_equipment: list[int], parameters):
    trigger_id = callback_context.triggered_id
    if value is None or not isinstance(trigger_id, Mapping) or not dash_authenticated(config):
        return None, None, None
    triggered = trigger_id.get("id")
    setting = trigger_id.get("setting")
    activating = len(value) > 0
    restrictions = state.get_temporary_restrictions()
    rule, settings = restrictions.get_restriction(triggered)
    msg = None
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
            if has_parameters and isinstance(rule.condition, ListCondition) and parameters is not None and len(parameters) > 0:
                param_value = next(v for v in rule.condition.values if isinstance(v, ParameterValue))
                params0: str = parameters[0]
                parameters = [ConditionUtils.convert_to_parameter_type(param_value.parameter_type, p) for p in (p.strip() for p in params0.split(";")) if p]
            # TODO validate parameters and equipment, raise an error if they do not match the rule conditions
            #active = len(selected_equipment) > 0 and (not has_parameters or (parameters is not None and len(parameters) > 0))
            params = None if not has_parameters else parameters
            if has_parameters:  # validate appropriate number of parameters
                pass
            new_settings = RuleSettings(active=activating, active_equipment=selected_equipment, parameters=params, setting_id=setting)
            restrictions.store(triggered, new_settings)
            # msg = {"type": "success", "msg": f"Status toggled: {triggered} = {not active}"}  # the alert is too ugly here
        except Exception as e:
            traceback.print_exc()
            msg = {"type": "error", "msg": f"Failed to toggle status: {e}"}
    rule_active = restrictions.is_active(triggered, setting_id=setting)
    status = "✔" if rule_active else "✖"
    value = [""] if rule_active else []
    clazz = "temprest-cell " + ("temprest-active" if rule_active else "temprest-inactive")
    title = "Rule is " + ("active" if rule_active else "inactive")
    return value, title, msg

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
        return None, None
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


def _parameter_control(param: ParameterValue[Any], parameter: Any|None, rule_id: str, setting_id: int, counter: Iterator[int]):
    cnt = next(counter)
    el_id = {"role": "temprest-parameter-control", "id": rule_id, "setting": setting_id, "count": cnt}
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


def _print_rule_leaf_condition_with_parameters(condition: Condition, parameter_values: list[Any]|None, rule_id: str, setting_id: int, counter: Iterator[int]):
    children = []
    if isinstance(condition, RangeCondition):
        val0 = condition.value_range[0]
        val1 = condition.value_range[1]
        param_value0 = parameter_values.pop(0) if isinstance(val0, ParameterValue) and parameter_values is not None else None
        param_value1 = parameter_values.pop(0) if isinstance(val1, ParameterValue) and parameter_values is not None else None
        val0_el = _parameter_control(val0, param_value0, rule_id, setting_id, counter) if isinstance(val0, ParameterValue) else html.Span(str(val0))
        val1_el = _parameter_control(val1, param_value1, rule_id, setting_id, counter) if isinstance(val1, ParameterValue) else html.Span(str(val1))
        children.extend([val0_el, html.Span(condition.operators[0]), html.Span(condition.attribute), html.Span(condition.operators[1]), val1_el])
    elif isinstance(condition, PropertyCondition):
        children.append(html.Span(condition.attribute))
        if isinstance(condition, ThresholdCondition):
            children.append(condition.operator)
            value = condition.value
            if isinstance(value, ParameterValue):
                param_value = parameter_values.pop(0) if parameter_values is not None else None
                children.append(_parameter_control(value, param_value, rule_id, setting_id, counter))
            else:
                children.append(html.Span(str(value)))
        elif isinstance(condition, ListCondition):
            param_value = next(v for v in condition.values if isinstance(v, ParameterValue))
            values = None
            if parameter_values:
                values = [str(v) for v in parameter_values] if parameter_values is not None else None
                values = "; ".join(values)
                parameter_values.clear()
            ctrl = _parameter_control(param_value, values, rule_id, setting_id, counter)
            ctrl.type = "string"
            ctrl.style = {"min-width": "12em"}
            ctrl.placeholder = "3; 1; 5; 17; ..." if param_value.parameter_type == "int" else "2.12; 34.6; ..." if param_value.parameter_type == "float" else \
                    "true; false; false; ..." if param_value.parameter_type.startswith("bool") else "value1; value2; ..."
            ctrl.title = "Separate multiple values by a semi-colon: ;"
            children.append(html.Span(" " + condition.operator + " "))
            children.append(ctrl)
    return html.Div(children, style={"display": "flex", "column-gap": "0.3em", "row-gap": "0.5em", "flex-wrap": "wrap"})


def _print_rule_condition(condition: Condition, parameter_values: list[Any]|None, rule_id: str, setting_id: int, counter: Iterator[int]|None=None) -> tuple[Any, Iterator[int]]:
    if counter is None:
        counter = itertools.count()
    if isinstance(condition, CompositeCondition):
        return html.Div([html.Span(condition.type.upper() + ":")] +
                        [html.Div(_print_rule_condition(c, parameter_values, rule_id, setting_id, counter=counter)[0], style={"padding-left": "1em"}) for c in condition.conditions],
                        style={"display": "flex", "flex-direction": "column"}), counter
    if isinstance(condition, NotCondition):
        return html.Div([html.Span("!("), _print_rule_condition(condition.base, parameter_values, rule_id, setting_id, counter=counter)[0], html.Span(")")]), counter
    return _print_rule_leaf_condition(condition, parameter_values, rule_id, setting_id, counter), counter


def _print_rule_leaf_condition(condition: LeafCondition, parameter_values: list[Any]|None, rule_id: str, setting_id: int, counter: Iterator[int]):
    if ConditionUtils.condition_has_parameters(condition):
        return _print_rule_leaf_condition_with_parameters(condition, parameter_values, rule_id, setting_id, counter)
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



