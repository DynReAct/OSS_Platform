"""Common short-term planning utilities for OSS_Platform/ShortTermPlanning/dynreact/shortterm/common/__init__.

The module is documented in English to make the short-term planning
workflow easier to maintain across OSS and RAS-specific integrations.
"""

from typing import Any
import json
import argparse
from datetime import datetime
import os
import traceback
from uuid import uuid4

from confluent_kafka import KafkaException, KafkaError, Message, Producer, Consumer, OFFSET_END, TopicPartition
from confluent_kafka.admin import AdminClient, NewTopic
from flatdict import FlatDict

from dynreact.shortterm.shorttermtargets import ShortTermTargets

def _compute_partition_topic(topic_name: str, admin_client: AdminClient) -> Any:
    """
    Function to list topic partitions.

    :param str topic_name: Topic name to search partitions for.
    :param AdminClient admin_client: Confluent kafka admin client.

    returns: list of topic partitions.
    """

    # Fetch metadata for the topic
    md = admin_client.list_topics(timeout=10)

    if topic_name not in md.topics:
        print(f"Topic '{topic_name}' not found.")
        return []
    else:
        partitions = md.topics[topic_name].partitions
        return list(map(lambda p: TopicPartition(topic_name, int(p), offset=OFFSET_END), partitions.keys()))

def shared_topics() -> set[str]:
    """Return the configured parent and callback channels; neither belongs to an auction."""
    return {str(value) for key in ("TOPIC_GEN", "TOPIC_CALLBACK")
            if (value := KeySearch.search_for_value(key))}


def protect_shared_topics(topics: list[str], *, allow_shared: bool = False) -> None:
    """Reject an entire destructive request before contacting Kafka.

    ``allow_shared`` is reserved for explicitly offline maintenance on an isolated
    broker/context. A message's age or a momentary zero lag is not authorization.
    """
    protected = shared_topics().intersection(topics)
    if protected and not allow_shared:
        raise ValueError(f"Refusing to delete shared Kafka history: {sorted(protected)}")


def create_callback_consumer(kafka_ip: str, callback_topic: str) -> Consumer:
    """Create an independent callback reader positioned before the next request.

    Explicit assignment at each partition's high watermark avoids both historical
    replay and the subscribe/latest race (assignment occurring after the reply).
    Call this before sending requests, and always close the returned consumer.
    Request IDs still distinguish replies from other readers and delayed replies.
    """
    # The first requester may arrive before any callback has ever been produced.
    # Create-only is harmless to an existing channel and preserves its configuration.
    admin = AdminClient({"bootstrap.servers": kafka_ip})
    try:
        admin.create_topics([NewTopic(callback_topic, num_partitions=1, replication_factor=1)])[callback_topic].result()
    except KafkaException as exc:
        if exc.args[0].code() != KafkaError.TOPIC_ALREADY_EXISTS:
            raise
    consumer = Consumer({
        "bootstrap.servers": kafka_ip,
        "group.id": f"UX-{uuid4().hex}",
        "enable.auto.commit": False,
        "enable.auto.offset.store": False,
        "allow.auto.create.topics": False,
    })
    try:
        metadata = consumer.list_topics(topic=callback_topic, timeout=10)
        topic_metadata = metadata.topics[callback_topic]
        if topic_metadata.error is not None or not topic_metadata.partitions:
            raise RuntimeError(f"Callback topic unavailable: {callback_topic}")
        partitions = []
        for partition in topic_metadata.partitions:
            tp = TopicPartition(callback_topic, partition)
            _, high = consumer.get_watermark_offsets(tp, timeout=10, cached=False)
            partitions.append(TopicPartition(callback_topic, partition, high))
        consumer.assign(partitions)
        return consumer
    except BaseException:
        consumer.close()
        raise


def purge_topics(topics: list[str], *, allow_shared: bool = False) -> None:
    """
    Delete all retained records in the requested topics.

    Shared channels are rejected unless explicitly opted into offline maintenance.

    :param str topics: Topic names to search partitions for.

    returns: list of purged topics.
    """

    protect_shared_topics(topics, allow_shared=allow_shared)
    admin_client = AdminClient({"bootstrap.servers": KeySearch.search_for_value("KAFKA_IP")})

    topics_partitions = []
    for topic in topics:
        topics_partitions.extend(_compute_partition_topic(topic, admin_client))

    if not topics_partitions:
        return
    delete_results = admin_client.delete_records(topics_partitions)

    for tp, f in delete_results.items():
        try:
            f.result()  # Raises exception if delete failed
        except Exception as e:
            dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
            raise Exception(f"{dt} | ERROR: Failed: {tp} with error {e}")

