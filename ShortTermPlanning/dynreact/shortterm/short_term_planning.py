"""
Module: short_term_planning.py

This program runs the scripts required to start the general agents,
clones them for an auction with the equipments indicated by the user,
and starts the auction, waiting for its completion.

First Prototype of Kubernetes oriented solution for the UX service

Version History:
- 1.0 (2024-03-09): Initial version developed by Rodrigo Castro Freibott.
- 1.1 (2024-10-30): Updated version (JOM).
- 1.2 (2025-01-30): Rename references from machine/plant to equipment and coil to material. Handle subprocess errors

Note:

    To run scenario 05, use: python3 short_term_planning.py -v 3  -b . -rw 10 -cw 30 -aw 50 -bw 15 -ew 10 -e 14 -n 1 -g 111
    To run scenario 06, use: python3 short_term_planning.py -v 3  -b . -rw 10 -cw 30 -aw 50 -bw 15 -ew 10 -e 14 -n 2 -g 111
    To run scenario 07, use: python3 short_term_planning.py -v 3 -b . -rw 10 -cw 30 -aw 200 -bw 15 -ew 10 -e 14 15 -n 1 -g 111

    To run a reduced version, use: python3 short_term_planning.py -v 3 -b . -rw 10 -cw 30 -aw 200 -bw 15 -ew 10 -e 14 15 -n 4 -g 111
    To run a full version, use: python3 short_term_planning.py -v 3 -b . -rw 100 -cw 300 -aw 1200 -bw 45 -ew 100 -e 14 15 -g 111

"""
import time
import random
import string
import argparse
from typing import Any, Generator, cast
from datetime import datetime

from confluent_kafka import Producer, Consumer
from confluent_kafka.admin import AdminClient
import configparser

from dynreact.shortterm.common.functions import get_transport_times
from dynreact.shortterm.common import VAction, sendmsgtopic, KeySearch
from dynreact.shortterm.common.data.data_functions import end_auction
from dynreact.shortterm.common.data.data_setup import DataSetup
import os, re, json

from dynreact.shortterm.common.data.load_url import DOCKER_MANAGER
from dynreact.shortterm.common.handler import DockerManager
from dynreact.shortterm.shorttermtargets import ShortTermTargets
from dynreact.shortterm.timedelay import TimeDelay


def _key_str(key: str, default: str = "") -> str:
    """Return one ``KeySearch`` value as a string."""
    value = KeySearch.search_for_value(key, default)
    return default if value is None else str(value)


def _key_float(key: str, default: float = 0.0) -> float:
    """Return one ``KeySearch`` value as a float."""
    value = KeySearch.search_for_value(key, default)
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def list_all_topics(admin_client: AdminClient, verbose: int) -> Any:
    """
    List all topics in the Kafka broker.

    :param object admin_client: A Kafka AdminClient instance
    :param int verbose: Verbosity level
    """
    topics_metadata = admin_client.list_topics(timeout=10)

    if verbose > 0:
        print("Finished listing all hanging topics.")

    return topics_metadata.topics or []

def topic_exist(admin_client: AdminClient, topic_name: str, verbose: int) -> Any:
    """
    Check if a topic exist in the Kafka broker.
    This is necessary when to check name duplicity.

    :param object admin_client: A Kafka AdminClient instance
    :param topic_name: Topic name
    :param int verbose: Verbosity level

    :return Boolean: True if topic exists, False otherwise
    """
    topics_metadata = list_all_topics(admin_client, verbose)
    for topic_m_name in topics_metadata:
        if topic_m_name.lower() == topic_name.lower():
           return True

    return False

def delete_all_topics(admin_client: AdminClient, verbose: int) -> None:
    """
    Delete all hanging topics in the Kafka broker.
    This is necessary when a previous execution did not finish correctly
    and there are messages left in the general topic which may break subsequent executions.

    :param object admin_client: A Kafka AdminClient instance
    :param int verbose: Verbosity level
    """
    topics_metadata = list_all_topics(admin_client, verbose)
    for topic_name in topics_metadata:
        if topic_name.lower().startswith("dyn"):
            if verbose > 0:
                print(f"Deleting topic {topic_name}...")
            futures = admin_client.delete_topics([topic_name])
            if verbose > 0:
                for topic, future in futures.items():
                    print(f"Deleted topic {topic}.")
    if verbose > 0:
        print("Finished deleting all hanging topics.")


