"""
log.py

First Prototype of Kubernetes oriented solution for the LOG service

Version History:
- 1.0 (2023-12-15): Initial version developed by Carlos-GCastellanos.
- 1.1 (2024-01-24): Updated by JOM.
- 1.2 (2024-03-04): Updated by Rodrigo Castro Freibott.
- 1.3 (2024-09-09): Updated by JOM.

"""

import os
import time
import json
import platform
import configparser
import multiprocessing
import datetime
import logging
import argparse
from confluent_kafka.admin import AdminClient, NewTopic
from datetime import datetime
from multiprocessing import Pool
from pathlib import Path
from common import VAction, TOPIC_GEN, sendmsgtopic, TOPIC_CALLBACK
from agent import Agent


class Log(Agent):
    """
        Class holding the methods relevant for the operation of the Log agent,
        which is in charge for storing all the messages exchanged between the
        different agents through Kafka brokering system.

    Attributes:
        topic     (str): Topic driving the relevant converstaion.
        agent     (str): Name of the agent creating the object.
        kafka_ip  (str): IP address and TCP port of the broker.
        left_path (str): Path to place the log file.
        log_file  (str): Name of the log file.
        verbose   (int): Level of details being saved.

    .. _Google Python Style Guide:
       https://google.github.io/styleguide/pyguide.html
    """

    def __init__(self, topic: str, agent: str, kafka_ip: str, left_path: str, log_file: str, verbose: int = 1):
        super().__init__(topic=topic, agent=agent, kafka_ip=kafka_ip, verbose=verbose)
        """
           Constructor function for the Log Class

        :param str topic: Topic driving the relevant converstaion.
        :param str agent: Name of the agent creating the object.
        :param str kafka_ip: IP address and TCP port of the broker.
        :param str left_path: Path to place the log file.
        :param str log_file: Name of the log file.
        :param int verbose: Level of details being saved.
        """
        self.action_methods.update({
            'CREATE': self.handle_create_action, 'CHECK': self.handle_check_action, 'WRITE': self.handle_write_action,
            'PINGANSWER': self.handle_pinganswer_action, "ASKRESULTS": self.handle_askresults_action,
            "ISAUCTIONACTIVE": self.handle_is_auction_started_action
        })

        # To handle the start of the auction
        self.present_agents = set()
        self.auction_start = False
        self.total_num_agents = None

        # To store the results of the auction so far
        self.results = dict()

        # Log file
        self.left_path = left_path
        self.log_file = log_file
        self.formatter = logging.Formatter('%(asctime)s;%(levelname)s;%(name)s;%(message)s')
        self.logger = self.setup_logger()
        if self.verbose > 1:
            self.write_log(f"Set up a logger in file {self.log_file}.")

        # Some log messages must be given a higher verbosity level than other agents
        # to avoid cluttering the log files
        self.min_verbose = 3

        self.admin_client = AdminClient({"bootstrap.servers": str(self.kafka_ip)})
        self.topic_list = []
        self.write_log(f"Number of cpu : {multiprocessing.cpu_count()}", action='SETUP')

        os_path = Path(self.log_file)
        if not os_path.is_file():
            self.write_log(f"ERROR: {self.log_file} does not exist", action='CREATE')
        self.write_log(f"New log file created for topic {self.topic}.", action='CREATE')

    def write_log(self, msg: str, action: str = 'WRITE', verbose: float = float("inf")):
        """
        Function writing a message to the log itself

        :param str msg: Message to be stored.
        :param str action: Action Name (WRITE, EXIT, etc.)
        """
        full_msg = dict(
            source=self.agent, dest=self.agent, action=action, payload=dict(msg=msg)
        )
        self.handle_write_action(full_msg, verbose)

    def callback_on_topic_not_available(self, topic: str = None):
        """
        Function executed when 'Subscribed topic not available'

        :param str topic: Name of the topic you want to create
        """

        topic = topic if topic else self.topic
        if self.verbose > 1:
            self.write_log(f"The subscribed topic {topic} is not available. Creating the topic...")
        self.topic_list.append(NewTopic(topic, 1, 1))
        self.admin_client.create_topics(self.topic_list)
        if self.verbose > 1:
            self.write_log(f"Created topic {self.topic}.")
        time.sleep(2)

    def callback_on_not_match(self, dctmsg: dict):
        """
        When the LOG is not the destination, write the message in the log file and record the results.
        This allows the LOG to record all the messages exchanged within the topic.

        :param dict dctmsg: Dictionary supporting the message exchange
        """
        # Write the message in the log file
        full_msg = dict(
            source=dctmsg['source'], dest=dctmsg['dest'], action=dctmsg['action'],
            payload=dict(msg='[Topic] ' + str(self.topic) + '|' + str(dctmsg) + '.')
        )
        self.handle_write_action(full_msg)

        # Record the results
        if dctmsg['action'] == "CONFIRM":
            material_name = dctmsg['source'].split(':')[-1]  # MATERIAL:DynReact-UE9L5LJASTQ1:1003937408 -> 1003937408
            equipment_name = dctmsg['dest'].split(':')[-2]  # EQUIPMENT:DynReact-UE9L5LJASTQ1:14:0 -> 14
            round_number = dctmsg['dest'].split(':')[-1]  # EQUIPMENT:DynReact-UE9L5LJASTQ1:14:0 -> 0
            stdat = dctmsg['payload']['material_params']['order']
            stdat.pop('material', None)
            stdat['round'] = round_number
            stdat['mat'] = equipment_name

            if self.verbose > 1:
                self.write_log(
                    f"Recorded the assignment of material {material_name} to equipment {equipment_name}. "
                    f"Results so far: {self.results}"
                )

            if equipment_name not in self.results:
                # self.results[equipment_name] = [material_name]
                self.results[equipment_name] = [stdat]
            else:
                # self.results[equipment_name].append(material_name)
                self.results[equipment_name].append(stdat)

    def setup_logger(self) -> logging.Logger:
        """
        Set up a Logger object

        :returns: Logger object
        :rtype:  Logger object
        """

        handler = logging.FileHandler(self.log_file, mode="a")
        handler.setFormatter(self.formatter)

        logger = logging.getLogger(self.topic)
        logger.setLevel(logging.INFO)
        logger.addHandler(handler)

        return logger

    def handle_write_action(self, full_msg: dict, verbose: float = float("inf")) -> str:
        """
        Handles the WRITE action.

        :param dict full_msg: Message dictionary
        :param dict verbose: Show print console output
        """
        if 'payload' not in full_msg.keys():
            self.logger.info("HANDLE_WRITE_ERROR: payload is not a key for message")
        else:
            if isinstance(full_msg['payload'], str):
                full_msg['payload'] = json.loads(full_msg['payload'])

            self.logger.info(
                f"|MSG|{full_msg['source']}|{full_msg['dest']}|{full_msg['action']}|{full_msg['payload']['msg']}"
            )
            if min(verbose, self.verbose) > float(1):
                ctme = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
                print(ctme + " => " + json.dumps(full_msg))

        return 'CONTINUE'

    def handle_exit_action(self, dctmsg: dict) -> str:
        """
        Handles the EXIT action.

        :param dict dctmsg: Message dictionary

        :returns: Status of the handling
        :rtype:  str
        """
        full_msg = dict(
            source=dctmsg['source'], dest=dctmsg['dest'], action='EXIT',
            payload=dict(msg=f"Requested Exit")
        )
        self.handle_write_action(full_msg)
        return 'END'

    def handle_create_action(self, dctmsg: dict) -> str:
        """
        Handles the CREATE action.

        :param dict dctmsg: Message dictionary

        :returns: Status of the handling
        :rtype:  str
        """
        topic = dctmsg['topic']
        agent = f"LOG:{topic}"
        log_file = f"{self.left_path}{topic}.log"
        init_kwargs = dict(
            topic=topic, agent=agent, kafka_ip=self.kafka_ip, verbose=self.verbose,
            left_path=self.left_path, log_file=log_file
        )
        if self.verbose > 1:
            self.write_log(f"Creating log with configuration {init_kwargs}...")

        pool = Pool(processes=2)
        pool.apply_async(create_log, (init_kwargs,))
        pool.close()
        return 'CONTINUE'

    def handle_check_action(self, dctmsg: dict) -> str:
        """
        Sets the total number of agents and probes all agents to ping to the LOG agent
        to check their existence before the auction starts.
        It has been observed that the agents receive the instruction to ping
        even when they have been created after this message was produced,
        so it is not necessary to call this method more than once.

        :param dict dctmsg: Dictionary object holding the message

        :returns: Status of the handling
        :rtype:  str
        """
        topic = dctmsg['topic']
        payload = dctmsg['payload']
        self.total_num_agents = payload['num_agents']

        sendmsgtopic(
            producer=self.producer,
            tsend=topic,
            topic=topic,
            source=self.agent,
            dest=".*",
            action="PING",
            vb=self.verbose
        )

        if self.verbose > 1:
            self.write_log("Instructed all agents to PING")
        return 'CONTINUE'

    def handle_pinganswer_action(self, dctmsg: dict) -> str:
        """
        Adds the agent to the set of present agents.

        :param dict dctmsg: Dictionary for the message

        :returns: Status of the handling
        :rtype:  str
        """
        agent = dctmsg['source']
        if agent not in self.present_agents:
            self.present_agents.add(agent)
            if self.verbose > 1:
                self.write_log(
                    f"Added agent {agent} to the list of present agents. "
                    f"Progress: {len(self.present_agents)} / {self.total_num_agents}"
                )
        return 'CONTINUE'

    def handle_is_auction_started_action(self, dctmsg: dict) -> str:
        """
        Check if the auction has started

        :param dict dctmsg: Dictionary for the message

        :returns: Status of the handling
        :rtype:  str
        """

        topic = dctmsg['topic']
        sender = dctmsg['source']

        self.write_log(f"Checking if auction has already started...")

        start_conditions = [self.total_num_agents is not None, self.auction_start]

        if all(start_conditions) and len(self.present_agents) == self.total_num_agents:

            sendmsgtopic(
                producer=self.producer,
                tsend=TOPIC_CALLBACK,
                topic=TOPIC_CALLBACK,
                source=self.agent,
                dest=sender,
                action="AUCTIONSTARTED",
                payload={
                    "present_agents": len(self.present_agents),
                    "total_num_agents": self.total_num_agents or 0,
                    "is_auction_started": True
                },
                vb=self.verbose
            )

            if self.verbose > 1:
                self.write_log(f"Answered {sender} with the current status of the auction.")

        else:
            sendmsgtopic(
                producer=self.producer,
                tsend=topic,
                topic=topic,
                source=self.agent,
                dest=sender,
                action="AUCTIONSTARTED",
                payload={
                    "present_agents": len(self.present_agents),
                    "total_num_agents": self.total_num_agents or 0,
                    "is_auction_started": False
                },
                vb=self.verbose
            )

        return 'CONTINUE'

    def handle_start_action(self, dctmsg: dict) -> str:
        """
        Starts an auction by instructing all EQUIPMENT children to start communicating with the MATERIALs

        :param dict dctmsg: Dictionary for the message

        :returns: Status of the handling
        :rtype:  str
        """
        topic = dctmsg['topic']
        sendmsgtopic(
            producer=self.producer,
            tsend=topic,
            topic=topic,
            source=self.agent,
            dest="EQUIPMENT:" + topic + ":.*",
            action="START",
            vb=self.verbose
        )
        self.auction_start = True
        if self.verbose > 1:
            self.write_log(f"The auction has started!")
        return 'CONTINUE'

    def handle_askresults_action(self, dctmsg: dict) -> str:
        """
        Answers the sender of the message with the results of the auction

        :param dict dctmsg: Dictionary for the message

        :returns: Status of the handling
        :rtype:  str
        """
        topic = dctmsg['topic']
        sender = dctmsg['source']
        sendmsgtopic(
            producer=self.producer,
            tsend=TOPIC_CALLBACK,
            topic=TOPIC_CALLBACK,
            source=self.agent,
            dest=sender,
            action="RESULTS",
            payload=self.results,
            vb=self.verbose
        )
        if self.verbose > 1:
            self.write_log(f"Answered {sender} with the current results of the auction: {self.results}")
        return 'CONTINUE'

    def callback_before_message(self) -> str:
        """
        Starts the auction when the number of present agents reaches the desired total number of agents

        :returns: Status of the handling
        :rtype:  str
        """
        start_conditions = [self.total_num_agents is not None, not self.auction_start]
        if all(start_conditions) and len(self.present_agents) == self.total_num_agents:
            if self.verbose > 1:
                self.write_log(
                    f"The desired number of agents, {self.total_num_agents}, have confirmed their presence. "
                    f"Starting the auction..."
                )
            full_msg = dict(
                source=self.agent, dest=self.agent, topic=self.topic, action='START', payload=dict()
            )
            self.handle_start_action(full_msg)
        # Updated by JOM 20240805 (else to inform unconformities).
        else:
            foundag = len(self.present_agents)
            verbosity = 1 if foundag == 0 else self.verbose
            # self.write_log(msg=f"Declared number of agents:{self.total_num_agents}. Responding number:{foundag}",
            #                verbose=verbosity)
        return 'CONTINUE'


