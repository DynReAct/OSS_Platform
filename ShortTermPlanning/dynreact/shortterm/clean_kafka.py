"""
Module: clean_kafka.py

This program runs the scripts required to start the general agents,
clones them for an auction with the equipments indicated by the user,
and starts the auction, waiting for its completion.

First Prototype of Kubernetes oriented solution for the UX service

Version History:
- 1.0 (2024-03-09): Initial version developed by Rodrigo Castro Freibott.

Note:

    To run scenario 05, use: python3 ux.py -v 3  -b . -rw 10 -cw 30 -aw 50 -bw 15 -ew 10 -r 14 -n 1
    To run scenario 06, use: python3 ux.py -v 3  -b . -rw 10 -cw 30 -aw 50 -bw 15 -ew 10 -r 14 -n 2
    To run scenario 07, use: python3 ux.py -v 3 -b . -rw 10 -cw 30 -aw 200 -bw 15 -ew 10 -r 14 15 -n 1

    To run a reduced version, use: python3 ux.py -v 3 -b . -rw 10 -cw 30 -aw 200 -bw 15 -ew 10 -r 14 15 -n 4
    To run a full version, use: python3 ux.py -v 3 -b . -rw 100 -cw 300 -aw 1200 -bw 45 -ew 100 -r 14 15

"""

import time, os, sys, random, string,re,json
import argparse
from confluent_kafka import Producer, Consumer
from confluent_kafka.admin import AdminClient
import configparser
from common import VAction, sendmsgtopic, TOPIC_GEN
from data.data_functions import get_equipment_materials
import subprocess


config = configparser.ConfigParser()
config.read('config.cnf')
if os.environ.get('SPHINX_BUILD'):
    # Mock REST_URL for Sphinx Documentatiom
    IP = '127.0.0.1:9092'
else:
    IP = config['DEFAULT']['IP']

PYTHON_PATH = sys.executable
SCRIPT_LOG = "log.py"
SCRIPT_RESOURCE = "equipment.py"
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


def sleep(seconds: float, producer: Producer, verbose: int):
    """Sleep for the specified number of seconds and notify the general LOG about it

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
    Main module focused on cleaning the kafka queue.
    params are provided as external arguments in command line.
    
    :param str base: Path to the config file.
    :param int verbose: Verbosity level.
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
    args = vars(ap.parse_args())

    verbose = args["verbose"]
    base = args["base"]
    if verbose > 0:
        print( f"Running program with {verbose=}, {base=} ")

    # Uncomment this if there are any uncompleted previous executions that left harmful messages in the general topic
    admin_client = AdminClient({"bootstrap.servers": IP})
    delete_all_topics(admin_client, verbose=verbose)

    producer_config = {"bootstrap.servers": IP}
    producer = Producer(producer_config)
    consumer_config = {"bootstrap.servers": IP, "group.id": "UX", "auto.offset.reset": "earliest"}
    consumer = Consumer(consumer_config)

    return None


if __name__ == '__main__':
    main()