def genauction(act: str | None = None) -> str:
    """Generate the name of a topic with 12 random capital letters and digits
    :param str act: Prefered topic name for the auction.

    :return: Generated string as bae for the topic
    :rtype: str
    """
    # return(str(uuid.uuid4()))
    if act is None:
        act = ''.join(random.choices(string.ascii_uppercase + string.digits, k=12))

    topic_prefix = os.environ.get("KAFKA_TOPIC_PREFIX", "Dynreact_OSS")

    return f"{topic_prefix}-" + act

def run_general_agents(producer: Producer, gagents: str, verbose: int) -> Any:
    """
    Creates the general agents by running the corresponding scripts.

    :param object producer: A Kafka Producer instance
    :param str gagents: Hot encoded label to decide with agents to run
    :param int verbose: Verbosity level
    """

    small_wait = _key_float("SMALL_WAIT")

    log_handler = None
    equipment_handler = None
    material_handler = None

    # The general LOG must be created first in case the general topic was deleted
    if str(gagents)[0] == '1':
        log_handler = DockerManager(tag=f"log{DOCKER_MANAGER}", max_allowed=1)
        log_handler.clean_containers()
        log_handler.launch_container(name="Base", agent="log", mode="base", params={
            "verbose": verbose,
            "kafka-ip": _key_str("KAFKA_IP")
        }, auto_remove=False)
        sleep(small_wait, producer=producer, verbose=verbose)
    if str(gagents)[1] == '1':
        equipment_handler = DockerManager(tag=f"equipment{DOCKER_MANAGER}", max_allowed=1)
        equipment_handler.clean_containers()
        equipment_handler.launch_container(name="Base", agent="equipment", mode="base", params={
            "verbose": verbose,
            "kafka-ip": _key_str("KAFKA_IP")
        }, auto_remove=False)
        sleep(small_wait, producer=producer, verbose=verbose)
    if str(gagents)[2] == '1':
        material_handler = DockerManager(tag=f"material{DOCKER_MANAGER}", max_allowed=1)
        material_handler.clean_containers()
        material_handler.launch_container(name="Base", agent="material", mode="base", params={
            "verbose": verbose,
            "kafka-ip": _key_str("KAFKA_IP")
        }, auto_remove=False)
        sleep(small_wait, producer=producer, verbose=verbose)

    return log_handler, equipment_handler, material_handler


