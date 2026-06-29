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
        - RunAgents (-g): 0 => General agents are not launched; 100 => Material ; 010 => Equipment; 001 => Log;

    Example:

        To replace all base agents run: python3 replace_base.py -v 3  -b . -g 111
"""

from typing import Any
import argparse
import os
import re
import time

from confluent_kafka import Producer
from dynreact.shortterm.common import VAction, KeySearch, initialize_keysearch_from_runtime, purge_topics
from dynreact.shortterm.short_term_planning import clean_agents, run_general_agents


def _normalize_profile_token(value: str | None) -> str | None:
    """Return one normalized profile label when it is present in the text."""
    if value is None:
        return None
    lowered = str(value).strip().lower()
    if lowered == "":
        return None
    if "oss" in lowered:
        return "oss"
    if "ras" in lowered:
        return "ras"
    return None


def _validate_safe_replace_base_context(
    topic_gen: str | None,
    topic_callback: str | None,
    topic_prefix: str | None,
    expected_profile: str | None = None,
) -> str:
    """Reject replace-base runs unless they target one test-scoped profile context."""
    missing = [
        label for label, value in (
            ("TOPIC_GEN", topic_gen),
            ("TOPIC_CALLBACK", topic_callback),
        )
        if not isinstance(value, str) or value.strip() == ""
    ]
    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(f"replace_base requires configured topics. Missing or empty: {joined}.")

    normalized_topic_gen = str(topic_gen).strip()
    normalized_topic_callback = str(topic_callback).strip()
    normalized_topic_prefix = None if topic_prefix is None else str(topic_prefix).strip()

    non_test_topics = [
        topic_name for topic_name in (normalized_topic_gen, normalized_topic_callback)
        if re.search(r"test", topic_name, flags=re.IGNORECASE) is None
    ]
    if non_test_topics:
        joined = ", ".join(non_test_topics)
        raise RuntimeError(
            "replace_base is restricted to TEST contexts and refused to act on "
            f"non-test topics: {joined}."
        )

    detected_profiles = {
        profile for profile in (
            _normalize_profile_token(normalized_topic_gen),
            _normalize_profile_token(normalized_topic_callback),
            _normalize_profile_token(normalized_topic_prefix),
        )
        if profile is not None
    }
    if len(detected_profiles) != 1:
        detected = ", ".join(sorted(detected_profiles)) if detected_profiles else "none"
        raise RuntimeError(
            "replace_base could not resolve one unambiguous profile from the configured "
            f"context. Detected profiles: {detected}. "
            f"TOPIC_GEN={normalized_topic_gen}, TOPIC_CALLBACK={normalized_topic_callback}, "
            f"KAFKA_TOPIC_PREFIX={normalized_topic_prefix}."
        )

    resolved_profile = next(iter(detected_profiles))
    normalized_expected_profile = _normalize_profile_token(expected_profile)
    if normalized_expected_profile is not None and resolved_profile != normalized_expected_profile:
        raise RuntimeError(
            "replace_base profile mismatch. "
            f"Expected {normalized_expected_profile}, detected {resolved_profile} from "
            f"TOPIC_GEN={normalized_topic_gen}, TOPIC_CALLBACK={normalized_topic_callback}, "
            f"KAFKA_TOPIC_PREFIX={normalized_topic_prefix}."
        )

    return resolved_profile


def main() -> Any:
    """
    Main module focused on cleaning the kafka queue.
    params are provided as external arguments in command line.

    :param str base: Path to the config file.
    :param int verbose: Verbosity level.
    """
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

    initialize_keysearch_from_runtime(overrides={"VB": verbose})

    kafka_ip = KeySearch.search_for_value("KAFKA_IP")

    if verbose > 0:
        print(f"Running program with {verbose=}, {rungagnts=}")

    producer_config = {
        "bootstrap.servers": kafka_ip,
        'linger.ms': 100,
        'acks': 'all'
    }
    producer = Producer(producer_config)

    topic_callback = KeySearch.search_for_value("TOPIC_CALLBACK")
    topic_gen = KeySearch.search_for_value("TOPIC_GEN")
    topic_prefix = KeySearch.search_for_value("KAFKA_TOPIC_PREFIX")
    expected_profile = os.environ.get("EXPECTED_STP_PROFILE")

    resolved_profile = _validate_safe_replace_base_context(
        topic_gen=topic_gen,
        topic_callback=topic_callback,
        topic_prefix=topic_prefix,
        expected_profile=expected_profile,
    )

    if verbose > 0:
        print(
            "Validated replace_base context for "
            f"profile={resolved_profile}, topic_gen={topic_gen}, topic_callback={topic_callback}."
        )
        print(f"Purging verification topics: {topic_gen}, {topic_callback}, DYN_TEST")
    purge_topics(topics=[topic_callback, topic_gen, "DYN_TEST"])

    clean_agents(producer=producer, verbose=verbose, rungagnts=rungagnts)
    run_general_agents(producer=producer, gagents=rungagnts, verbose=verbose)

    print("Sleeping for 2 minutes")
    time.sleep(120)

    print("Done, containers should be restarted")

    return None


if __name__ == '__main__':
    main()