def delete_topics(topics: list[str], silent: bool = False, *, allow_shared: bool = False) -> None:
    """
    Delete topics, rejecting shared channels before any broker operation.

    :param str topics: Topic names to search partitions for.

    returns: list of purged topics.
    """

    protect_shared_topics(topics, allow_shared=allow_shared)
    admin_client = AdminClient({"bootstrap.servers": KeySearch.search_for_value("KAFKA_IP")})

    topics_partitions = []
    for topic in topics:
        topics_partitions.extend(_compute_partition_topic(topic, admin_client))

    delete_results = admin_client.delete_topics(topics=topics)

    for tp, f in delete_results.items():
        try:
            f.result()  # Raises exception if delete failed
        except Exception as e:
            if not silent:
                dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
                raise Exception(f"{dt} | ERROR: Failed: {tp} with error {e}")

def list_existing_topics(kafka_ip: str | None = None, timeout: float = 10.0) -> set[str] | None:
    """Lists the topics currently present in the Kafka broker.

    Args:
        kafka_ip: Bootstrap servers. Defaults to the ``KAFKA_IP`` value of ``KeySearch``.
        timeout: Seconds to wait for the broker metadata.

    Returns:
        Set of topic names, or None when the broker could not be queried. Callers must
        treat None as "unknown", never as "no topics".
    """
    try:
        admin_client = AdminClient({"bootstrap.servers": kafka_ip or KeySearch.search_for_value("KAFKA_IP")})
        return set(admin_client.list_topics(timeout=timeout).topics.keys())
    except Exception as e:
        print(f"Could not list the Kafka topics: {e}")
        return None


class KeySearch:
    """Key search.
    
    This class belongs to the short-term planning integration layer. It
    encapsulates state, configuration, or UI behavior used by the planning
    workflow without changing the runtime semantics of the original module.
    """
    _global_config: ShortTermTargets | None = None

    @classmethod
    def is_initialized(cls) -> Any:
        """
        Returns if the class has been initialized.

        returns: boolean True or False.
        """
        return cls._global_config is not None

    @classmethod
    def dump_model(cls, include_env: bool = True) -> Any:
        """
        Dump the class information to a dict, assigning values from the config and environment.

        :return: dict The model assigned.
        """

        if cls._global_config is None:
            raise RuntimeError("KeySearch global config has not been set. Call KeySearch.set_global() first.")

        dump_model = cls._global_config.model_copy()
        update = {}

        if include_env:
            for field_name in dump_model.__class__.model_fields.keys():
                if field_name in os.environ:
                    update[field_name] = os.environ[field_name]

        merged = dump_model.model_dump()
        merged.update(update)
        return dump_model.__class__.model_validate(merged).model_dump()

    @classmethod
    def assign_value(cls, key: str, value: str) -> None:
        """
        Assign new single value to a key.

        :param str key: Key values to assign.
        :param str value: New value.

        :return: None.
        """
        if cls._global_config is None:
            raise RuntimeError("KeySearch global config has not been set. Call KeySearch.set_global() first.")

        merged = cls._global_config.model_dump()
        merged[key] = value
        cls._global_config = cls._global_config.__class__.model_validate(merged)

    @classmethod
    def assign_values(cls, new_values: dict) -> None:
        """
        Assign new values to keys (batch).

        :param dict new_values: Key values to assign.
        :return: None.
        """
        if cls._global_config is None:
            raise RuntimeError("KeySearch global config has not been set. Call KeySearch.set_global() first.")

        merged = cls._global_config.model_dump()
        merged.update(new_values)
        cls._global_config = cls._global_config.__class__.model_validate(merged)

    @classmethod
    def set_global(cls, config_provider: ShortTermTargets) -> None:
        """
        Function to update the config provider.

        :param str config_provider: The configuration provider with the set values
        """
        cls._global_config = config_provider

    @classmethod
    def _get_value(cls, key_name: str, default_value: Any=None) -> Any:
        """
        Retrieve the value associated with a flattened key segment from the configuration.

        :param key_name: The segment of the flattened key to match.
        :param default_value: Value to return if no match is found.
        :return: Matched value or the default.
        """
        if cls._global_config is None:
            return default_value

        cfg = cls._global_config.model_dump()

        flatten_cfg = FlatDict(cfg, delimiter='.')
        look_function = (value for key, value in flatten_cfg.items() if key_name == key.split(".")[-1])

        deep_search = next(look_function, default_value)

        return default_value if deep_search is None else deep_search

    @classmethod
    def search_for_value(cls, key_name: Any, default_value: Any=None) -> Any:
        """
        Function to check for a given key name between env and context including recursive structure.

        Priority list:

            - Environment value
            - STP Context/Config definition

        :param str key_name: Key name to search for
        :param str default_value: Default value in case not found

        returns: value of key otherwise null or default value.
        """

        if cls._global_config is None:
            raise RuntimeError("KeySearch global config has not been set. Call KeySearch.set_global() first.")

        if key_name in os.environ:
            return os.environ[key_name]

        if cls._global_config:
            return cls._get_value(key_name, default_value)

        return default_value


