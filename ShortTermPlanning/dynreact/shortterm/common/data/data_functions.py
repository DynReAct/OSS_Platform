"""
Module: Data_Functions data_functions.py

This module defines the functions used outside to get relevant data.
"""
import json
import time
import requests
from confluent_kafka import Producer
from confluent_kafka.admin import AdminClient

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

    try:
        return load_url_json_get(url_equipment_status)
    except (requests.exceptions.HTTPError, requests.exceptions.RequestException) as e:
        print(f"Error {e} trying to get the status of equipment {equipment_id}. Using fallback status.")
        return {
            "targets": {"equipment": int(equipment_id)},
            "snapshot_id": snapshot_time,
            "current_order": None,
            "current_material": [],
            "planning": {"transition_costs": 0}
        }
    except Exception as e:
        print(f"Unexpected error getting status of equipment {equipment_id}: {e}. Using fallback status.")
        return {
            "targets": {"equipment": int(equipment_id)},
            "snapshot_id": snapshot_time,
            "current_order": None,
            "current_material": [],
            "planning": {"transition_costs": 0}
        }

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

    equipment_id = equipment_status["targets"]["equipment"] if equipment_status["targets"] is not None else None
    next_material = material_params["id"]
    prev_material = (equipment_status.get("current_material") or [None])[-1]
    current_order = equipment_status.get("current_order")

    if verbose > 0:
        print(f"Transition of equipment {equipment_id} from {prev_material} to {next_material}...")

    msg_incompatible = "The transition is not possible."
    if equipment_id is not None and equipment_id not in material_params["order"]["allowed_equipment"]:
        if verbose > 0:
            print(msg_incompatible, f"The equipment {equipment_id} is not among the allowed equipments of {next_material}")
        return None, None

    if current_order is None:
        if verbose > 0:
            print(f"First order for equipment {equipment_id}, assigning cost 0.")
        return 0, equipment_status

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

    try:
        new_status = load_url_json_post(URL_UPDATE_STATUS, payload=payload)
        new_status = new_status["status"]
        cost = new_status["planning"]["transition_costs"]
    except (requests.exceptions.HTTPError, requests.exceptions.RequestException) as e:
        print(f"Error {e} trying to check the cost. Assigning cost 0.")
        return 0, equipment_status
    except Exception as e:
        print(f"Unexpected error checking transition cost: {e}. Assigning cost 0.")
        return 0, equipment_status

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


def cleanup_auction(topic: str, kafka_ip: str, wait_time: float = 0.0, timeout: float = 30.0) -> dict[str, int]:
    """Deletes the Kafka leftovers of a finished auction: its topic and its consumer groups.

    Every auction creates a topic and one consumer group per agent (named after the agent,
    ``<KIND>:<topic>[:...]``). Nothing else removes them when the auction is driven by the
    Recommender, so they pile up in the broker. Call this after ``end_auction``.

    The cleanup is best effort and never raises. A replica that has not yet consumed its
    ``EXIT`` when the topic disappears is later removed by the reaper of its parent agent.

    Args:
        topic: Topic of the auction to clean.
        kafka_ip: Kafka bootstrap servers.
        wait_time: Seconds to wait before deleting, so the agents can read their ``EXIT``.
        timeout: Seconds to wait for each broker operation.

    Returns:
        Number of deleted ``topics`` and ``groups``.
    """
    deleted = {"topics": 0, "groups": 0}
    if not topic:
        return deleted
    if wait_time > 0:
        time.sleep(wait_time)
    try:
        admin_client = AdminClient({"bootstrap.servers": kafka_ip})
    except Exception as e:
        print(f"Could not create the Kafka admin client to clean {topic}: {e}")
        return deleted

    try:
        for _, future in admin_client.delete_topics([topic], operation_timeout=timeout).items():
            try:
                future.result(timeout)
                deleted["topics"] += 1
            except Exception as e:
                print(f"Could not delete the topic {topic}: {e}")
    except Exception as e:
        print(f"Could not delete the topic {topic}: {e}")

    try:
        listing = admin_client.list_consumer_groups().result(timeout)
        group_ids = [g.group_id for g in listing.valid
                     if f":{topic}:" in g.group_id or g.group_id.endswith(f":{topic}")]
        if group_ids:
            for group_id, future in admin_client.delete_consumer_groups(group_ids).items():
                try:
                    future.result(timeout)
                    deleted["groups"] += 1
                except Exception as e:
                    # Groups that still have members cannot be deleted; the broker expires them later
                    print(f"Could not delete the consumer group {group_id}: {e}")
    except Exception as e:
        print(f"Could not clean the consumer groups of {topic}: {e}")
    return deleted