def create_auction(
        equipments: list[str], producer: Producer, verbose: int,
        snapshot: str | None = None, act: str | None = None, nmaterials: int | None = None,
        materials: list[str] | None = None, admin_client: AdminClient | None = None,
        equip_configs: dict[str, dict[str, Any]] | None = None,
        target_tons: dict[str, int | float | str] | None = None) -> tuple[str, int]:
    """
    Creates an auction by instructing the master LOG, EQUIPMENTS and MATERIAL to clone themselves to follow a new topic

    :param list equipments: List of equipments IDs that will participate in the auction
    :param object producer: A Kafka Producer instance
    :param object admin_client: A Kafka Admin Client instance
    :param int verbose: Verbosity level
    :param str snapshot: Snapshot time in ISO8601 format, otherwise use the latest available
    :param str act: Preferred auction name, otherwise a random name will be assigned
    :param int nmaterials: Maximum number of cloned used for each equipment (default is to clone all). Can't be used along materials param
    :param list materials: Selected materials to generate the auction, can't be used along nmaterials
    :param dict target_tons: Optional target tonnage by equipment id. Missing values default in the equipment agent.

    :return: Topic name of the auction and number of agents
    :rtype: tuple(str,int)
    """

    topic_gen = _key_str("TOPIC_GEN")
    transport_times_url = _key_str("TRANSPORT_TIMES_URL") or _key_str("REST_URL")

    if nmaterials is not None and materials is not None:
        dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
        raise Exception(f"{dt} | ERROR: Cannot specify both nmaterials and materials")

    # Initialize search of latest snapshot
    data_setup = DataSetup(verbose=verbose, snapshot_time=snapshot)

    # Keep track of the number of agents created
    num_agents = 0

    # Instruct the general LOG to clone itself to create a new auction
    act = genauction(act)

    if admin_client and topic_exist(admin_client=admin_client, topic_name=act, verbose=verbose):
        raise Exception(f"Topic {act} already exists. Try with another name")

    sendmsgtopic(
        producer=producer,
        tsend=topic_gen,
        topic=act,
        source="UX",
        dest="LOG:" + topic_gen,
        action="CREATE",
        payload=dict(msg=f"Created Topic {act}", variables=KeySearch.dump_model()),
        vb=verbose
    )
    num_agents += 1

    # Instruct the LOG of the auction to write a test message
    msg = "Initial Test"
    sendmsgtopic(
        producer=producer,
        tsend=act,
        topic=act,
        source="UX",
        dest="LOG:" + act,
        action="WRITE",
        payload=dict(msg=msg),
        vb=verbose
    )

    # Instruct the general EQUIPMENT to clone itself for the auction,
    # for as many times as specified by the user
    target_tons = target_tons or {}
    for equipment in equipments:

        payload_data: dict[str, Any] = dict(
            id=equipment,
            snapshot=data_setup.last_snapshot,
            variables=KeySearch.dump_model()
        )

        equipment_config: dict[str, Any] | None = None
        if equip_configs:
            equipment_config = equip_configs.get(equipment, equip_configs.get(str(equipment)))
        if equipment_config:
            payload_data['user_start_time'] = equipment_config['start_time']

        equipment_target_tons = target_tons.get(equipment, target_tons.get(str(equipment)))
        if equipment_target_tons is not None:
            payload_data['target_tons'] = equipment_target_tons

        sendmsgtopic(
            producer=producer,
            tsend=topic_gen,
            topic=act,
            source="UX",
            dest="EQUIPMENT:" + topic_gen,
            action="CREATE",
            payload=payload_data,
            vb=verbose
        )
        num_agents += 1

    # Instruct the general MATERIAL to clone itself for the auction,
    # for as many materials associated to each equipment
    all_materials: list[Any] = []

    if materials is None:
        for equipment in equipments:
            # Get the list of materials of the equipment
            equipment_ids = re.findall(r'\d+', str(equipment))

            if len(equipment_ids) == 1:
                equipment_materials = data_setup.get_equipment_materials(int(equipment_ids[0]))
                if verbose > 1:
                    msg = f"Obtained list of materials from equipment {equipment}: {equipment_materials}"
                    print(msg)
                    sendmsgtopic(
                        producer=producer, tsend=topic_gen, topic=act, source="UX", dest="LOG:" + topic_gen, action="WRITE",
                        payload=dict(msg=msg), vb=verbose
                    )
            else:
                dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
                raise Exception(f"{dt} | ERROR: No equipment ID found in equipment {equipment}")

            if materials is None and nmaterials is not None:
                all_materials.extend(equipment_materials[:nmaterials])
            else:
                all_materials.extend(equipment_materials)

            print("Current material list size is {}".format(len(all_materials)))
    else:
        all_materials = materials

    # # If the user provided the materials make sure all are part of at least one equipment
    # if materials is not None:
    #     if all(item in all_materials for item in materials):
    #         all_materials = materials
    #     else:
    #         unwanted = [item for item in materials if item not in all_materials]
    #         dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
    #         raise Exception(f"{dt} | ERROR: Provided materials {unwanted} are not part of the selected equipment")

    all_materials = list(set(all_materials))
    print("Final material list size is {}".format(len(all_materials)))

    transport_times = get_transport_times(transport_times_url)
    print(f"Transport times: {transport_times}")

    # Clone the master MATERIAL for each material ID
    for material in all_materials:
        sendmsgtopic(
            producer=producer,
            tsend=topic_gen,
            topic=act,
            source="UX",
            dest="MATERIAL:" + topic_gen,
            action="CREATE",
            payload=dict(
                id=str(material),
                params=data_setup.get_material_params(material),
                transport_times=transport_times,
                variables=KeySearch.dump_model()
            ),
            vb=verbose
        )
        num_agents += 1

    return act, num_agents


