import argparse
import json
from datetime import datetime
from pathlib import Path

from dynreact.shortterm.agents.log import Log
import platform
import configparser
import os

from dynreact.shortterm.agents.equipment import Equipment
from dynreact.shortterm.agents.material import Material
from dynreact.shortterm.common import VAction, KeySearch
from dynreact.shortterm.shorttermtargets import ShortTermTargets


def log_base(verbose: int):

    if verbose > 0:
        print(f"Running log agent with {verbose=}")

    # Global configuration - assign the values to the global variables using the information above
    config = configparser.ConfigParser()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config.optionxform = str
    config.read(os.path.join(current_dir, "dynreact", "shortterm", "config.cnf"))

    short_term_config = ShortTermTargets(VB=verbose).model_copy(update=dict(config["DEFAULT"].items()))
    KeySearch.set_global(config_provider=short_term_config)

    left_path = KeySearch.search_for_value('LOG_FILE_PATH')
    topic_gen = KeySearch.search_for_value('TOPIC_GEN')
    topic_callback = KeySearch.search_for_value('TOPIC_CALLBACK')

    folder_path = Path(left_path)

    # Create log folder if not added
    if not folder_path.exists():
        folder_path.mkdir(parents=True)

    # Creation of the main log file
    now = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    log_file = f"{topic_gen}-{now}.log"
    if platform.system() == 'Windows':
        log_file = log_file.replace(":", "_")
    log_file = os.path.join(left_path, log_file)
    agent_gen = 'LOG:' + topic_gen

    main_log = Log(
        topic=topic_gen, agent=agent_gen, left_path=left_path, log_file=log_file
    )

    # Creates Callback topic!
    main_log.callback_on_topic_not_available(topic_callback)

    return main_log

def equipment_base(verbose: int):
    if verbose > 0:
        print(f"Running equipment agent with {verbose=}")

    # Global configuration - assign the values to the global variables using the information above
    config = configparser.ConfigParser()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config.optionxform = str
    config.read(os.path.join(current_dir, "dynreact", "shortterm", "config.cnf"))

    short_term_config = ShortTermTargets(VB=verbose).model_copy(update=dict(config["DEFAULT"].items()))
    KeySearch.set_global(config_provider=short_term_config)

    topic_gen = KeySearch.search_for_value('TOPIC_GEN')

    main_equipment = Equipment(
        topic=topic_gen, agent=f"EQUIPMENT:{topic_gen}", status=dict(),
        counterbid_wait=15
    )

    return main_equipment

def material_base(verbose: int):
    if verbose > 0:
        print(f"Running material agent with {verbose=}")

    # Global configuration - assign the values to the global variables using the information above
    config = configparser.ConfigParser()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config.optionxform = str
    config.read(os.path.join(current_dir, "dynreact", "shortterm", "config.cnf"))

    short_term_config = ShortTermTargets(VB=verbose).model_copy(update=dict(config["DEFAULT"].items()))
    KeySearch.set_global(config_provider=short_term_config)

    topic_gen = KeySearch.search_for_value('TOPIC_GEN')

    main_material = Material(
        topic=topic_gen, agent=f"MATERIAL:{topic_gen}", params=dict()
    )

    return  main_material



