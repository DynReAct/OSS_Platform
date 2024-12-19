"""
Module: ShortTermPlanning.py

This program runs the scripts required to start the general agents,
clones them for an auction with the resources indicated by the user,
and starts the auction, waiting for its completion.

First Prototype of Kubernetes oriented solution for the UX service

Version History:
- 1.0 (2024-03-09): Initial version developed by Rodrigo Castro Freibott.
- 1.1 (2024-10-30): Updated version (JOM).

Note:

    To run scenario 05, use: python3 ShortTermPlanning.py -v 3  -b . -rw 10 -cw 30 -aw 50 -bw 15 -ew 10 -r 14 -n 1
    To run scenario 06, use: python3 ShortTermPlanning.py -v 3  -b . -rw 10 -cw 30 -aw 50 -bw 15 -ew 10 -r 14 -n 2
    To run scenario 07, use: python3 ShortTermPlanning.py -v 3 -b . -rw 10 -cw 30 -aw 200 -bw 15 -ew 10 -r 14 15 -n 1

    To run a reduced version, use: python3 ShortTermPlanning.py -v 3 -b . -rw 10 -cw 30 -aw 200 -bw 15 -ew 10 -r 14 15 -n 4
    To run a full version, use: python3 ShortTermPlanning.py -v 3 -b . -rw 100 -cw 300 -aw 1200 -bw 45 -ew 100 -r 14 15

"""

import time
import random
import string
import argparse
from confluent_kafka import Producer, Consumer
from confluent_kafka.admin import AdminClient
import configparser
from common import VAction, sendmsgtopic, TOPIC_GEN
from data.data_functions import get_equipment_materials
import subprocess, sys, os, re, json


if os.environ.get('SPHINX_BUILD'):
    # Mock REST_URL for Sphinx Documentatiom
    IP = '127.0.0.1:9092'
else:
    config = configparser.ConfigParser()
    config.read('config.cnf')
    IP = config['DEFAULT']['IP']

PYTHON_PATH = sys.executable
SCRIPT_LOG = "log.py"
SCRIPT_RESOURCE = "resource.py"
SCRIPT_MATERIAL = "material.py"

SMALL_WAIT = 5


def delete_all_topics(admin_client: AdminClient, verbose: int):
    """
    Delete all hanging topics in the Kafka broker.
    This is necessary when a previous execution did not finish correctly
    and there are messages left in the general topic which may break subsequent executions.

    :param object admin_client: A Kafka AdminClient instance
    :param int verbose: Verbosity level
    """
    topics_metadata = admin_client.list_topics(timeout=10)
    if topics_metadata.topics:
        for topic_name in topics_metadata.topics:
            if not topic_name.startswith("__"):
                if verbose > 0:
                    print(f"Deleting topic {topic_name}...")
                futures = admin_client.delete_topics([topic_name])
                if verbose > 0:
                    for topic, future in futures.items():
                        print(f"Deleted topic {topic}.")
    if verbose > 0:
        print("Finished deleting all hanging topics.")


def genauction() -> str:
    """Generate the name of a topic with 12 random capital letters and digits

    :return: Generated string as bae for the topic
    :rtype: str
    """
    # return(str(uuid.uuid4()))
    N = 12
    res = ''.join(random.choices(string.ascii_uppercase + string.digits, k=N))
    return 'DynReact-' + res


def run_script(script: str, producer: Producer, base: str, verbose: int):
    """
    Run the given script and notify the LOG about it.

    :param str script: Path to the script to run
    :param object producer: A Kafka Producer instance
    :param str base: Path to the configuration file (with the IP address)
    :param int verbose: Verbosity level
    """
    command = [PYTHON_PATH, script, "-b", base, "-v", str(verbose)]
    # We use subprocess.Popen() instead of subprocess.run() because we don't want to wait for the program to finish
    subprocess.Popen(command)
    if verbose > 1:
        msg = f"Executed program {script} to create the general {script.split('.')[0].upper()} agent."
        sendmsgtopic(
            producer=producer, tsend=TOPIC_GEN, topic=TOPIC_GEN, source="UX", dest="LOG:" + TOPIC_GEN,
            action="WRITE", payload=dict(msg=msg), vb=verbose
        )


