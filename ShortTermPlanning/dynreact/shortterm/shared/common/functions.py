"""
 Module: functions.py 

Functions that depend on the material parameters and equipment status.
These functions depend on how these values are given.
"""
import json
from datetime import datetime, timedelta
import random
from common.data.data_functions import get_transition_cost_and_status

def calculate_bidding_price(material_params: dict, equipment_status: dict, previous_price: float | None) -> float | None:
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

    bidding_price = 150 / (delivery_date - datetime(2020, 1, 1)).days

    # For now, the bidding price is simply increased by the previous bidding price
    if previous_price is not None:
        bidding_price += previous_price

    return bidding_price


def calculate_production_cost(material_params: dict, equipment_status: dict, verbose: int) -> float | None:
    """
    Calculates the production cost incurred by processing the given MATERIAL
    with the given EQUIPMENT. Returns None if the equipment cannot process the material.

    :param dict equipment_status: Status of the EQUIPMENT
    :param dict material_params: Parameters of the MATERIAL
    :param int verbose: Verbosity Level

    :return: Production cost
    :rtype: float
    """
    prod_cost, _ = get_transition_cost_and_status(material_params=material_params, equipment_status=equipment_status, verbose=verbose)
    return prod_cost


def get_new_equipment_status(material_params: dict, equipment_status: dict, verbose: int) -> dict | None:
    """
    Get the status of the EQUIPMENT after processing the given MATERIAL

    :param dict equipment_status: Status of the EQUIPMENT
    :param dict material_params: Parameters of the MATERIAL
    :param int verbose: Verbosity Level

    :return: New equipment status
    :rtype: float
    """
    _, new_status = get_transition_cost_and_status(material_params=material_params, equipment_status=equipment_status, verbose=verbose)
    return new_status