def initialize_keysearch_from_runtime(
    *,
    default_uri: str = "default+file:./data/stp_context.json",
    overrides: dict[str, Any] | None = None,
) -> ShortTermTargets:
    """
    Initialize ``KeySearch`` from the runtime STP context when available.

    The short-term agents and helper scripts are often started directly from a
    container entrypoint, without going through the UI path that loads
    ``stp_context.json``. In that case, relying on ``ShortTermTargets()``
    alone silently falls back to OSS defaults. This helper keeps the existing
    environment precedence but first loads the configured STP JSON when it is
    present in the container.
    """

    config: ShortTermTargets | None = None
    uri = os.getenv("SHORT_TERM_PLANNING_PARAMS", default_uri)

    if isinstance(uri, str) and uri.startswith("default+file:"):
        file_path = uri[len("default+file:"):]
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as file:
                config = ShortTermTargets.model_validate_json(file.read())

    if config is None:
        config = ShortTermTargets()

    if overrides:
        normalized_overrides = {key: value for key, value in overrides.items() if value is not None}
        if normalized_overrides:
            merged = config.model_dump()
            merged.update(normalized_overrides)
            config = config.__class__.model_validate(merged)

    KeySearch.set_global(config_provider=config)
    return config

class VAction(argparse.Action):
    """
    Custom action for argparse to handle verbosity levels.
    From https://stackoverflow.com/questions/6076690/
    verbose-level-with-argparse-and-multiple-v-options

    Attributes:
        option_strings (str): String with options to be considered.
        dest  (str): Variable name storing the result.
        nargs (int): Number of Arguments.
        const (bool): Constant or variable.
        default (str): Default value when absent.
        type (str): Type of data being processed.
        choices (str): Set of values .
        required (bool): Required or not.
        help (str): String describing the meaning of the parameter for help.
        metavar (str):
    """

    def __init__(self, option_strings: Any, dest: Any, nargs: Any=None, const: Any=None,
                 default: Any=None, type: Any=None, choices: Any=None, required: Any=False,
                 help: Any=None, metavar: Any=None) -> None:
        super(VAction, self).__init__(option_strings, dest, nargs, const,
                                      default, type, choices, required,
                                      help, metavar)
        """
        Constructor method of the VAction Class

        :param str option_strings: String with options to be considered.
        :param str dest: Variable name storing the result.
        :param int nargs: Number of Arguments.
        :param bool const: Constant or variable.
        :param str default: Default value when absent.
        :param str type: Type of data being processed.
        :param str choices: Set of values.
        :param bool required: Required or not.
        :param str help: String describing the meaning of the parameter for help.
        :param str metavar: 

        """
        self.values = 0

    def __call__(self, parser: Any, args: Any, values: Any, option_string: Any=None) -> None:
        """
        Function able to handle the arguments.

        :param object parser: Object in charge of processing the operation.
        :param dict args: Dictionary of arguments.
        :param dict values: Dictionary of values.
        :param str option_string: Options requested.
        """
        if values is None:
            self.values += 1
        else:
            try:
                self.values = int(values)
            except ValueError:
                self.values = values.count('v') + 1
        setattr(args, self.dest, self.values)


def confirm(err: KafkaError | None, msg: Message) -> None:
    """
    Function to confirm the message delivery and prints an error message if any.

    :param str err: Error message, if any.
    :param str msg: The message being confirmed.
    """
    if err:
        print(f"Error sending message: {msg} [{err}]")
    return None


def sendmsgtopic(producer: Producer, tsend: str, topic: str, source: str, dest: str,
                 action: str, payload: dict[str, Any] | None = None, vb: int = 0,
                 request_id: str | None = None) -> None:
    """
    Send message to a Kafka topic.

    :param object producer: The Kafka producer instance.
    :param str tsend: The topic to send the message to.
    :param str topic: The topic of the message.
    :param str source: The source of the message.
    :param str dest: The destination of the message.
    :param str action: The action to be performed.
    :param dict payload: The payload of the message. Defaults to {"msg": "-"}
    :param int vb: Verbosity level. Defaults to 0.
    :param str request_id: Optional correlation ID, echoed by LOG callbacks.
    """
    if payload is None:
        payload = {"msg": "-"}
    msg = dict(
        topic=topic,
        action=action,
        source=source,
        dest=dest,
        payload=payload
    )
    if request_id is not None:
        msg["request_id"] = request_id
    mtxt = json.dumps(msg)
    try:
        producer.produce(value=mtxt.encode("utf-8"), topic=tsend, on_delivery=confirm) # 30 seconds
        producer.flush()
    except Exception as e:
        error_message = traceback.format_exc()
        print("Captured error message:")
        print(error_message)  # Prints the traceback as a string
        print(f'Failed to deliver message: {str(e)} - Topic {topic} - Source {source} - Dest {dest}')