def start_auction(topic: str, producer: Producer, consumer: Consumer, num_agents: int, verbose: int) -> None:
    """
    Starts an auction by instructing the LOG to check the presence of all agents

    :param str topic: Topic name of the auction we want to start
    :param object producer: A Kafka Producer instance
    :param object consumer: A Kafka Consumer instance
    :param int num_agents:
    :param int verbose: Verbosity level
    """

    topic_gen = _key_str("TOPIC_GEN")
    topic_callback = _key_str("TOPIC_CALLBACK")

    sendmsgtopic(
        producer=producer, tsend=topic_gen, topic=topic, source="UX", dest="LOG:" + topic_gen,
        action="WRITE", payload=dict(msg="Starting auction"), vb=verbose
    )

    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="LOG:" + topic,
        action="CHECK",
        payload=dict(num_agents=num_agents),
        vb=verbose
    )

    time.sleep(_key_float("SMALL_WAIT"))

    sendmsgtopic(
        producer=producer, tsend=topic_gen, topic=topic, source="UX", dest="LOG:" + topic_gen,
        action="WRITE", payload=dict(msg="Waiting for auction confirmation"), vb=verbose
    )

    for i in range(5):

        sendmsgtopic(
            producer=producer,
            tsend=topic,
            topic=topic,
            source="UX",
            dest="LOG:" + topic,
            action="ISAUCTIONACTIVE",
            vb=verbose
        )

        message_objs = wait_for_callback(topic_callback, "AUCTIONSTARTED", consumer, verbose, sleep_timeout=2, max_iters=10)

        for message in message_objs:

            if message is None:
                print("Exiting start auction loop")
                break
            else:
                print(json.dumps(message["payload"]))

            payload = json.loads(message['payload']) if (type(message["payload"]) is str) else message['payload']
            if payload["is_auction_started"]:
                return
            elif payload["total_num_agents"] < payload["present_agents"]["total"]:
                dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
                raise Exception(f"{dt} | ERROR: More agents responded than expected. Expected {payload["total_num_agents"]["total"]} got {payload["present_agents"]}")

    dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
    raise Exception(f"{dt} | ERROR: Failed to start/run auction, timeout exceeded")


def wait_for_callback(
        topic: str, expected_action: str, consumer: Consumer, verbose: int,
        sleep_timeout: int = 1, max_iters: int = 10
) -> Generator[dict[str, Any] | None, None, None]:
    """
    Starts an auction by instructing the LOG to check the presence of all agents

    :param str topic: Topic name of the auction we want to start
    :param str expected_action: The message action your expecting
    :param object consumer: A Kafka Consumer instance
    :param int verbose: Verbosity level
    :param int sleep_timeout: Sleep timeout to wait for message
    :param int max_iters:
        Maximum iterations with no message (if this parameter is 1, the loop will stop once there are no more messages)
    """

    # Consume all messages until reaching a message destined for UX or exhausting the maximum number of iterations
    iter_no_msg = 0
    while iter_no_msg < max_iters:
        message_obj = consumer.poll(timeout=1)
        if message_obj.__str__() == 'None':
            iter_no_msg += 1
            # if verbose > 0 and (iter_no_msg - 1) % 5 == 0:
                # msg = f"Iteration {iter_no_msg - 1}. No message found."
                # sendmsgtopic(
                #     producer=producer, tsend=KeySearch.search_for_value("TOPIC_GEN"), topic=topic, source="UX", dest="LOG:" + KeySearch.search_for_value("TOPIC_GEN"),
                #     action="WRITE", payload=dict(msg=msg), vb=verbose
                # )
            time.sleep(sleep_timeout)
        else:
            iter_no_msg = 0

            if message_obj is not None:
                messtpc = message_obj.topic()
                vals = message_obj.value()
                msg_error = message_obj.error()
            else:
                continue
            if messtpc is None or vals is None:
                iter_no_msg += 1
                time.sleep(sleep_timeout)
                continue

            message_is_ok = all([
                messtpc == topic, 'Subscribed topic not available' not in str(vals), msg_error is None
            ])

            if message_is_ok:

                consumer.commit(message_obj)

                dctmsg = json.loads(vals.decode("utf-8") if isinstance(vals, bytes) else vals)
                match = re.search(dctmsg['dest'], "UX")
                action = dctmsg['action'].upper()

                if match and action == expected_action:
                    yield dctmsg

    print("No message found")
    return None

