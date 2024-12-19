import dash_cytoscape as cyto
from dynreact.base.model import Equipment, Site, Storage, Process

from dynreact.app import config, state
from dynreact.auth.authentication import dash_authenticated


def default_stylesheet(background_color="green", color="white", line_color="green"):
    return [
        {
            "selector": "node.plant-node",
            "style": {
                "background-color": background_color,
                "line-color": line_color,
                "color": color,
                "content": "data(label)",
                "shape": "rectangle",
                "text-valign" : "center",
                "text-halign" : "center",
                "width": "data(width)",
                "height": "data(height)"
            }
        },
        {
            "selector": "node.storage-node",
            "style": {
                "content": "data(label)",
                "text-valign": "center",
                "text-halign": "center",
                "width": "data(size)",
                "height": "data(size)"
            }
        }, {
            "selector": "edge",
            "style": {
                #"target-arrow-color": "blue",
                "target-arrow-shape": "triangle", # "triangle", "vee"
                "curve-style": "bezier"
            }
        }
    ]

def plants_graph(element_id: str, style={'width': '100%', 'height': '500px'}, stylesheet=default_stylesheet(),
                minZoom=1e-1, maxZoom=4, *args, **kwargs):
    #lang = language.data if hasattr(language, "data") else "en"
    if not dash_authenticated(config):
        return None
    mode = kwargs.get("mode")
    if mode is None:
        mode = "centered"
    site = state.get_site()
    processes = [p.name_short for p in site.processes]
    plants_per_process: dict[int, int] = {}
    follow_up_process_per_storage: dict[str, str] = {}
    storages_per_process: dict[str, int] = {}
    process_graph_dict: dict[str, int] = _process_graph(site.processes)
    if mode == "centered":  # prefill plants_per_process to move the plants
        for plant in site.equipment:
            proc = site.get_process(plant.process)
            if proc is None:
                continue
            ids = proc.process_ids
            for proc_id in ids:
                if proc_id not in plants_per_process:
                    plants_per_process[proc_id] = 0
                plants_per_process[proc_id] += 1
        plants_per_process = {proc: -int(cnt/2) for proc, cnt in plants_per_process.items()}

    plant_elements = [{"data": {"id": f"plant_{plant.id}", "label": str(plant.name_short), "width": 100, "height": 50}, "classes": "plant-node",
            "position": _position_for_plant(plant, processes, plants_per_process, follow_up_process_per_storage, process_graph_dict, site)} for plant in site.equipment]
    storage_elements = [{"data": {"id": f"storage_{storage.name_short}", "label": str(storage.name_short), "size": 50}, "classes": "storage-node",
            "position": _position_for_storage(storage, processes, follow_up_process_per_storage, storages_per_process, process_graph_dict)} for storage in site.storages]
    edges_in = [{"data": {"id": f"storage_{plant.storage_in}_plant_{plant.id}", "source": f"storage_{plant.storage_in}", "target": f"plant_{plant.id}"}} for plant in site.equipment if plant.storage_in is not None]
    edges_out = [{"data": {"id": f"plant_{plant.id}_storage_{plant.storage_out}", "target": f"storage_{plant.storage_out}", "source": f"plant_{plant.id}"}} for plant in site.equipment if plant.storage_out is not None]
    elements = plant_elements + storage_elements + edges_in + edges_out
    return cyto.Cytoscape(
            id=element_id,
            layout={'name': 'preset'}, # {'name': 'preset'},  {'name': 'breadthfirst'}
            style=style,
            elements=elements,
            stylesheet=stylesheet,
            minZoom=minZoom,
            maxZoom=maxZoom
        )


# with side effects
def _position_for_plant(plant: Equipment,
                        processes: list[str],
                        plants_per_process: dict[int, int],
                        follow_up_process_per_storage: dict[str, str],
                        process_graph: dict[str, int],
                        site: Site,
                        delta_x: float = 100,
                        delta_y: float = 100) -> dict[str, int]:
    process = plant.process
    #x = processes.index(process) * 2 + 1
    x0 = process_graph[process] if process in process_graph else processes.index(process)
    x = x0 * 2 + 1
    proc = site.get_process(process)
    x_id = proc.process_ids[0] if len(proc.process_ids) > 0 else x0
    if x_id not in plants_per_process:
        plants_per_process[x_id] = 0
    y = plants_per_process[x_id]
    plants_per_process[x_id] += 1
    storage = plant.storage_in
    if storage is not None and len(storage) > 0:
        if storage not in follow_up_process_per_storage:
            follow_up_process_per_storage[storage] = process
        elif process != follow_up_process_per_storage[storage]:
            existing = follow_up_process_per_storage[storage]
            existing_idx = processes.index(existing)
            new_idx = processes.index(process)
            if new_idx < existing_idx:
                follow_up_process_per_storage[storage] = process
    return {"x": x * delta_x, "y": -y * delta_y}


def _position_for_storage(storage: Storage,
                          processes: list[str],
                          follow_up_process_per_storage: dict[str, str],
                          storages_per_process: dict[str, int],
                          process_graph: dict[str, int],
                          delta_x: float = 100,
                          delta_y: float = 100) -> dict[str, int]:
    stg = storage.name_short
    if stg in follow_up_process_per_storage:
        process = follow_up_process_per_storage[stg]
        #x = processes.index(process) * 2
        x = process_graph[process] * 2 if process in process_graph else processes.index(process) * 2
        if process not in storages_per_process:
            storages_per_process[process] = 0
        y = storages_per_process[process]
        storages_per_process[process] += 1
        return {"x": x * delta_x, "y": -y * delta_y}
    else:
        return {"x": len(processes) * 2 * delta_x, "y": 0}


def _process_graph(processes: list[Process]) -> dict[str, int]:
    step: dict[str, int] = {}
    final_steps = [p for p in processes if p.next_steps is None or len(p.next_steps) == 0]
    current_steps = final_steps
    cnt: int = 0
    while len(current_steps) > 0:
        current_ids = [p.name_short for p in current_steps]
        step.update({p: cnt for p in current_ids})
        previous = [p for p in processes if p.next_steps is not None and
                    next((proc for proc in current_ids if proc in p.next_steps), None) is not None]
        current_steps = previous
        cnt += 1
    step_inverted = {p: cnt - step - 1 for p, step in step.items()}
    return step_inverted