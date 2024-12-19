"""
 Module: functions.py 

Functions that depend on the material parameters and equipment status.
These functions depend on how these values are given.
"""

from datetime import datetime
from data.data_functions import get_transition_cost_and_status


def calculate_bidding_price(material_params: dict, resource_status: dict, previous_price: float | None) -> float | None:
    """
    Calculates the bidding price that the MATERIAL would pay to be processed in the RESOURCE with the given status.
    Returns None if the RESOURCE's status is not compatible with the MATERIAL's parameters.
    Otherwise, returns the bidding price as a float, which depends on the MATERIAL's parameters and the previous
    bidding price (but not on the RESOURCE's status).

    :param dict resource_status: Status of the RESOURCE
    :param dict material_params: Parameters of the MATERIAL
    :param float previous_price: Bidding price in the RESOURCE's previous round

    :return: Bidding price, or None if the MATERIAL cannot be processed by that equipment
    :rtype: float
    """
    # Reject offer is equipment is not among the allowed equipments of the material
    if resource_status['plant'] not in material_params['order']['allowed_plants']:
        return None

    # For now, the bidding price is greater when the delivery date is sooner
    delivery_date = material_params['order']['due_date']
    delivery_date = datetime.strptime(delivery_date, '%Y-%m-%dT%H:%M:%SZ')
    bidding_price = 150 / (delivery_date - datetime(2020, 1, 1)).days

    # For now, the bidding price is simply increased by the previous bidding price
    if previous_price is not None:
        bidding_price += previous_price

    return bidding_price


def calculate_production_cost(material_params: dict, resource_status: dict) -> float | None:
    """
    Calculates the production cost incurred by processing the given MATERIAL
    with the given RESOURCE. Returns None if the equipment cannot process the material.

    :param dict resource_status: Status of the EQUIPMENT
    :param dict material_params: Parameters of the MATERIAL

    :return: Production cost
    :rtype: float
    """
    prod_cost, _ = get_transition_cost_and_status(material_params=material_params, resource_status=resource_status)
    return prod_cost


def get_new_equipment_status(material_params: dict, resource_status: dict) -> float| None:
    """
    Get the status of the EQUIPMENT after processing the given MATERIAL

    :param dict resource_status: Status of the EQUIPMENT
    :param dict material_params: Parameters of the MATERIAL

    :return: New equipment status
    :rtype: float
    """
    _, new_status = get_transition_cost_and_status(material_params=material_params, resource_status=resource_status)
    return new_status