def ask_results(
        topic: str, producer: Producer, consumer: Consumer, verbose: int, wait_answer: float = 5., max_iters: int = 10
) -> dict:
    """
    Asks the LOG of the auction to get the results of the auction.

    :param str topic: Topic name of the auction we want to start
    :param object producer: A Kafka Producer instance
    :param object consumer: A Kafka Consumer instance
    :param int verbose: Verbosity level
    :param float wait_answer: Number of seconds to wait for an answer
    :param int max_iters:
        Maximum iterations with no message (if this parameter is 1, the loop will stop once there are no more messages)
    """

    topic_gen = _key_str("TOPIC_GEN")
    topic_callback = _key_str("TOPIC_CALLBACK")

    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="LOG:" + topic,
        action="ASKRESULTS",
        vb=verbose
    )
    if verbose > 0:
        msg = f"Requested results from LOG"
        sendmsgtopic(
            producer=producer, tsend=topic_gen, topic=topic, source="UX", dest="LOG:" + topic_gen, action="WRITE",
            payload=dict(msg=msg), vb=verbose
        )

    sleep(wait_answer, producer=producer, verbose=verbose)

    message_objs = wait_for_callback(topic_callback, "RESULTS", consumer, verbose)

    for message in message_objs:

        if message is None:
            print("Exiting ask results loop")
            break

        payload = json.loads(message['payload']) if (type(message["payload"]) is str) else message['payload']
        if verbose > 0:
            msg = f"Obtained results: {payload}"
            sendmsgtopic(
                producer=producer, tsend=topic_callback, topic=topic, source="UX", dest="LOG:" + topic_gen,
                action="WRITE", payload=dict(msg=msg), vb=verbose
            )
        return payload


    if verbose > 0:
        msg = f"Did not obtain results after waiting for {wait_answer}s and having {max_iters} iters with no message"
        sendmsgtopic(
            producer=producer, tsend=topic_callback, topic=topic, source="UX", dest="LOG:" + topic_gen, action="WRITE",
            payload=dict(msg=msg), vb=verbose
        )
    return dict()


def _equipment_order_scope(equipments: list[str], snapshot: str, nmaterials: int | None, materials: list[str] | None = None) -> dict[str, set[str]]:
    """
    Return the order ids that belong to the material selection requested for each equipment.
    """
    data_setup = DataSetup(verbose=0, snapshot_time=snapshot)
    scope = {str(equipment): set() for equipment in equipments}

    if materials is not None:
        for material_id in materials:
            order = data_setup.get_material_params(material_id)["order"]
            order_id = order["id"]
            allowed_equipment = {str(equipment_id) for equipment_id in order.get("allowed_equipment", [])}
            for equipment in scope:
                if equipment in allowed_equipment:
                    scope[equipment].add(order_id)
        return scope

    for equipment in equipments:
        equipment_key = str(equipment)
        equipment_id = int(equipment_key)
        material_ids = data_setup.get_equipment_materials(equipment_id)
        selected_materials = material_ids[:nmaterials] if nmaterials else material_ids
        scope[equipment_key] = {
            data_setup.get_material_params(material_id)["order"]["id"]
            for material_id in selected_materials
        }
    return scope


