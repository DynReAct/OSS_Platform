"""
log.py

First Prototype of Kubernetes oriented solution for the LOG service

Version History:
- 1.0 (2023-12-15): Initial version developed by Carlos-GCastellanos.
- 1.1 (2024-01-24): Updated by JOM.
- 1.2 (2024-03-04): Updated by Rodrigo Castro Freibott.
- 1.3 (2024-09-09): Updated by JOM.

"""

import time
import json

import multiprocessing
import logging

from confluent_kafka.admin import AdminClient, NewTopic
from datetime import datetime
from pathlib import Path

from common import sendmsgtopic, TOPIC_CALLBACK
from agents import Agent
from common.data.data_functions import end_auction
from common.data.load_url import DOCKER_REPLICA
from common.handler import DockerManager


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

    def __init__(self, topic: str, agent: str, kafka_ip: str, left_path: str, log_file: str, verbose: int = 1, manager=True):
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
            "ISAUCTIONACTIVE": self.handle_is_auction_started_action, "RECIEVEERROR": self.handle_receive_error_action
        })

        # To handle the start of the auction
        self.present_agents = set()
        self.auction_start = False
        self.total_num_agents = None

        if manager:
            self.handler = DockerManager(tag=f"log{DOCKER_REPLICA}")

        # To store the results of the auction so far
        self.results = dict()

        # Log file
        self.left_path = left_path
        self.log_file = log_file
        self.formatter = logging.Formatter('%(asctime)s;%(levelname)s;%(name)s;%(message)s')
        self.logger = self.setup_logger()
        if self.verbose > 1:
            self.write_log(f"Set up a logger in file {self.log_file}.", "a37fbe3a-0f5e-4979-aa18-47bfcd6cf8cd")

        # Some log messages must be given a higher verbosity level than other agents
        # to avoid cluttering the log files
        self.min_verbose = 3

        self.admin_client = AdminClient({"bootstrap.servers": str(self.kafka_ip)})
        self.topic_list = []
        self.write_log(f"Number of cpu : {multiprocessing.cpu_count()}", "f66036b8-cda8-4742-80c0-0880870d6216", action='SETUP')

        os_path = Path(self.log_file)
        if not os_path.is_file():
            self.write_log(f"ERROR: {self.log_file} does not exist", "b82f31ef-1750-4f33-8b2c-7bba4ed408de", action='CREATE')
        self.write_log(f"New log file created for topic {self.topic}.", "1a40e14a-845a-489a-8bea-5768c8940f1f", action='CREATE')

    def write_log(self, msg: str, identifier: str, action: str = 'WRITE', verbose: float = float("inf")):
        """
        Function writing a message to the log itself

        :param str msg: Message to be stored.
        :param str identifier: Identifier of the agent.
        :param str action: Action Name (WRITE, EXIT, etc.)
        """
        full_msg = dict(
            source=self.agent, dest=self.agent, action=action, payload=dict(msg=msg, identifier=identifier)
        )
        self.handle_write_action(full_msg, verbose)

    def callback_on_topic_not_available(self, topic: str = None):
        """
        Function executed when 'Subscribed topic not available'

        :param str topic: Name of the topic you want to create
        """

        topic = topic if topic else self.topic
        if self.verbose > 1:
            self.write_log(f"The subscribed topic {topic} is not available. Creating the topic...", "d2b894d4-b227-4495-9dc0-7877aaa67725")
        self.topic_list.append(NewTopic(
            topic,
            num_partitions=1,
            replication_factor=1,
            config={"retention.ms": str(30000)} # 30 sec
        ))
        self.admin_client.create_topics(self.topic_list)
        if self.verbose > 1:
            self.write_log(f"Created topic {self.topic}.", "762baef6-e85d-4a35-83d3-6298b6970b8c")
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
                    f"Results so far: {self.results}",
                    "290b91bf-8d1d-420a-b265-1d903df32512"
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

            try:
                self.logger.info(
                    f"|MSG|{full_msg['source']}|{full_msg['dest']}|{full_msg['action']}|{full_msg['payload']['identifier'][0:8]}|{full_msg['payload']['msg']}"
                )
            except:
                print(full_msg)

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

    def handle_receive_error_action(self, dctmsg: dict) -> str:
        """
        Handles the ERROR action for any agent.

        :param dict dctmsg: Message dictionary

        :returns: Status of the handling
        :rtype:  str
        """

        self.write_log(f"Killing auction early, fatal error in one of the agents {dctmsg['source']}", "f8987e40-e3d3-4045-9e7d-f3b9c39b9e00")

        self.results = {}

        # Force auction to crash due to error
        end_auction(topic=self.topic, producer=self.producer, verbose=self.verbose)

        return 'CONTINUE'

    def handle_create_action(self, dctmsg: dict) -> str:
        """
        Handles the CREATE action.

        :param dict dctmsg: Message dictionary

        :returns: Status of the handling
        :rtype:  str
        """

        if self.handler:
            topic = dctmsg['topic']
            agent = f"LOG:{topic}"
            log_file = f"{self.left_path}{topic}.log"

            init_kwargs = {
                "topic": topic, 
                "agent-name": agent,
                "kafka-ip": self.kafka_ip,
                "verbose": self.verbose,
                "left-path": self.left_path,
                "log-file": log_file
            }

            self.handler.launch_container(name=topic, agent="log", mode="replica", params=init_kwargs)

            if self.verbose > 1:
                self.write_log(f"Creating log with configuration {init_kwargs}...", "be68d495-4b5b-4a06-b5bf-eff1151d7c6b")

            return 'CONTINUE'
        else:
            self.write_log(f"Refuse to create log replica from another replica instance.", "99848564-684c-4eef-b3fa-efce3a667d25")
            raise Exception("Replicas can't create new instances. Only managers can")

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
            self.write_log("Instructed all agents to PING", "f188b141-ca68-468e-914b-e3b42cb76e21")
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
                    f"Progress: {len(self.present_agents)} / {self.total_num_agents}",
                    "87a353b2-de86-4c4b-bc6b-1f25768094a2"
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

        self.write_log(f"Checking if auction has already started...", "ce438bc1-37ee-4e87-a5d4-7b17b10acbf7")

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
                self.write_log(f"Answered {sender} with the current status of the auction.", "d7f95814-1932-4d89-ace6-618f50a725bd")

        else:
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
            self.write_log(f"The auction has started!", "f9ea052e-b0e9-43b0-9368-acf295f28e56")
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
            self.write_log(f"Answered {sender} with the current results of the auction: {self.results}", "b49a876b-8bf2-4677-8142-b32f8b2e5df5")
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
                    f"Starting the auction...",
                    "6a7072f6-2f3c-49e7-a24c-ae4de8a5239a"
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