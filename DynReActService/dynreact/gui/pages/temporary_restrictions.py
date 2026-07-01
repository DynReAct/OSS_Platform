import json
from typing import Sequence

from dash import html, callback, Output, ALL, Input
import dash

from dynreact.app import config, state
from dynreact.base.TemporaryRestrictionsProvider import EquipmentRestriction
from dynreact.base.conditions import MaterialCondition, PropertyCondition, ThresholdCondition, ListCondition, \
    RangeCondition
from dynreact.base.model import Site
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
    grid = [html.Span("Rule"), html.Span("Explanation"), html.Span("Equipment"), html.Span("Material filter"), html.Span("Property filter"),
            html.Span("Active"), html.Span("Toggle")]
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
        grid.extend([html.Span(rst.label, title=f"Id: {rst.id}"), html.Span(rst.description), html.Span(equipment_text, title="Id: " + equipment_title),
                     html.Span(material_filter), html.Span(f"{order_attribute}"), html.Span(f"{active}"),
                     html.Div(html.Button("Toggle", id={"role": "temprest-toggle", "id": rst.id}, className="dynreact-button"))])
    return html.Div([
        html.H1("Temporary restrictions"),
        html.Div(grid, style={"display": "grid", "grid-template-columns": "repeat(7, auto)", "column-gap": "1em", "row-gap": "0.5em", "justify-content": "start", "align-items": "center"}),
        html.Span(id="temprest-blub")
    ])

@callback(Output("temprest-blub", "children"),
         Input({"role": "temprest-toggle", "id": ALL}, "n_clicks"),
          config_prevent_initial_callbacks=True)
def toggle(clicks):
    changed = GuiUtils.changed_ids(excluded_ids=("",))
    if len(changed) == 0:
        return
    triggered = json.loads(changed[0])["id"]
    restrictions = state.get_temporary_restrictions()
    active = restrictions.is_active(triggered)
    restrictions.set_active_status(triggered, not active)
    return "Successfully toggled status"


def _equipment_text(e: int, site: Site) -> tuple[str, str|None]:
    eq_ob = site.get_equipment(e, do_raise=True)
    label = eq_ob.name or eq_ob.name_short or str(eq_ob.id)
    return label, str(eq_ob.id)