def normalize_auction_results(results: dict, order_scope: dict[str, set[str]] | None = None) -> dict:
    """
    Compact auction results to one entry per order and equipment.

    Multiple materials can belong to the same order and trigger repeated
    confirmations across rounds. The external auction result is expected to
    represent unique orders per equipment, so we keep the most recent entry
    for each order id within every equipment bucket.
    """
    normalized_results = {}

    for equipment, assignments in results.items():
        equipment_key = str(equipment)
        if not isinstance(assignments, list):
            normalized_results[equipment] = assignments
            continue

        latest_assignment_by_order = {}
        assignment_order = []

        for assignment in assignments:
            if not isinstance(assignment, dict):
                continue

            order_id = assignment.get("id")
            if order_id is None:
                continue
            order_id = str(order_id)

            allowed_equipment = {str(equipment_id) for equipment_id in assignment.get("allowed_equipment", [])}
            if allowed_equipment and equipment_key not in allowed_equipment:
                continue

            if order_scope is not None and order_id not in order_scope.get(equipment_key, set()):
                continue

            if order_id not in latest_assignment_by_order:
                assignment_order.append(order_id)
                latest_assignment_by_order[order_id] = assignment
                continue

            previous_assignment = latest_assignment_by_order[order_id]
            previous_round = int(previous_assignment.get("round", -1))
            current_round = int(assignment.get("round", -1))

            if current_round >= previous_round:
                latest_assignment_by_order[order_id] = assignment

        normalized_results[equipment] = [
            latest_assignment_by_order[order_id]
            for order_id in assignment_order
            if order_id in latest_assignment_by_order
        ]

    return normalized_results


def sleep(seconds: float | int | None, producer: Producer, verbose: int) -> None:
    """
    Sleep for the specified number of seconds and notify the general LOG about it.

    :param float seconds: Number of seconds to be waited. 
    :param object producer: Kafka object producer.
    :param int verbose: Level of verbosity.
    """

    seconds_value = 0.0 if seconds is None else float(seconds)
    topic_gen = _key_str("TOPIC_GEN")

    if verbose > 0:
        sendmsgtopic(
            producer=producer, tsend=topic_gen, topic=topic_gen, source="UX", dest="LOG:" + topic_gen, action="WRITE",
            payload=dict(msg=f"Waiting for {seconds_value}s..."), vb=verbose
        )
    time.sleep(seconds_value)

def main() -> Any:
    """
    Main module to capture arguments from command line
    params are provided as external arguments in command line.

    :param int verbose: Verbosity level.
    :param str runningWait: Number of seconds to wait for the general agents to start running.
    :param str cloningWait: Number of seconds to wait for the agents to clone themselves.
    :param str auctionWait: Number of seconds to wait for the auction to start and finish.
    :param str counterbidWait: Number of seconds that each equipment waits for all materials to counterbid.
    :param str exitWait: Number of seconds to wait for the agents to exit.
    :param str equipments: One or more equipment IDs (e.g., '08')
    :param int nmaterials: Maximum number of materials cloned for each equipment (default is to clone all materials)
    """
    # Extract the command line arguments
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-v", "--verbose", nargs='?', action=VAction,
        dest='verbose', help="Option for detailed information"
    )
    ap.add_argument(
        "-rw", "--runningWait", type=str, required=True,
        help="Number of seconds to wait for the general agents to start running"
    )
    ap.add_argument(
        "-cw", "--cloningWait", type=str, required=True,
        help="Number of seconds to wait for the agents to clone themselves"
    )
    ap.add_argument(
        "-aw", "--auctionWait", type=str, required=True,
        help="Number of seconds to wait for the auction to start and finish"
    )
    ap.add_argument(
        "-bw", "--counterbidWait", type=str, required=True,
        help="Number of seconds that each equipment waits for all materials to counterbid"
    )
    ap.add_argument(
        "-sw", "--smallWait", type=str, required=True, default="5",
        help="Number of seconds to sleep for small waiting times"
    )
    ap.add_argument(
        "-ew", "--exitWait", type=str, required=True,
        help="Number of seconds to wait for the agents to exit"
    )
    ap.add_argument(
        "-e", "--equipments", metavar='EQUIPMENT_ID', default="", type=str, nargs='+',
        help="One or more equipments IDs (e.g., '08')"
    )
    ap.add_argument(
        "-n", "--nmaterials", default=0, type=int,
        help="Maximum number of materials cloned for each equipment (default is to clone all materials)"
    )
    ap.add_argument(
        "-g", "--rungagents", default='000', type=str,
        help="0 => General agents are not launched; 100 => Material ; 010 => Equipment; 001 => Log; "
    )

    ap.add_argument(
        "-sn", "--snapshot", type=str,
        help="Optional snapshot time in ISO8601 format, otherwise use the latest available"
    )
    ap.add_argument(
        "-st", "--start_time", dest="start_time", type=str,
        help="Start time"
    )
    args = vars(ap.parse_args())

    return execute_short_term_planning(args)


