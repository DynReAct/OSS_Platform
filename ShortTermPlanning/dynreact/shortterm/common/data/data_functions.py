"""
Module: Data_Functions data_functions.py

This module defines the functions used outside to get relevant data.
"""
import json
import time
from confluent_kafka import Producer

from dynreact.shortterm.common import sendmsgtopic
from dynreact.shortterm.common.data.load_url import URL_INITIAL_STATE, URL_UPDATE_STATUS, load_url_json_get, \
    load_url_json_post


def get_equipment_status(equipment_id: int, snapshot_time: str) -> dict:
    """
    Get the initial status of the given equipment.

    :param int equipment_id: Id of the interesting equipment
    :param str snapshot_time: Snapshot time in ISO8601 format, otherwise use the latest available

    :return: Status of the interesting equipment
    :rtype: dict
    """
    url_equipment_status = URL_INITIAL_STATE.format(equipment_id=equipment_id, snapshot_timestamp=snapshot_time)
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
    equipment_id = equipment_status["targets"]["equipment"]
    next_material = material_params["id"]
    prev_material = equipment_status["current_material"][-1]
    if verbose > 0:
        print(f"Transition of equipment {equipment_id} from {prev_material} to {next_material}...")

    msg_incompatible = "The transition is not possible."
    if equipment_id not in material_params["order"]["allowed_equipment"]:
        if verbose > 0:
            print(msg_incompatible, f"The equipment {equipment_id} is not among the allowed equipments of {next_material}")
        return None, None

    payload = {
        "equipment": equipment_id,
        "snapshot_id": equipment_status["snapshot_id"],
        "current_order": equipment_status.get("current_order"),
        "next_order": material_params["order"]["id"],
        "current_material": prev_material,
        "next_material": next_material,
        "equipment_status": equipment_status
    }

    if verbose > 1:
        print("Payload:")
        print(json.dumps(payload, indent=4))

    new_status = load_url_json_post(URL_UPDATE_STATUS, payload=payload)
    new_status = new_status["status"]
    cost = new_status["planning"]["transition_costs"]

    if cost is None:
        if verbose > 0:
            print(msg_incompatible, f"The returned cost is null.")
        return None, None

    if verbose > 0:
        print(f"Cost: {cost} | New status: {new_status}")
    return cost, new_status


def end_auction(topic: str, producer: Producer, verbose: int, wait_time: int) -> None:
    """
    Ends an auction by instructing all EQUIPMENT, MATERIAL and LOG children of the auction to exit

    :param str topic: Topic name of the auction we want to end
    :param object producer: A Kafka Producer instance
    :param int verbose: Verbosity level
    :param int wait_time: Wait Time to end the auction
    """

    if verbose > 0:
        msg = "Auction has ended!"
        sendmsgtopic(
            producer=producer,
            tsend=topic,
            topic=topic,
            source="UX",
            dest="LOG:" + topic,
            action="WRITE",
            payload=dict(msg=msg),
            vb=verbose
        )

    # Instruct all EQUIPMENT children to exit
    # We can define the destinations of the message using a regex instead of looping through all equipment IDs
    # In this case, the regex ".*" matches any sequence of characters; that is, any equipment ID
    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="EQUIPMENT:" + topic + ":.*",
        action="EXIT",
        vb=verbose
    )

    # Instruct all MATERIAL children to exit
    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="MATERIAL:" + topic + ":.*",
        action="EXIT",
        vb=verbose
    )

    time.sleep(wait_time)

    # Instruct the LOG of the auction to exit
    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="LOG:" + topic,
        action="EXIT",
        vb=verbose
    )