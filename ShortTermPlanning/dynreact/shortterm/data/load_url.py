"""
load_url.py
This module contains the URLs with relevant data and the functions used to load their data.
"""
import configparser
import requests
import os

config = configparser.ConfigParser()
current_dir = os.path.dirname(os.path.abspath(__file__))
config.read(os.path.join(current_dir, "..", "config.cnf"))
REST_URL = config['DEFAULT']['REST_URL']

URL_SNAPSHOTS = REST_URL + '/snapshots'
URL_SNAPSHOT_DATA = REST_URL + '/snapshots/{snapshot_timestamp}'
URL_INITIAL_STATE = REST_URL + '/costs/status/{plant_id}/{snapshot_timestamp}?unit=coil'
URL_UPDATE_STATUS = REST_URL + '/costs/transitions-stateful'


def load_url_json_get(url: str, verbose: int = 1) -> dict:
    """
    Load the JSON data from the given URL using the GET method. Raises an error when the response is not OK.


    :param str url: Url for the json file to be used.
    :param int verbose: Verbosity Level.

    :return: Relevant dataset read.
    :rtype: dict
    """
    response = requests.get(url)
    if response.ok:
        data = response.json()
    else:
        error_msg = f"ERROR: Failed to retrieve data from {url}: {response.status_code} {response.text}"
        if verbose > 0:
            print(error_msg)
        raise requests.exceptions.HTTPError(error_msg)
    return data


def load_url_json_post(url: str, payload: dict, verbose: int = 1) -> dict:
    """
    Load the JSON data from the given URL using the POST method. Raises an error when the response is not OK.

    :param str url: Url for the json file to be used.
    :param dict payload: Dictionary for the message.
    :param int verbose: Verbosity Level.

    :return: Relevant dataset read.
    :rtype: dict
    """
    response = requests.post(url, json=payload)
    if response.ok:
        data = response.json()
    else:
        error_msg = f"ERROR: Failed to retrieve data from {url}: {response.status_code} {response.text}"
        if verbose > 0:
            print(error_msg)
        raise requests.exceptions.HTTPError(error_msg)
    return data
