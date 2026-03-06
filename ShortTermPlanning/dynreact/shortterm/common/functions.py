"""
 Module: functions.py 

Functions that depend on the material parameters and equipment status.
These functions depend on how these values are given.
"""
import os
from datetime import datetime, timedelta
import random
from dynreact.shortterm.common.data.data_functions import get_transition_cost_and_status

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

def load_transport_times(file_path: str) -> dict[str, dict[str, int]]:
    """
    Extract transport times from a CSV file and converts into a nested dictionary.

    :param str file_path: Path to the CSV file.

    :return: Nested dictionary with transport times.
    :rtype: dict[str, dict[str, int]]
    """

    transport_times = {}
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return transport_times

    with open(file_path, 'r') as file:
        print(f"Opening file: {file_path}")
        next(file) # Skip the header
        for line in file:
            print(f"Processing line: {line}")
            parts = line.strip().split(';')
            if len(parts) == 3:
                origin = parts[0].strip()
                dest = parts[1].strip()
                time = int(parts[2].strip())
                print(f"Origin: {type(origin)}, Destination: {type(dest)}, Time: {type(time)}")

                if origin not in transport_times:
                    transport_times[origin] = {}

                transport_times[origin][dest] = time

    return transport_times

def get_transport_times(perf_url: str) -> dict:
#TODO: add docs

    print(f"PERF_URL: {perf_url}, type: {type(perf_url)}")

    if not isinstance(perf_url, str):
        print(f"Transport times URL is not a string: {perf_url}")
        return {}

    if perf_url.startswith("default+file:"):
        file_path = perf_url.split("default+file:")[1]
        print(f"Loading transport times from file: {file_path}")
        return load_transport_times(file_path)

    elif perf_url.startswith("http://") or perf_url.startswith("https://"):
        print(f"Loading transport times from URL: {perf_url}")
        pass #TODO: Implement service for transport times

    print(f"Unknown transport times URL: {perf_url}")

    return {}
