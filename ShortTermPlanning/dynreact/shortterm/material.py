"""
material.py

First Prototype of Kubernetes oriented solution for the MATERIAL agent

Version History:
- 1.0 (2024-03-09): Initial version developed by Rodrigo Castro Freibott.
"""

import argparse
import configparser
from multiprocessing import Pool
from common import VAction, TOPIC_GEN, sendmsgtopic
from data.data_functions import get_material_params
from functions import calculate_bidding_price
from agent import Agent


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
    def __init__(self, topic: str, agent: str, params: dict, kafka_ip: str, verbose: int = 1):

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
            'CREATE': self.handle_create_action, 'BID': self.handle_bid_action,
            'ASKCONFIRM': self.handle_askconfirm_action
        })

        self.assigned_resource = ""
        self.params = params
        if self.verbose > 1:
            self.write_log(f"Finished creating the agent {self.agent} with parameters {self.params}.")

    def handle_create_action(self, dctmsg: dict) -> str:
        """
        Handles the CREATE action. It clones the master MATERIAL for one auction.
        This instruction should only be given to the general MATERIAL.

        :param dict dctmsg: Message dictionary
        """
        topic = dctmsg['topic']
        payload = dctmsg['payload']
        material = payload['id']
        agent = f"MATERIAL:{topic}:{material}"
        params = get_material_params(material)

        init_kwargs = dict(
            topic=topic, agent=agent, params=params, kafka_ip=self.kafka_ip, verbose=self.verbose
        )
        if self.verbose > 1:
            self.write_log(f"Creating material with configuration {init_kwargs}...")

        pool = Pool(processes=2)
        pool.apply_async(create_material, (init_kwargs,))
        pool.close()

        return 'CONTINUE'

    def handle_bid_action(self, dctmsg: dict) -> str:
        """
        Handles the BID action. If the MATERIAL finds the RESOURCE's offer interesting,
        it gives the RESOURCE a message with its bidding price.

        :param dict dctmsg: Message dictionary
        :return: Status of the processing
        :rtype: str
        """
        topic = dctmsg['topic']
        payload = dctmsg['payload']
        resource_id = payload['id']
        resource_status = payload['status']
        previous_price = payload['previous_price']

        # Calculate the bidding price based on RESOURCE status and MATERIAL parameters
        bidding_price = calculate_bidding_price(
            material_params=self.params, resource_status=resource_status, previous_price=previous_price
        )
        if bidding_price is not None:
            sendmsgtopic(
                producer=self.producer,
                tsend=topic,
                topic=topic,
                source=self.agent,
                dest=resource_id,
                action="COUNTERBID",
                payload=dict(id=self.agent, material_params=self.params, price=bidding_price),
                vb=self.verbose
            )
            if self.verbose > 2:
                self.write_log(f"Instructed {resource_id} to counterbid")
        else:
            if self.verbose > 1:
                self.write_log(
                    f"Rejected offer from {resource_id}. "
                    f"This resource is not among the allowed resources for the material"
                )

        return 'CONTINUE'

    def handle_askconfirm_action(self, dctmsg: dict) -> str:
        """
        Handles the ASKCONFIRM action.
        It answers the resource to indicate that the material can be assigned to the resource
        and has not already been assigned to another resource.

        :param dict dctmsg: Message dictionary
        :return: Status of the handling
        :rtype: str
        """
        topic = dctmsg['topic']
        resource = dctmsg['payload']['id']
        sendmsgtopic(
            producer=self.producer,
            tsend=topic,
            topic=topic,
            source=self.agent,
            dest=resource,
            action="CONFIRM",
            payload=dict(id=self.agent, material_params=self.params),
            vb=self.verbose
        )

        self.assigned_resource = resource
        if self.verbose > 1:
            self.write_log(
                f"Assigned material to resource {self.assigned_resource}. Sending ASSIGNED message..."
            )
        full_msg = dict(
            source=self.agent, dest=self.agent, topic=self.topic, action='SENDASSIGNED', payload=dict()
        )
        self.handle_sendassigned_action(full_msg)

        if self.verbose > 1:
            self.write_log(
                f"Assigned material to resource {self.assigned_resource} and sent ASSIGNED message. "
                f"Killing the agent..."
            )
        return 'END'

    def handle_sendassigned_action(self, dctmsg: dict) -> str:
        """
        Handles the SENDASSIGNED action.
        It informs all resources (except the assigned resource)
        that this material has already been ASSIGNED to another resource.

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
            dest=f"^(?!{self.assigned_resource})(RESOURCE:{topic}:.*)$",
            action="ASSIGNED",
            payload=dict(id=self.agent),
            vb=self.verbose
        )
        if self.verbose > 1:
            self.write_log(f"Informed all resources (except {self.assigned_resource}) that {self.agent} is ASSIGNED.")
        return 'CONTINUE'


def create_material(init_kwargs: dict):
    """
    Helper function to create Material instances asynchronously with Python's multiprocessing.
    The reason for this function is that multiprocessing can handle functions but not methods.
    Source: https://stackoverflow.com/questions/41000818/can-i-pass-a-method-to-apply-async-or-map-in-python-multiprocessing

    :param dict init_kwargs:
    """
    material = Material(**init_kwargs)
    material.follow_topic()


def main():
    """
    Create the general MATERIAL and make it follow the general topic

    :param str base: Path for the configuration file. Passed in the command line
    :param int verbose: Option to print information. Passed in the command line
    """

    # Extract the 'verbose' command line argument
    # The value in 'base' indicates the path to the configuration file
    # where the IP will be read
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
        base = args["base"]
    if verbose > 0:
        print(f"Running program with {verbose=}, {base=}.")

    # Global configuration
    config = configparser.ConfigParser()
    config.read(base + '/config.cnf')
    kafka_ip = config['DEFAULT']['IP']

    main_material = Material(
        topic=TOPIC_GEN, agent=f"MATERIAL:{TOPIC_GEN}", params=dict(), kafka_ip=kafka_ip, verbose=verbose
    )
    main_material.follow_topic()


if __name__ == '__main__':
    main()
