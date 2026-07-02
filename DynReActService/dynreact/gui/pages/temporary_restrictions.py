import json
from typing import Sequence

from dash import html, callback, Output, ALL, Input, dcc
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
                html.Th("Rule", scope="col", title="Name of the rule"),
                html.Th("Explanation", scope="col", title="Explanation of the rule"),
                html.Th("Equipment", scope="col", title="Equipment affected by the rule"),
                html.Th("Material filter", scope="col", title="Does the rule apply to a specific material class?"),
                html.Th("Property filter", scope="col", title="Does the rule apply to specific order properties?"),
                html.Th("Active", scope="col", title="Is the rule currently active?"),
                html.Th("Toggle", scope="col", title="Toggle the active status of the rule")
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
        grid_body.append(html.Tr([
                    html.Th(rst.label, title=f"Id: {rst.id}", scope="row"), html.Td(rst.description), html.Td(equipment_text, title="Id: " + equipment_title),
                    html.Td(material_filter), html.Td(f"{order_attribute}"),
                    html.Td(f"{active}", id={"role": "temprest-active", "id": rst.id}),
                    html.Td(html.Button("Toggle", id={"role": "temprest-toggle", "id": rst.id}, className="dynreact-button"))
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
        html.H1("Temporary restrictions"),
        html.H2("Equipment restrictions"),
        html.Table(grid),
        html.H2("Orders affected"),
        html.Div([
            html.Div([
                html.Span("Rule", title="Select the rule to evaluate on orders"),
                dcc.Dropdown(id="temprest-selected-rule", options=rule_options, value=rule_options[0]["value"] if len(rule_options) > 0 else None, style={"min-width": "15em"}),
            ], style={"display": "flex", "column-gap": "1em", "align-items": "center"}),
            html.Br(),
            orders_table
        ])

    ])


@callback(Output({"role": "temprest-active", "id": ALL}, "children"),
         Input({"role": "temprest-toggle", "id": ALL}, "n_clicks"),
         running=[
              (Output({"role": "temprest-toggle", "id": ALL}, "disabled"), True, False),
         ],
         config_prevent_initial_callbacks=True)
def toggle(clicks):
    changed = GuiUtils.changed_ids(excluded_ids=("",))
    if len(changed) == 0 or not dash_authenticated(config):
        return
    triggered = json.loads(changed[0])["id"]
    restrictions = state.get_temporary_restrictions()
    active = restrictions.is_active(triggered)
    restrictions.set_active_status(triggered, not active)
    status = [f"{active}" for _, active in restrictions.equipment_restrictions()]
    return status


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