def create_log(init_kwargs: dict):
    """
    Helper function to create Log instances asynchronously with Python's multiprocessing.
    The reason for this function is that multiprocessing can handle functions but not methods.
    Source: https://stackoverflow.com/questions/41000818/can-i-pass-a-method-to-apply-async-or-map-in-python-multiprocessing

    :param dict init_kwargs: Dictionary to init the Syslog recording system
    """
    resource = Log(**init_kwargs)
    resource.follow_topic()


def main():
    """
    Create method to setup the general LOG and make it follow the general topic

    :param str base: Path for the configuration file. Passed in the command line
    :param int verbose: Option to print information. Passed in the command line
    """
    # Extract the 'verbose' and 'base' command line arguments
    # The value in 'base' indicates the path to the configuration file
    ap = argparse.ArgumentParser()
    ap.add_argument("-b", "--base", type=str, dest="base", required=True,
                    help="Path from current place to find config.cnf file")
    ap.add_argument("-v", "--verbose", nargs='?', action=VAction,
                    dest='verbose', help="Option for printing detailed information")
    args = vars(ap.parse_args())

    verbose = 0
    if args["verbose"]:
        verbose = args["verbose"]
    base = "."
    if args["base"]:
        base = args["base"].strip()
    if verbose > 0:
        print(f"Running program with {verbose=} and {base=}.")

    # Global configuration - assign the values to the global variables using the information above
    config = configparser.ConfigParser()
    config.read(base + '/config.cnf')
    kafka_ip = config['DEFAULT']['IP']
    left_path = config['DEFAULT']['LogFilePath']

    # Creation of the main log file
    now = datetime.now().strftime("%Y-%m-%d_%H:%M:%S")
    log_file = f"{TOPIC_GEN}-{now}.log"
    if platform.system() == 'Windows':
        log_file = log_file.replace(":", "_")
    log_file = os.path.join(left_path, log_file)
    agent_gen = 'LOG:' + TOPIC_GEN

    main_log = Log(
        topic=TOPIC_GEN, agent=agent_gen, kafka_ip=kafka_ip, left_path=left_path, log_file=log_file, verbose=verbose
    )

    # Creates Callback topic!
    main_log.callback_on_topic_not_available(TOPIC_CALLBACK)

    main_log.follow_topic()


if __name__ == '__main__':
    main()