def run_general_agents(producer: Producer, base: str, verbose: int):
    """
    Creates the general agents by running the corresponding scripts.

    :param object producer: A Kafka Producer instance
    :param str base: Path to the configuration file (with the IP address)
    :param int verbose: Verbosity level
    """
    # The general LOG must be created first in case the general topic was deleted
    run_script(SCRIPT_LOG, producer=producer, base=base, verbose=verbose)
    sleep(SMALL_WAIT, producer=producer, verbose=verbose)
    run_script(SCRIPT_RESOURCE, producer=producer, base=base, verbose=verbose)
    run_script(SCRIPT_MATERIAL, producer=producer, base=base, verbose=verbose)


def create_auction(
        resources: list[str], producer: Producer, verbose: int, counterbid_wait: float, nmaterials: int = None
) -> tuple[str, int]:
    """
    Creates an auction by instructing the master LOG, RESOURCE and MATERIAL to clone themselves to follow a new topic

    :param list resources: List of resource IDs that will participate in the auction
    :param object producer: A Kafka Producer instance
    :param int verbose: Verbosity level
    :param float counterbid_wait: Number of seconds to wait for the materials to counterbid
    :param int nmaterials: Maximum number of materials cloned for each resource (default is to clone all)

    :return: Topic name of the auction and number of agents
    :rtype: tuple(str,int)
    """
    # Keep track of the number of agents created
    num_agents = 0

    # Instruct the general LOG to clone itself to create a new auction
    act = genauction()
    sendmsgtopic(
        producer=producer,
        tsend=TOPIC_GEN,
        topic=act,
        source="UX",
        dest="LOG:" + TOPIC_GEN,
        action="CREATE",
        payload=dict(msg=f"Created Topic {act}"),
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

    # Instruct the general RESOURCE to clone itself for the auction,
    # for as many times as specified by the user
    for resource in resources:
        sendmsgtopic(
            producer=producer,
            tsend=TOPIC_GEN,
            topic=act,
            source="UX",
            dest="RESOURCE:" + TOPIC_GEN,
            action="CREATE",
            payload=dict(id=resource, counterbid_wait=counterbid_wait),
            vb=verbose
        )
        num_agents += 1

    # Instruct the general MATERIAL to clone itself for the auction,
    # for as many materials associated to each resource
    for resource in resources:
        # Get the list of materials of the resource
        resource_materials = get_equipment_materials(int(resource))
        if verbose > 1:
            msg = f"Obtained list of materials from equipment {resource}: {resource_materials}"
            sendmsgtopic(
                producer=producer, tsend=TOPIC_GEN, topic=act, source="UX", dest="LOG:" + TOPIC_GEN, action="WRITE",
                payload=dict(msg=msg), vb=verbose
            )

        # If a maximum number of materials is given, keep only the first `nmaterials` materials of the resource
        if nmaterials is not None:
            resource_materials = resource_materials[:nmaterials]

        # Clone the master MATERIAL for each material ID
        for material in resource_materials:
            sendmsgtopic(
                producer=producer,
                tsend=TOPIC_GEN,
                topic=act,
                source="UX",
                dest="MATERIAL:" + TOPIC_GEN,
                action="CREATE",
                payload=dict(id=str(material)),
                vb=verbose
            )
            num_agents += 1

    return act, num_agents


def start_auction(topic: str, producer: Producer, num_agents: int, verbose: int) -> None:
    """
    Starts an auction by instructing the LOG to check the presence of all agents

    :param str topic: Topic name of the auction we want to start
    :param object producer: A Kafka Producer instance
    :param int num_agents:
    :param int verbose: Verbosity level
    """
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
            producer=producer, tsend=TOPIC_GEN, topic=topic, source="UX", dest="LOG:" + TOPIC_GEN, action="WRITE",
            payload=dict(msg=msg), vb=verbose
        )

    sleep(wait_answer, producer=producer, verbose=verbose)

    # Consume all messages until reaching a message destined for UX or exhausting the maximum number of iterations
    iter_no_msg = 0
    while iter_no_msg < max_iters:
        message_obj = consumer.poll(timeout=1)
        if message_obj.__str__() == 'None':
            iter_no_msg += 1
            if verbose > 0 and (iter_no_msg - 1) % 5 == 0:
                msg = f"Iteration {iter_no_msg - 1}. No message found."
                sendmsgtopic(
                    producer=producer, tsend=TOPIC_GEN, topic=topic, source="UX", dest="LOG:" + TOPIC_GEN,
                    action="WRITE", payload=dict(msg=msg), vb=verbose
                )
            time.sleep(1)
        else:
            messtpc = message_obj.topic()
            vals = message_obj.value()
            consumer.commit(message_obj)
            message_is_ok = all([
                messtpc == topic, 'Subscribed topic not available' not in str(vals), not message_obj.error()
            ])
            if message_is_ok:
                dctmsg = json.loads(vals)
                match = re.search(dctmsg['dest'], "UX")
                action = dctmsg['action'].upper()
                if match and action == "RESULTS":
                    results = dctmsg['payload']
                    if verbose > 0:
                        msg = f"Obtained results: {results}"
                        sendmsgtopic(
                            producer=producer, tsend=TOPIC_GEN, topic=topic, source="UX", dest="LOG:" + TOPIC_GEN,
                            action="WRITE", payload=dict(msg=msg), vb=verbose
                        )
                    return results

    if verbose > 0:
        msg = f"Did not obtain results after waiting for {wait_answer}s and having {max_iters} iters with no message"
        sendmsgtopic(
            producer=producer, tsend=TOPIC_GEN, topic=topic, source="UX", dest="LOG:" + TOPIC_GEN, action="WRITE",
            payload=dict(msg=msg), vb=verbose
        )
    return dict()