def main():
    print("Starting agent")

    parser = argparse.ArgumentParser(description="Select an agent to run.")

    subparsers = parser.add_subparsers(dest="agent", required=True, help="Choose an agent to run")

    # ------------------------
    # Instance Log Subparser
    parser_log = subparsers.add_parser("log", help="Run Log Agent")
    subparsers_log = parser_log.add_subparsers(dest="type", required=True, help="Which type of agent to run")

    # Log Agent - Base Mode
    parser_log_base = subparsers_log.add_parser("base", help="Run the base log agent")
    parser_log_base.add_argument("-v", "--verbose", default=0, nargs='?', action=VAction,
                    dest='verbose', help="Option for printing detailed information")

    # Log Agent - Replica Mode
    parser_log_replica = subparsers_log.add_parser("replica", help="Run the replica log agent")

    # Required string arguments
    parser_log_replica.add_argument("-t", "--topic", type=str, required=True, help="Topic name")
    parser_log_replica.add_argument("-a", "--agent-name", type=str, required=True, help="Agent name")
    parser_log_replica.add_argument("-k", "--kafka-ip", type=str, required=True, help="Kafka broker IP address")
    parser_log_replica.add_argument("-p", "--left-path", type=str, required=True, help="Path to the left file")
    parser_log_replica.add_argument("-l", "--log-file", type=str, required=True, help="Path to the log file")

    # Optional integer argument with default value
    parser_log_replica.add_argument("-v", "--verbose", default=0, nargs='?', action=VAction,
                                 dest='verbose', help="Option for printing detailed information")

    # ------------------------
    # Instance Equipment Subparser
    parser_equipment = subparsers.add_parser("equipment", help="Run Equipment Agent")
    subparsers_equipment = parser_equipment.add_subparsers(dest="type", required=True, help="Which type of agent to run")

    # Equipment Agent - Base Mode
    parser_equipment_base = subparsers_equipment.add_parser("base", help="Run the base equipment agent")
    parser_equipment_base.add_argument("-v", "--verbose", default=0, nargs='?', action=VAction,
                                 dest='verbose', help="Option for printing detailed information")


    # Equipment Agent - Replica Mode
    parser_equipment_replica = subparsers_equipment.add_parser("replica", help="Run the replica equipment agent")

    # Required string arguments
    parser_equipment_replica.add_argument("-t", "--topic", type=str, required=True, help="Topic name")
    parser_equipment_replica.add_argument("-a", "--agent-name", type=str, required=True, help="Agent name")
    parser_equipment_replica.add_argument("-s", "--status", type=str, required=True, help="Equipment Status")
    parser_equipment_replica.add_argument("-k", "--kafka-ip", type=str, required=True, help="Kafka broker IP address")
    parser_equipment_replica.add_argument("-cw", "--counter-wait", type=int, required=True, help="Amount of time to wait to counterbid")

    # Optional integer argument with default value
    parser_equipment_replica.add_argument("-v", "--verbose", default=0, nargs='?', action=VAction,
                                    dest='verbose', help="Option for printing detailed information")

    # ------------------------
    # Instance Material Subparser
    parser_material = subparsers.add_parser("material", help="Run Material Agent")
    subparsers_material = parser_material.add_subparsers(dest="type", required=True,
                                                           help="Which type of agent to run")

    # Material Agent - Base Mode
    parser_material_base = subparsers_material.add_parser("base", help="Run the base equipment agent")
    parser_material_base.add_argument("-v", "--verbose", default=0, nargs='?', action=VAction,
                                       dest='verbose', help="Option for printing detailed information")


    # Material Agent - Replica Mode
    parser_material_replica = subparsers_material.add_parser("replica", help="Run the replica equipment agent")

    # Required string arguments
    parser_material_replica.add_argument("-t", "--topic", type=str, required=True, help="Topic name")
    parser_material_replica.add_argument("-a", "--agent-name", type=str, required=True, help="Agent name")
    parser_material_replica.add_argument("-p", "--params", type=str, required=True, help="Materials parameters relevant to the configuration of the agent.")
    parser_material_replica.add_argument("-k", "--kafka-ip", type=str, required=True, help="Kafka broker IP address")

    # Optional integer argument with default value
    parser_material_replica.add_argument("-v", "--verbose", default=0, nargs='?', action=VAction,
                                          dest='verbose', help="Option for printing detailed information")

    # ------------------------

    args = parser.parse_args()

    if args.type not in ["base", "replica"]:
        raise ValueError(f"Value {args.type} is not supported.")

    if args.agent == "log":
        if args.type == "base":
            agent = log_base(verbose=args.verbose)
        elif args.type == "replica":

            KeySearch.set_global(config_provider=ShortTermTargets(
                VB=args.verbose,
                IP=args.kafka_ip,
            ))

            agent = Log(
                topic=args.topic,
                agent=args.agent_name,
                left_path=args.left_path,
                log_file=args.log_file,
                manager=False
            )

    elif args.agent == "equipment":
        if args.type == "base":
            agent = equipment_base(verbose=args.verbose)
        elif args.type == "replica":

            KeySearch.set_global(config_provider=ShortTermTargets(
                VB=args.verbose,
                IP=args.kafka_ip,
            ))

            agent = Equipment(
                topic=args.topic,
                agent=args.agent_name,
                counterbid_wait=args.counter_wait,
                status=json.loads(args.status),
                manager=False
            )

    elif args.agent == "material":
        if args.type == "base":
            agent = material_base(verbose=args.verbose)
        elif args.type == "replica":

            KeySearch.set_global(config_provider=ShortTermTargets(
                VB=args.verbose,
                IP=args.kafka_ip,
            ))

            agent = Material(
                topic=args.topic,
                agent=args.agent_name,
                params=json.loads(args.params),
                manager=False
            )
    else:
        raise ValueError("Unknown agent value")

    print("Running agent")
    # Run the topic
    agent.follow_topic()


if __name__ == "__main__":
    main()
