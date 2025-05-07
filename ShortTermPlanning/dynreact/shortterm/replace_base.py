"""
Module: replace_base.py

This program runs the scripts required to replace the general agents remotely

First Prototype of Docker oriented solution for the UX service

Version History:
- 1.0 (2024-03-09): Initial version developed by Rodrigo Castro Freibott.
- 2.0 (2025-05-06): Replace solution to a Docker approach by Hector Flores

Note:
    The program accepts two input parameters:

        - Verbose (-v): Verbosity Level 1-5
        - Base (-b): Base configuration file
        - RunAgents (-g): 0 => General agents are not launched; 100 => Material ; 010 => Equipment; 001 => Log;

    Example:

        To replace all base agents run: python3 replace_base.py -v 3  -b . -g 111
"""

import os
import argparse
import time

from confluent_kafka import Producer
import configparser
from common import VAction
from short_term_planning import clean_agents

def main():
    """
    Main module focused on cleaning the kafka queue.
    params are provided as external arguments in command line.
    
    :param str base: Path to the config file.
    :param int verbose: Verbosity level.
    """
    # Extract the command line arguments
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "-v", "--verbose", nargs='?', action=VAction,
        dest='verbose', help="Option for detailed information"
    )
    ap.add_argument(
        "-g", "--rungagents", default='000', type=str,
        help="0 => General agents are not launched; 100 => Material ; 010 => Equipment; 001 => Log; "
    )
    args = vars(ap.parse_args())

    verbose = args["verbose"]
    rungagnts = str(args['rungagents'])

    config = configparser.ConfigParser()
    current_dir = os.path.dirname(os.path.abspath(__file__))
    config.read(os.path.join(current_dir, "config.cnf"))
    kafka_ip = config['DEFAULT']['IP']

    if verbose > 0:
        print( f"Running program with {verbose=}, {rungagnts=} ")

    producer_config = {
        "bootstrap.servers": kafka_ip,
        'linger.ms': 100,  # Reduce latency
        'acks': 'all'  # Ensure message durability
    }
    producer = Producer(producer_config)

    clean_agents(producer=producer, verbose=verbose, rungagnts=rungagnts)

    print("Sleeping for 30 seconds")
    time.sleep(30)

    print("Done, containers should be restarting")

    return None


if __name__ == '__main__':
    main()