def execute_short_term_planning(args: dict) -> Any:
    """
    Method to running tests for validation

    param dict args: Arguments to run the test. Definition is mentioned the in the main method
    """

    verbose = args["verbose"]
    if verbose is None:
        verbose = 0
    running_wait = int(args["runningWait"])
    cloning_wait = int(args["cloningWait"])
    auction_wait = int(args["auctionWait"])
    exit_wait = int(args["exitWait"])
    counterbid_wait = int(args["counterbidWait"])
    small_wait = int(args["smallWait"])

    rungagnts = str(args['rungagents'])
    equipments = args["equipments"]
    snapshot = args["snapshot"]
    nmaterials = args["nmaterials"]
    start_time = args["start_time"]

    time_delay = TimeDelay(AUCTION_WAIT=auction_wait, COUNTERBID_WAIT=counterbid_wait,
                           EXIT_WAIT=exit_wait, CLONING_WAIT=cloning_wait, RUNNING_WAIT=running_wait, SMALL_WAIT=small_wait)

    # Other arguments will be retrieved from env variables
    short_term_config = cast(ShortTermTargets, ShortTermTargets().model_copy(update={"VB": verbose, "TimeDelays": time_delay}))  # type: ignore

    # Class method
    KeySearch.set_global(config_provider=short_term_config)

    if os.environ.get('SPHINX_BUILD'):
        # Mock REST_URL for Sphinx Documentation
        ip = '127.0.0.1:9092'
    else:
        ip = _key_str("KAFKA_IP")

    if verbose > 0:
        print(
            f"Running program with {verbose=}, RW={_key_float('RUNNING_WAIT')}, CW={_key_float('CLONING_WAIT')}, AW={_key_float('AUCTION_WAIT')}, "
            f"BW={_key_float('COUNTERBID_WAIT')} EW={_key_float('EXIT_WAIT')} SW={_key_float('SLEEP_WAIT')}, {equipments=}, {nmaterials=}, {snapshot=}, {rungagnts=}."
        )

    producer_config = {
        "bootstrap.servers": ip,
        'linger.ms': 100,  # Reduce latency
        'acks': 'all'  # Ensure message durability
    }
    producer = Producer(producer_config)
    consumer_config = {
        "bootstrap.servers": ip,
        "group.id": "UX",
        "auto.offset.reset": "earliest",
        'enable.auto.commit': False
    }
    consumer = Consumer(consumer_config)
    act = ""

    if int(rungagnts) > 0:

        min_base_agents = sum(int(bit) for bit in str(rungagnts))
        running_base_agents = 0

        log_handler, equipment_handler, material_handler = run_general_agents(
            producer=producer,
            gagents=rungagnts,
            verbose=verbose
        )
        sleep(_key_float("RUNNING_WAIT"), producer=producer, verbose=verbose)

        if str(rungagnts)[0] == '1' and log_handler is not None:
            log_tracked  = len(list(filter(lambda x: x["status"] == "running", log_handler.list_tracked_containers())))
            running_base_agents = running_base_agents + log_tracked

            if verbose >= 3:
                print(f"Tracked {log_tracked} LOG containers")
        if str(rungagnts)[1] == '1' and equipment_handler is not None:
            equipment_tracked = len(list(filter(lambda x: x["status"] == "running", equipment_handler.list_tracked_containers())))
            running_base_agents = running_base_agents + equipment_tracked

            if verbose >= 3:
                print(f"Tracked {equipment_tracked} EQUIPMENT containers")
        if str(rungagnts)[2] == '1' and material_handler is not None:
            material_tracked = len(list(filter(lambda x: x["status"] == "running", material_handler.list_tracked_containers())))
            running_base_agents = running_base_agents + material_tracked

            if verbose >= 3:
                print(f"Tracked {material_tracked} MATERIAL containers")

        if running_base_agents < min_base_agents:
            raise Exception(
                f"Missing base agents, expected {min_base_agents} currently running {running_base_agents}. Aborting!")

    results = {}

    equip_configs = {equipment: {'start_time': start_time} for equipment in equipments} if start_time else None
    order_scope = _equipment_order_scope(equipments=equipments, snapshot=snapshot, nmaterials=nmaterials, materials=None)

    try:
        act, n_agents = create_auction(
            equipments=equipments, producer=producer, verbose=verbose,
            nmaterials=nmaterials, snapshot=snapshot, equip_configs=equip_configs
        )

        print(f"Creating auction for topic {act}")

        consumer.subscribe([act, _key_str("TOPIC_CALLBACK")])
        sleep(_key_float("CLONING_WAIT"), producer=producer, verbose=verbose)

        if n_agents > 1:
            start_auction(topic=act, consumer=consumer, producer=producer, verbose=verbose, num_agents=n_agents)
            sleep(_key_float("AUCTION_WAIT"), producer=producer, verbose=verbose)
            results = ask_results(topic=act, producer=producer, consumer=consumer, verbose=verbose)
            results = normalize_auction_results(results, order_scope=order_scope)
            if verbose > 0:
                print("---- RESULTS ----")
                print(results)
                print("----  ----")
            sleep(_key_float("SMALL_WAIT"), producer=producer, verbose=verbose)
    finally:
        end_auction(topic=act, producer=producer, verbose=verbose, wait_time=int(_key_float("SMALL_WAIT")))
        sleep(_key_float("EXIT_WAIT"), producer=producer, verbose=verbose)

        # Remove all main agents
        clean_agents(producer, verbose, rungagnts)

        sleep(_key_float("SMALL_WAIT"), producer=producer, verbose=verbose)

    return results