def end_auction(topic: str, producer: Producer, verbose: int) -> None:
    """
    Ends an auction by instructing all RESOURCE, MATERIAL and LOG children of the auction to exit

    :param str topic: Topic name of the auction we want to end
    :param object producer: A Kafka Producer instance
    :param int verbose: Verbosity level
    """
    # Instruct all RESOURCE children to exit
    # We can define the destinations of the message using a regex instead of looping through all resource IDs
    # In this case, the regex ".*" matches any sequence of characters; that is, any resource ID
    sendmsgtopic(
        producer=producer,
        tsend=topic,
        topic=topic,
        source="UX",
        dest="RESOURCE:" + topic + ":.*",
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


def sleep(seconds: float, producer: Producer, verbose: int):
    """
    Sleep for the specified number of seconds and notify the general LOG about it.

    :param float seconds: Number of seconds to be waited. 
    :param object producer: Kafka object producer.
    :param int verbose: Level of verbosity.
    """
    if verbose > 0:
        sendmsgtopic(
            producer=producer, tsend=TOPIC_GEN, topic=TOPIC_GEN, source="UX", dest="LOG:" + TOPIC_GEN, action="WRITE",
            payload=dict(msg=f"Waiting for {seconds}s..."), vb=verbose
        )
    time.sleep(seconds)


def main():
    """
    Main module running tests for validation
    params are provided as external arguments in command line.

    :param str base: Path to the config file.
    :param int verbose: Verbosity level.
    :param str runningWait: Number of seconds to wait for the general agents to start running.
    :param str cloningWait: Number of seconds to wait for the agents to clone themselves.
    :param str auctionWait: Number of seconds to wait for the auction to start and finish.
    :param str counterbidWait: Number of seconds that each resource waits for all materials to counterbid.
    :param str exitWait: Number of seconds to wait for the agents to exit.
    :param str resources: One or more resource IDs (e.g., '08')
    :param int nmaterials: Maximum number of materials cloned for each resource (default is to clone all materials)
    """
    # Extract the command line arguments
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-v", "--verbose", nargs='?', action=VAction,
        dest='verbose', help="Option for detailed information"
    )
    ap.add_argument(
        "-b", "--base", type=str, dest="base", required=True,
        help="Path from current place to find config.cnf file"
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
        help="Number of seconds that each resource waits for all materials to counterbid"
    )
    ap.add_argument(
        "-ew", "--exitWait", type=str, required=True,
        help="Number of seconds to wait for the agents to exit"
    )
    ap.add_argument(
        "-r", "--resources", metavar='RESOURCE_ID', type=str, nargs='+',
        help="One or more resource IDs (e.g., '08')"
    )
    ap.add_argument(
        "-n", "--nmaterials", default=None, type=int,
        help="Maximum number of materials cloned for each resource (default is to clone all materials)"
    )
    args = vars(ap.parse_args())

    verbose = args["verbose"]
    base = args["base"]
    running_wait = int(args["runningWait"])
    cloning_wait = int(args["cloningWait"])
    auction_wait = int(args["auctionWait"])
    counterbid_wait = float(args["counterbidWait"])
    exit_wait = int(args["exitWait"])
    resources = args["resources"]
    nmaterials = args["nmaterials"]
    if verbose > 0:
        print(
            f"Running program with {verbose=}, {base=}, {running_wait=}, {cloning_wait=}, {auction_wait=}, "
            f"{counterbid_wait=} {exit_wait=}, {resources=}, {nmaterials=}."
        )

    # Uncomment this if there are any uncompleted previous executions that left harmful messages in the general topic
    # admin_client = AdminClient({"bootstrap.servers": IP})
    # delete_all_topics(admin_client, verbose=verbose)

    producer_config = {"bootstrap.servers": IP}
    producer = Producer(producer_config)
    consumer_config = {"bootstrap.servers": IP, "group.id": "UX", "auto.offset.reset": "earliest"}
    consumer = Consumer(consumer_config)

    run_general_agents(producer=producer, base=base, verbose=verbose)
    sleep(running_wait, producer=producer, verbose=verbose)

    act, n_agents = create_auction(
        resources=resources, producer=producer, verbose=verbose, counterbid_wait=counterbid_wait, nmaterials=nmaterials
    )
    consumer.subscribe([act])
    sleep(cloning_wait, producer=producer, verbose=verbose)

    start_auction(topic=act, producer=producer, verbose=verbose, num_agents=n_agents)
    sleep(auction_wait, producer=producer, verbose=verbose)

    results = ask_results(topic=act, producer=producer, consumer=consumer, verbose=verbose)
    if verbose > 0:
        print("---- RESULTS ----")
        print(results)
        print("----  ----")
    sleep(SMALL_WAIT, producer=producer, verbose=verbose)

    end_auction(topic=act, producer=producer, verbose=verbose)
    sleep(exit_wait, producer=producer, verbose=verbose)

    # Instruct the LOG of the auction to exit
    sendmsgtopic(
        producer=producer,
        tsend=act,
        topic=act,
        source="UX",
        dest="LOG:" + act,
        action="EXIT",
        vb=verbose
    )

    # Instruct all general agents (except the LOG) to exit
    sendmsgtopic(
        producer=producer,
        tsend=TOPIC_GEN,
        topic=TOPIC_GEN,
        source="UX",
        dest=f"^(?!.*LOG:{TOPIC_GEN}).*$",
        action="EXIT",
        vb=verbose
    )
    sleep(SMALL_WAIT, producer=producer, verbose=verbose)

    # Instruct the general LOG to exit
    sendmsgtopic(
        producer=producer,
        tsend=TOPIC_GEN,
        topic=TOPIC_GEN,
        source="UX",
        dest=f"LOG:{TOPIC_GEN}",
        action="EXIT",
        vb=verbose
    )
    sleep(SMALL_WAIT, producer=producer, verbose=verbose)

    return None


if __name__ == '__main__':
    main()
