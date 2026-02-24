"""
material.py

First Prototype of Kubernetes oriented solution for the MATERIAL agent

Version History:
- 1.0 (2024-03-09): Initial version developed by Rodrigo Castro Freibott.
"""

from datetime import datetime
from dynreact.shortterm.common import sendmsgtopic, KeySearch
from dynreact.shortterm.common.data.load_url import DOCKER_REPLICA
from dynreact.shortterm.agents.agent import Agent
from dynreact.shortterm.common.handler import DockerManager
from datetime import datetime, timedelta
import random


class Material(Agent):
    """
    Class Material supporting the material agents.

    Arguments:
        topic     (str): Topic driving the relevant converstaion.
        agent     (str): Name of the agent creating the object.
        params   (dict): parameters relevant to the configuration of the agent.
        transport_times (dict): Dictionary with the transport times for each equipment expressed in seconds.
        coil_lengths (list): List with the coil lengths for each equipment expressed in meters.
    """
    def __init__(self, topic: str, agent: str, params: dict, transport_times: dict[str, int] = None, coil_lengths: list[float] = None, manager=True):

        super().__init__(topic=topic, agent=agent)
        """
           Constructor function for the Log Class

        :param str topic: Topic driving the relevant converstaion.
        :param str agent: Name of the agent creating the object.
        :param dict params: Parameters relevant to the configuration of the agent.
        :param dict transport_times: Dictionary with the transport times for each equipment expressed in seconds.
        :param list coil_lengths: List with the coil lengths for each equipment expressed in meters.
        :param str manager: Is this instance a base.
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
        self.transport_times = transport_times if transport_times is not None else {}
        self.coil_lengths = coil_lengths if coil_lengths is not None else [0.0]
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
        
            topic = dctmsg.get('topic', "")
            payload = dctmsg.get('payload', {})
            material = payload.get('id', "0")
            agent = f"MATERIAL:{topic}:{material}"
            params = payload.get('params', {})
            transport_times = payload.get('transport_times', {})
            coil_lengths = payload.get('coil_lengths', [0.0])
            variables = payload.get('variables', {})

            KeySearch.assign_values(new_values=variables)
    
            init_kwargs = {
                "topic": topic, 
                "agent": agent,
                "params": params,
                "transport_times": transport_times,
                "coil_lengths": coil_lengths,
                "variables": KeySearch.dump_model()
            }

            self.handler.launch_container(name=f"{topic}_{material}", agent="material", mode="replica", params=init_kwargs, auto_remove=True)

            if self.verbose > 1:
                self.write_log(f"Creating material with configuration {init_kwargs}...", "ffac4444-ec23-4f00-af6a-f4300e3af7a7")

            return 'CONTINUE'

        else:
            self.write_log(f"Refuse to create material replica from another replica instance.", "c891fe14-041f-48b7-8de9-aa0d201e7083")
            dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
            raise Exception(f"{dt} | ERROR: Replicas can't create new instances. Only managers can")

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
        previous_price = payload.get('previous_price')
        auction_start_time = payload.get('start_time')
        auction_start_time = datetime.strptime(auction_start_time, '%Y-%m-%dT%H:%M:%SZ')

        time_to_equipment = timedelta(seconds=int(self.transport_times.get(equipment_id, 0)))
        material_start_time = datetime.now() + time_to_equipment

        if material_start_time <= auction_start_time:
            # Calculate the bidding price based on EQUIPMENT status and MATERIAL parameters
            bidding_price = self.calculate_bidding_price(
                material_params=self.params, equipment_status=equipment_status, previous_price=previous_price, auction_start_time=auction_start_time
            )
            if bidding_price is not None:
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
        else:
            if self.verbose > 1:
                self.write_log(
                    f"Material can't reach the equipment {equipment_id} in time."
                    f"Start of the auction: {auction_start_time.strftime('%H:%M:%S %d/%m/%Y')}"
                    f"Material time of arrival: {material_start_time.strftime('%H:%M:%S %d/%m/%Y')}",
                    "4a2e5658-3f55-4f2d-9b47-7737cc4f9517"
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
        costs = dctmsg['payload']['costs']
        sendmsgtopic(
            producer=self.producer,
            tsend=topic,
            topic=topic,
            source=self.agent,
            dest=equipment,
            action="CONFIRM",
            payload=dict(id=self.agent, material_params=self.params, order_length=self.calculate_order_length(), costs=costs),
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

    def calculate_order_length(self) -> float:
        """
        Calculates the total length of the order by summing up all the individual coil lengths.
        """
        return sum(self.coil_lengths)

    def calculate_bidding_price(self, material_params: dict, equipment_status: dict,
                                previous_price: float | None, auction_start_time: datetime) -> float | None:
        """
        Calculates the bidding price that the MATERIAL would pay to be processed in the EQUIPMENT with the given status.
        Returns None if the EQUIPMENT's status is not compatible with the MATERIAL's parameters.
        Otherwise, returns the bidding price as a float, which depends on the MATERIAL's parameters and the previous
        bidding price (but not on the EQUIPMENT's status).

        :param dict equipment_status: Status of the EQUIPMENT
        :param dict material_params: Parameters of the MATERIAL
        :param float previous_price: Bidding price in the EQUIPMENT's previous round

        :return: Bidding price, or None if the MATERIAL cannot be processed by that equipment
        :rtype: float
        """
        # Reject offer is equipment is not among the allowed equipments of the material
        # JOM 2025
        if equipment_status['targets']['equipment'] not in material_params['order']['allowed_equipment']:
            return None

        # For now, the bidding price is greater when the delivery date is sooner. If due_date is not present simulate a value
        if material_params['order'].get("due_date"):
            delivery_date = material_params['order']['due_date']
            delivery_date = datetime.strptime(delivery_date, '%Y-%m-%dT%H:%M:%SZ')
        else:
            # Calculate today's date
            today = datetime.now()
            # Calculate the date 10 days ago
            ten_days_ago = today - timedelta(days=10)
            # Generate a random date between today and 10 days ago
            delivery_date = ten_days_ago + timedelta(days=random.randint(0, 10))

        bidding_price = 150 / (delivery_date - datetime(2020, 1, 1)).days + 150 / (auction_start_time - datetime(2020, 1, 1)).seconds

        # For now, the bidding price is simply increased by the previous bidding price
        if previous_price is not None:
            bidding_price += previous_price

        return bidding_price
