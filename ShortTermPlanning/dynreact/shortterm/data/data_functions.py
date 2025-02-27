"""
Module: Data_Functions data_functions.py

This module defines the functions used outside to get relevant data.
"""
from data.load_url import URL_INITIAL_STATE, URL_UPDATE_STATUS, load_url_json_get, load_url_json_post
from data.data_setup import (LAST_SNAPSHOT, ALL_MATERIALS_PARAMS, ALL_EQUIPMENTS_MATERIALS)

def get_material_params(material_id: str) -> dict:
    """
    Get the parameters of the given material.
    
    :param str material_id: Id of the involved material in the production list.

    :return: Dictionary with all the parameters
    :rtype: dict
    """
    return ALL_MATERIALS_PARAMS[material_id]


def get_equipment_materials(equipment_id: int) -> list[str]:
    """
    Get the list of materials for the given equipment.

    :param int equipment_id: Id of the interesting equipment

    :return: List of all the materials looking at this equipment.
    :rtype: list
    """
    return ALL_EQUIPMENTS_MATERIALS[equipment_id]

def get_equipment_status(equipment_id: int) -> dict:
    """
    Get the initial status of the given equipment.

    :param int equipment_id: Id of the interesting equipment

    :return: Status of the interesting equipment
    :rtype: dict
    """
    url_equipment_status = URL_INITIAL_STATE.format(equipment_id=equipment_id, snapshot_timestamp=LAST_SNAPSHOT)
    return load_url_json_get(url_equipment_status)


def get_transition_cost_and_status(
        material_params: dict, equipment_status: dict, verbose: int = 1
) -> tuple[float | None, dict | None]:
    """
    Get the cost of processing the given material with the given equipment and
    the new equipment status after processing the given material.
    Returns None if the material cannot be processed by the equipment.

    :param dict material_params: Parameters for the Material being considered.
    :param dict equipment_status: Status of the equipment in charge for processing.
    :param int verbose: Verbosity level.

    :return: Tuple of cost(float) and status(dict)
    :rtype: tuple
    """
    equipment_id = equipment_status['equipment']
    prev_material = None if len(equipment_status['current_material']) == 0 else equipment_status['current_material'][-1]
    next_material = material_params['id']
    if verbose > 0:
        print(f"Transition of equipment {equipment_id} from {prev_material} to {next_material}...")

    msg_incompatible = "The transition is not possible."
    if equipment_id not in material_params['order']['allowed_equipment']:
        if verbose > 0:
            print(msg_incompatible, f"The equipment {equipment_id} is not among the allowed equipments of {next_material}")
        return None, None

    payload = {
        "equipment": equipment_status['equipment'],
        "snapshot_id": equipment_status['snapshot_id'],
        "current_order": equipment_status.get('current_order') or material_params['order']['id'],
        "next_order": material_params['order']['id'],
        "current_material": prev_material or next_material,
        "next_material": next_material,
        "equipment_status": equipment_status
    }

    print('\n***\n')
    print(payload)

    # TODO Uncomment when service is available
    # if verbose > 1:
    #     print("Payload:")
    #     print(json.dumps(payload, indent=4))
    #
    # new_status = load_url_json_post(URL_UPDATE_STATUS, payload=payload)
    # cost = new_status['planning']['transition_costs']
    # if cost is None:
    #     if verbose > 0:
    #         print(msg_incompatible, f"The returned cost is null.")
    #     return None, None
    #
    # if verbose > 0:
    #     print(f"Cost: {cost} | New status: {new_status}")
    # return cost, new_status

    # TODO: Remove provisional code to mock a cost
    try:
        new_status = load_url_json_post(URL_UPDATE_STATUS, payload=payload)
        cost = new_status['planning']['transition_costs']
    except:
        cost = 0.01
        equipment_status['current_cost'] = cost
        equipment_status['planning']['transition_costs'] = cost

    if cost is None:
        if verbose > 0:
            print(msg_incompatible, f"The returned cost is null.")
        return None, None

    if verbose > 0:
        print(f"Cost: {cost} | New status: {equipment_status}")
    return cost, equipment_status


