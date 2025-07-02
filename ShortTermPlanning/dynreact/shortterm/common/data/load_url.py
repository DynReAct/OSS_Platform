"""
load_url.py
This module contains the URLs with relevant data and the functions used to load their data.
"""
from datetime import datetime
from dynreact.shortterm.common import KeySearch
import requests

URL_SNAPSHOTS = '/snapshots'
URL_SNAPSHOT_DATA = '/snapshots/{snapshot_timestamp}'
URL_INITIAL_STATE = '/costs/status/{equipment_id}/{snapshot_timestamp}?unit=material'
URL_UPDATE_STATUS = '/costs/transitions-stateful'

DOCKER_MANAGER="_manager"
DOCKER_REPLICA="_replica"

def build_url(path: str):
    """
    Since parameters like IP can change any second, we force to doublecheck the base URL each time to always have the latest.

    :param str path: Base path to check

    :return: Full URL.
    :rtype: str
    """

    return KeySearch.search_for_value("REST_URL") + path

def load_url_json_get(path_url: str, verbose: int = 1) -> dict:
    """
    Load the JSON data from the given URL using the GET method. Raises an error when the response is not OK.


    :param str path_url: Path URL for the json file to be used.
    :param int verbose: Verbosity Level.

    :return: Relevant dataset read.
    :rtype: dict
    """
    full_url = build_url(path_url)
    response = requests.get(full_url)
    if response.ok:
        data = response.json()
    else:
        dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
        error_msg = f"{dt} | ERROR: Failed to retrieve data from {full_url}: {response.status_code} {response.text}"
        if verbose > 0:
            print(error_msg)
        raise requests.exceptions.HTTPError(error_msg)
    return data


def load_url_json_post(path_url: str, payload: dict, verbose: int = 1) -> dict:
    """
    Load the JSON data from the given URL using the POST method. Raises an error when the response is not OK.

    :param str path_url: Path URL for the json file to be used.
    :param dict payload: Dictionary for the message.
    :param int verbose: Verbosity Level.

    :return: Relevant dataset read.
    :rtype: dict
    """
    full_url = build_url(path_url)
    response = requests.post(full_url, json=payload)
    if response.ok:
        data = response.json()
    else:
        # Getting the current date and time
        dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
        error_msg = f"{dt} | ERROR: Failed to retrieve data from {full_url}: {response.status_code} {response.text}"
        if verbose > 0:
            print(error_msg)
        raise requests.exceptions.HTTPError(error_msg)
    return data
