"""
equipment.py 
First Prototype of Kubernetes oriented solution for the EQUIPMENT agent

Version History:
- 1.0 (2024-03-06): Initial version developed by Rodrigo Castro Freibott.
- 1.1 (2024-11-28): Updates from JOM
- 1.2 (2024-12-14): Updates from JOM Cosmetics to name equipment instead of resource
"""

import time
from datetime import datetime, timedelta

from sphinx.ext.ifconfig import ifconfig

from dynreact.shortterm.common import sendmsgtopic, KeySearch
from dynreact.shortterm.common.data.data_functions import get_equipment_status
from dynreact.shortterm.common.data.load_url import DOCKER_REPLICA
from dynreact.shortterm.common.functions import calculate_production_cost, get_new_equipment_status
from dynreact.shortterm.agents.agent import Agent
from dynreact.shortterm.common.handler import DockerManager


class Equipment(Agent):
    """
    Class Equipment supporting the equipment agents.

    Arguments:
        topic     (str): Topic driving the relevant converstaion.
        agent     (str): Name of the agent creating the object.
        status   (dict): Status of the equipment
        operation_speed (float): Operation speed of the equipment in m/s.
        start_time (datetime): Start time of the auction for the equipment.
        current_order_length (float): The total length of the current assigned order in meters.

    """
    def __init__(self, topic: str, agent: str, status: dict, operation_speed: float = None, start_time: datetime = None, current_order_length: float = None, manager=True):

        super().__init__(topic=topic, agent=agent)
        """
        Constructor function for the Equipment Class

        :param str topic: Topic driving the relevant converstaion.
        :param str agent: Name of the agent creating the object.
        :param dict status: Status of the equipment.
        :param float operation_speed: Operation speed of the equipment in m/s.
        :param datetime start_time: Start time of the auction for the equipment.
        :param float current_order_length: The total length of the current assigned order in meters.
        :param str manager: Is this instance a base.
        """
        self.action_methods.update({
            'CREATE': self.handle_create_action, 'START': self.handle_start_action,
            'COUNTERBID': self.handle_counterbid_action, 'ASKCONFIRM': self.handle_askconfirm_action,
            'CONFIRM': self.handle_confirm_action, 'ASSIGNED': self.handle_assigned_action
        })
        
        if manager:
            self.handler = DockerManager(tag=f"equipment{DOCKER_REPLICA}")

        self.operation_speed = operation_speed
        self.round_number = 0
        self.status = status
        self.equipment = 0
        self.iter_post_bid = 0
        self.bids = []
        self.last_bid_time = None
        self.bid_to_confirm = dict()
        self.previous_price = None
        self.start_time = start_time if start_time is not None else datetime.now()
        self.current_order_length = current_order_length

        if self.verbose > 1:
            self.write_log(msg=f"Finished creating the agent {self.agent} with status {self.status}.",
                           identifier="5e0e90e2-12be-4048-b70f-73917bfe947b",
                           to_stdout=True)

    def move_to_next_round(self, material_params: dict):
        """
        Moves the equipment to the next round by updating its status according to the assigned material's parameters,
        updating its name with the next round number, and starting the round.

        :param dict material_params:
        """
        self.status = get_new_equipment_status(material_params=material_params, equipment_status=self.status, verbose=self.verbose)
        roundless_name = self.agent[:self.agent.rfind(":")]
        self.round_number += 1
        self.agent = roundless_name + f":{self.round_number}"
        if self.verbose > 1:
            self.write_log(f"Moved equipment {roundless_name} to round {self.round_number}. New status: {self.status}", "eb019471-fbda-43bb-907f-951e503f366e")

        self.iter_post_bid = 0
        self.bids = []
        self.last_bid_time = None
        self.bid_to_confirm = dict()

        if self.start_time is not None and self.current_order_length is not None and self.operation_speed > 0:
            self.start_time += timedelta(seconds=self.current_order_length / self.operation_speed)

        self.current_order_length = None
        full_msg = dict(
            source=self.agent, dest=self.agent, topic=self.topic, action='START',
            payload=dict(price=self.previous_price)
        )
        self.handle_start_action(full_msg)

    def handle_create_action(self, dctmsg: dict) -> str:
        """
        Handles the CREATE action. It clones the master EQUIPMENT for one auction.
        This instruction should only be given to the general EQUIPMENT.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """

        print("Got a create action in equipment")

        if self.handler:

            print("Inside the handler")

            topic = dctmsg['topic'] if 'topic' in dctmsg else self.topic
            payload = dctmsg['payload'] if 'payload' in dctmsg else dict()
            variables = payload['variables'] if 'variables' in payload else dict()

            KeySearch.assign_values(new_values=variables)

            user_start_date = payload['user_start_date'] if 'user_start_date' in payload else None

            equipment = payload['id'] if 'id' in payload else 0
            snapshot = payload['snapshot']
            operation_speed = payload['operation_speed'] if 'operation_speed' in payload else 0.0

            if user_start_date is not None:
                start_time = user_start_date
            elif 'start_time' in payload:
                start_time = payload['start_time']
            else:
                start_time = None

            agent = f"EQUIPMENT:{topic}:{equipment}:0"
            status = get_equipment_status(equipment_id=equipment, snapshot_time=snapshot)
            self.equipment = equipment

            init_kwargs = {
                "topic": topic,
                "agent": agent,
                "status": status,
                "operation_speed": float(operation_speed),
                "start_time": start_time,
                "variables": KeySearch.dump_model(),
            }

            self.handler.launch_container(name=f"{topic}_{equipment}", agent="equipment", mode="replica", params=init_kwargs, auto_remove=False)

            if self.verbose > 1:
                self.write_log(f"Creating equipment with configuration {init_kwargs}...", "f886d124-383b-497e-b2a1-841222a3e14d")

            return 'CONTINUE'
        else:
            self.write_log(f"Refuse to create equipment replica from another replica instance.", "fe2dbc33-7dcb-486a-af35-9e485674fff2")
            dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
            raise Exception(f"{dt} | ERROR: Replicas can't create new instances. Only managers can")

    def handle_start_action(self, dctmsg: dict) -> str:
        """
        Handles the START action. It starts the EQUIPMENT's auction by instructing the MATERIALs to start bidding.
        This instruction should only be given to the EQUIPMENT children of the auction.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """
        topic = dctmsg['topic']
        payload = dctmsg['payload']
        previous_price = None
        if 'price' in payload:
            previous_price = payload['price']

        sendmsgtopic(
            producer=self.producer,
            tsend=topic,
            topic=topic,
            source=self.agent,
            dest="MATERIAL:" + topic + ":.*",
            action="BID",
            payload=dict(id=self.agent, status=self.status, start_time=self.start_time, previous_price=previous_price),
            vb=self.verbose
        )
        if self.verbose > 2:
            self.write_log(f"Instructed all MATERIAL:{topic} to bid", "ce79433f-c90b-42bc-a6d8-83e50f25cb5b")

        # Reset bidding status
        self.iter_post_bid = 0
        self.last_bid_time = time.perf_counter()

        return 'CONTINUE'

    def handle_counterbid_action(self, dctmsg: dict) -> str:
        """
        Handles the COUNTERBID action. It gets the material ID, its parameters, and its bidding price
        to calculate the profit (price minus producation cost) for the equipment.
        This instruction should only be given to the EQUIPMENT children of the auction.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """
        payload = dctmsg['payload']
        material_params = payload['material_params']
        bidding_price = payload['price']

        prod_cost = calculate_production_cost(material_params=material_params, equipment_status=self.status, verbose=self.verbose)
        if prod_cost is None:
            if self.verbose > 1:
                self.write_log(
                    f"Rejected offer from material {payload['id']}. "
                    f"The transition function to this material returns null",
                    "46d5bed6-4e29-4d99-af76-93d008961dbd"
                )
            return 'CONTINUE'

        profit = bidding_price - prod_cost
        bid = dict(material=payload['id'], profit=profit, price=bidding_price)

        # Reset bidding status
        self.iter_post_bid = 0
        self.last_bid_time = time.perf_counter()

        # Add the bid to the list
        self.bids.append(bid)
        if self.verbose > 1:
            self.write_log(f"Added {bid} to the list of bids, {self.bids}", "245bb0ae-d579-4fef-a6a1-6625c97afbe1")

        return 'CONTINUE'

    def handle_askconfirm_action(self, dctmsg: dict) -> str:
        """
        Handles the ASKCONFIRM action. It asks the material for confirmation to settle the equipment-material assignment.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """

        topic = dctmsg['topic']
        material = dctmsg['payload']['id']
        sendmsgtopic(
            producer=self.producer,
            tsend=topic,
            topic=topic,
            source=self.agent,
            dest=material,
            action="ASKCONFIRM",
            payload=dict(id=self.agent, costs=self.status["planning"]),
            vb=self.verbose
        )
        return 'CONTINUE'

    def handle_confirm_action(self, dctmsg: dict) -> str:
        """
        Handles the CONFIRM action. It receives the confirmation from the material and moves to the next round.
        This instruction should only be given to the EQUIPMENT children of the auction,
        and only from the MATERIAL that the equipment previously asked for confirmation.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """
        payload = dctmsg['payload']
        material = payload['id']
        material_params = payload['material_params']
        self.current_order_length = payload['order_length']

        if material != self.bid_to_confirm['material']:
            error_msg = (
                f"The sender of the confirmation {material} does not match "
                f"the pending material {self.bid_to_confirm['material']}"
            )
            if self.verbose > 1:
                self.write_log(f"ERROR: {error_msg}", "8515a8be-49c3-4f18-8748-55126f15bb97")
            raise RuntimeError(error_msg)

        self.previous_price = self.bid_to_confirm['price']
        if self.verbose > 1:
            self.write_log(
                f"The equipment will be assigned to material {material} with bid {self.bid_to_confirm}. "
                f"Moving to the next round...",
                "0f906ad0-5526-45de-8a51-bc43a2a5c19d"
            )
        self.move_to_next_round(material_params=material_params)
        return 'CONTINUE'

    def handle_assigned_action(self, dctmsg: dict) -> str:
        """
        Handles the ASSIGNED action. It removes the material from the list of bids or,
        if the material matches the pending material, it no longer waits for its confirmation.
        This instruction should only be given to the EQUIPMENT children of the auction.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """
        payload = dctmsg['payload']
        material = payload['id']

        if self.bid_to_confirm and material == self.bid_to_confirm['material']:
            if self.verbose > 1:
                self.write_log(f"The material {material} has been assigned to another equipment.", "91efd53e-43a4-47bb-8da8-61aef92b8fe2")
            self.bid_to_confirm = dict()
            return 'CONTINUE'

        for index, bid in enumerate(self.bids):
            if bid['material'] == material:
                self.bids.pop(index)
                if self.verbose > 1:
                    self.write_log(f"Removed the assigned material, {material}, from the list of bids: {self.bids}", "a2646085-16ed-41cb-8b3e-745f5f2d7fae")
        return 'CONTINUE'

    def callback_before_message(self) -> str:
        """
        Checks the bidding and confirmation status
        :return: Status of the callback
        :rtype: str
        """
        if self.last_bid_time is None:
            return 'CONTINUE'

        # A bid has already happened; increment the number of iterations post-bid
        self.iter_post_bid += 1
        time_after_bid = time.perf_counter() - self.last_bid_time
        if (self.verbose > 1) and ((self.iter_post_bid - 1) % 15 == 0):
            self.write_log(
                f"Iteration {self.iter_post_bid - 1} after bid. Passed {time_after_bid:.2f}s after last bid",
                "1055b7fa-32a0-40b5-800a-33ba6bf1820f"
            )

        # Do not proceed if not enough time has passed since the last bid or
        # the equipment is waiting for a material to confirm
        if time_after_bid <  KeySearch.search_for_value("COUNTERBID_WAIT") or self.bid_to_confirm:
            return 'CONTINUE'

        # Kill this equipment child if there are no more materials to ask
        if len(self.bids) == 0:
            if self.verbose > 1:
                self.write_log(
                    f"No more bids to process. The equipment will not be assigned to any material. "
                    f"Killing the agent...",
                    "b6afb95b-91ac-4160-81c1-ac539ad2e472"
                )
            return 'END'

        # Ask the (next) best material for confirmation
        self.sort_bids()
        best_bid = self.bids.pop()
        if self.verbose > 1:
            self.write_log(f"Removed the best bid, {best_bid}, from the list of bids: {self.bids}", "1ea89f70-2e6c-4840-9bdb-bb89dfc7bff5")

        dctmsg = dict(topic=self.topic, payload=dict(id=best_bid['material']))
        self.process_message(action='ASKCONFIRM', dctmsg=dctmsg)

        self.bid_to_confirm = best_bid
        if self.verbose > 1:
            self.write_log(f"Equipment: Asked material {best_bid['material']} for confirmation.", "8d7d38bc-00cb-486c-8efa-0e46257bf1a2")

        return 'CONTINUE'

    def sort_bids(self):
        """
        Sorts the bids based on their profit in ascending order.
        """

        self.bids.sort(key=lambda item: item['profit'])