def clean_agents(producer: Producer, verbose: int, rungagnts: str) -> None:

    """Clean agents.
    
    This function is part of the short-term planning workflow and keeps
    the existing runtime behavior while documenting the public contract.
    
    Args:
        producer: Input value for the `producer` parameter.
        verbose: Input value for the `verbose` parameter.
        rungagnts: Input value for the `rungagnts` parameter.
    
    Returns:
        The value produced by the underlying planning, UI, or test helper logic.
    """
    topic_gen = _key_str("TOPIC_GEN")

    if int(rungagnts) > 0:
        # Exit EQUIPMENT BASE
        if str(rungagnts)[1] == '1':
            sendmsgtopic(
                producer=producer,
                tsend=topic_gen,
                topic=topic_gen,
                source="UX",
                dest=f"EQUIPMENT:{topic_gen}",
                action="EXIT",
                vb=verbose
            )

        # Exit MATERIAL BASE
        if str(rungagnts)[2] == '1':
            sendmsgtopic(
                producer=producer,
                tsend=topic_gen,
                topic=topic_gen,
                source="UX",
                dest=f"MATERIAL:{topic_gen}",
                action="EXIT",
                vb=verbose
            )

        # Exit LOG BASE
        if str(rungagnts)[0] == '1':
            sleep(_key_float("SMALL_WAIT"), producer=producer, verbose=verbose)
            sendmsgtopic(
                producer=producer,
                tsend=topic_gen,
                topic=topic_gen,
                source="UX",
                dest=f"LOG:{topic_gen}",
                action="EXIT",
                vb=verbose
            )


if __name__ == '__main__':
    main()
