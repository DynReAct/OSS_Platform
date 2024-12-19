from dash import html, callback_context
from dynreact.base.model import Equipment


class GuiUtils:

    @staticmethod
    def plant_element(plant: Equipment) -> html.Div:
        if plant is None:
            return None
        title = ""
        if plant.name is not None:
            title += plant.name + " ("
        title += "plant id: " + str(plant.id)
        if plant.name is not None:
            title += ")"
        return html.Div(plant.name_short, title=title)

    @staticmethod
    def changed_ids(excluded_ids: list[str]|None=None):
        "To be called from a callback"
        return [cid for cid in (p['prop_id'].split(".")[0] for p in callback_context.triggered) if excluded_ids is None or cid not in excluded_ids]
