"""
Module: Data_Functions data_functions.py

This module defines the functions used outside to get relevant data.
"""
from data.load_url import URL_INITIAL_STATE, URL_UPDATE_STATUS, load_url_json_get, load_url_json_post
from data.data_setup import LAST_SNAPSHOT, ALL_MATERIALS_PARAMS, ALL_RESOURCES_MATERIALS
import json


def get_material_params(material_id: str) -> dict:
    """
    Get the parameters of the given material.
    
    :param str material_id: Id of the involved material in the production list.

    :return: Dictionary with all the parameters
    :rtype: dict
    """
    return ALL_MATERIALS_PARAMS[material_id]


def get_equipment_materials(resource_id: int) -> list[str]:
    """
    Get the list of materials for the given resource.

    :param int resource_id: Id of the interesting equipment

    :return: List of all the materials looking at this equipment.
    :rtype: list
    """
    return ALL_RESOURCES_MATERIALS[resource_id]


def get_equipment_status(resource_id: int) -> dict:
    """
    Get the initial status of the given equipment.

    :param int resource_id: Id of the interesting equipment

    :return: Status of the interesting equipment
    :rtype: dict
    """
    url_resource_status = URL_INITIAL_STATE.format(plant_id=resource_id, snapshot_timestamp=LAST_SNAPSHOT)
    return load_url_json_get(url_resource_status)


def get_transition_cost_and_status(
        material_params: dict, resource_status: dict, verbose: int = 1
) -> tuple[float | None, dict | None]:
    """
    Get the cost of processing the given material with the given equipment and
    the new equipment status after processing the given material.
    Returns None if the material cannot be processed by the equipment.

    :param dict material_params: Parameters for the Material being considered.
    :param dict resource_status: Status of the equipment in charge for processing.
    :param int verbose: Verbosity level.

    :return: Tuple of cost(float) and status(dict)
    :rtype: tuple
    """
    resource_id = resource_status['plant']
    prev_material = resource_status['current_coils'][-1]
    next_material = material_params['id']
    if verbose > 0:
        print(f"Transition of resource {resource_id} from {prev_material} to {next_material}...")

    msg_incompatible = "The transition is not possible."
    if resource_id not in material_params['order']['allowed_plants']:
        if verbose > 0:
            print(msg_incompatible, f"The resource {resource_id} is not among the allowed resources of {next_material}")
        return None, None

    payload = {
        "plant": resource_status['plant'],
        "snapshot_id": resource_status['snapshot_id'],
        "current_order": resource_status['current_order'],
        "next_order": material_params['order']['id'],
        "current_coil": prev_material,
        "next_coil": next_material,
        "plant_status": resource_status
    }
    if verbose > 1:
        print("Payload:")
        print(json.dumps(payload, indent=4))

    new_status = load_url_json_post(URL_UPDATE_STATUS, payload=payload)
    cost = new_status['planning']['transition_costs']
    if cost is None:
        if verbose > 0:
            print(msg_incompatible, f"The returned cost is null.")
        return None, None

    if verbose > 0:
        print(f"Cost: {cost} | New status: {new_status}")
    return cost, new_status

