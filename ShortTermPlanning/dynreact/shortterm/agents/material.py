"""
material.py

First Prototype of Kubernetes oriented solution for the MATERIAL agent

Version History:
- 1.0 (2024-03-09): Initial version developed by Rodrigo Castro Freibott.
"""

from dynreact.shortterm.common import sendmsgtopic
from dynreact.shortterm.common.data.load_url import DOCKER_REPLICA
from dynreact.shortterm.common.functions import calculate_bidding_price
from dynreact.shortterm.agents.agent import Agent
from dynreact.shortterm.common.handler import DockerManager


class Material(Agent):
    """
    Class Material supporting the material agents.

    Arguments:
        topic     (str): Topic driving the relevant converstaion.
        agent     (str): Name of the agent creating the object.
        params   (dict): parameters relevant to the configuration of the agent.
        kafka_ip  (str): IP address and TCP port of the broker.
        verbose   (int): Level of details being saved.

         

    """
    def __init__(self, topic: str, agent: str, params: dict, kafka_ip: str, verbose: int = 1, manager=True):

        super().__init__(topic=topic, agent=agent, kafka_ip=kafka_ip, verbose=verbose)
        """
           Constructor function for the Log Class

        :param str topic: Topic driving the relevant converstaion.
        :param str agent: Name of the agent creating the object.
        :param dict params: Parameters relevant to the configuration of the agent.
        :param str kafka_ip: IP address and TCP port of the broker.
        :param int verbose: Level of details being saved.
        """

        self.action_methods.update({
            'CREATE': self.handle_create_action,
            'BID': self.handle_bid_action,
            'ASKCONFIRM': self.handle_askconfirm_action
        })

        if manager:
            self.handler = DockerManager(tag=f"material{DOCKER_REPLICA}")

        self.assigned_equipment = ""
        self.params = params
        if self.verbose > 1:
            self.write_log(msg=f"Finished creating the agent {self.agent} with parameters {self.params}.",
                           identifier="ddea8374-6149-41e1-b86f-4cc147580d13",
                           to_stdout=True)

    def handle_create_action(self, dctmsg: dict) -> str:
        """
        Handles the CREATE action. It clones the master MATERIAL for one auction.
        This instruction should only be given to the general MATERIAL.

        :param dict dctmsg: Message dictionary
        """

        if self.handler:
        
            topic = dctmsg['topic']
            payload = dctmsg['payload']
            material = payload['id']
            agent = f"MATERIAL:{topic}:{material}"
            params = payload['params']
    
            init_kwargs = {
                "topic": topic, 
                "agent": agent,
                "params": params,
                "kafka-ip": self.kafka_ip,
                "verbose": self.verbose
            }

            self.handler.launch_container(name=f"{topic}_{material}", agent="material", mode="replica", params=init_kwargs)

            if self.verbose > 1:
                self.write_log(f"Creating material with configuration {init_kwargs}...", "ffac4444-ec23-4f00-af6a-f4300e3af7a7")

            return 'CONTINUE'

        else:
            self.write_log(f"Refuse to create material replica from another replica instance.", "c891fe14-041f-48b7-8de9-aa0d201e7083")
            raise Exception("Replicas can't create new instances. Only managers can")

    def handle_bid_action(self, dctmsg: dict) -> str:
        """
        Handles the BID action. If the MATERIAL finds the EQUIPMENT's offer interesting,
        it gives the EQUIPMENT a message with its bidding price.

        :param dict dctmsg: Message dictionary
        :return: Status of the processing
        :rtype: str
        """
        topic = dctmsg['topic']
        payload = dctmsg['payload']
        equipment_id = payload['id']
        equipment_status = payload['status']
        previous_price = payload['previous_price']

        # Calculate the bidding price based on EQUIPMENT status and MATERIAL parameters
        bidding_price = calculate_bidding_price(
            material_params=self.params, equipment_status=equipment_status, previous_price=previous_price
        )
        if bidding_price is not None:
            # --- START: New log message informing about the structure of the payload ---
            if self.verbose > 3:
                self.write_log(
                    msg=f"Sending COUNTERBID to {equipment_id} with material_params payload: {self.params}",
                    identifier="3a0c1b9f-4f2a-4a8e-8b1e-7f6d5c6b7a8d",
                    to_stdout=True # Also print to docker container stdout
                )
            # --- END: New log message ---            
            sendmsgtopic(
                producer=self.producer,
                tsend=topic,
                topic=topic,
                source=self.agent,
                dest=equipment_id,
                action="COUNTERBID",
                payload=dict(id=self.agent, material_params=self.params, price=bidding_price),
                vb=self.verbose
            )
            if self.verbose > 2:
                self.write_log(f"Instructed {equipment_id} to counterbid", "1df48bc3-a57f-40fa-a2db-effca1d2d40b")
        else:
            if self.verbose > 1:
                self.write_log(
                    f"Rejected offer from {equipment_id}. "
                    f"This equipment is not among the allowed equipments for the material",
                    "8c068331-38bf-4b1f-acd4-f9659c8c7be7"
                )

        return 'CONTINUE'

    def handle_askconfirm_action(self, dctmsg: dict) -> str:
        """
        Handles the ASKCONFIRM action.
        It answers, the equipment to indicate that the material can be assigned to the equipment
        and has not already been assigned to another equipment.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """
        topic = dctmsg['topic']
        equipment = dctmsg['payload']['id']
        sendmsgtopic(
            producer=self.producer,
            tsend=topic,
            topic=topic,
            source=self.agent,
            dest=equipment,
            action="CONFIRM",
            payload=dict(id=self.agent, material_params=self.params),
            vb=self.verbose
        )

        self.assigned_equipment = equipment
        if self.verbose > 1:
            self.write_log(
                f"Assigned material to equipment {self.assigned_equipment}. Sending ASSIGNED message...",
                "8f4703ed-8a8c-4070-8ffe-3577a268d11f"
            )
        full_msg = dict(
            source=self.agent, dest=self.agent, topic=self.topic, action='SENDASSIGNED', payload=dict()
        )
        self.handle_sendassigned_action(full_msg)

        if self.verbose > 1:
            self.write_log(
                f"Assigned material to equipment {self.assigned_equipment} and sent ASSIGNED message. "
                f"Killing the agent...",
                "e1fa8827-d3cc-40cf-a98a-ba899439c925"
            )
        return 'END'

    def handle_sendassigned_action(self, dctmsg: dict) -> str:
        """
        Handles the SENDASSIGNED action.
        It informs all equipments (except the assigned equipment)
        that this material has already been ASSIGNED to another equipment.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """
        topic = dctmsg['topic']
        sendmsgtopic(
            producer=self.producer,
            tsend=topic,
            topic=topic,
            source=self.agent,
            dest=f"^(?!{self.assigned_equipment})(EQUIPMENT:{topic}:.*)$",
            action="ASSIGNED",
            payload=dict(id=self.agent),
            vb=self.verbose
        )
        if self.verbose > 1:
            self.write_log(f"Informed all equipments (except {self.assigned_equipment}) that {self.agent} is ASSIGNED.", "bc8c9681-f990-47e5-90ff-5b0b782ff1ac")
        return 'CONTINUE'