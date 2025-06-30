import json
from datetime import datetime
import os
import traceback

from confluent_kafka import Producer, OFFSET_END, TopicPartition
from confluent_kafka.admin import AdminClient

from dynreact.shortterm.shorttermtargets import ShortTermTargets

def _compute_partition_topic(topic_name: str, admin_client: AdminClient):
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

def purge_topics(topics: list):
    """
    Function to purge list of topics.

    :param str topics: Topic names to search partitions for.

    returns: list of purged topics.
    """

    admin_client = AdminClient({"bootstrap.servers": KeySearch.search_for_value("IP")})

    topics_partitions = []
    for topic in topics:
        topics_partitions.extend(_compute_partition_topic(topic, admin_client))

    topics = admin_client.delete_records(topics_partitions)

    for tp, f in topics.items():
        try:
            f.result()  # Raises exception if delete failed
        except Exception as e:
            dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
            raise Exception(f"{dt} | ERROR: Failed: {tp} with error {e}")

def delete_topics(topics: list, silent=False):
    """
    Function to delete list of topics.

    :param str topics: Topic names to search partitions for.

    returns: list of purged topics.
    """

    admin_client = AdminClient({"bootstrap.servers": KeySearch.search_for_value("IP")})

    topics_partitions = []
    for topic in topics:
        topics_partitions.extend(_compute_partition_topic(topic, admin_client))

    topics = admin_client.delete_topics(topics=topics)

    for tp, f in topics.items():
        try:
            f.result()  # Raises exception if delete failed
        except Exception as e:
            if not silent:
                dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
                raise Exception(f"{dt} | ERROR: Failed: {tp} with error {e}")

class KeySearch:
    _global_config: ShortTermTargets = None

    @classmethod
    def set_global(cls, config_provider: ShortTermTargets):
        """
        Function to update the config provider.

        :param str config_provider: The configuration provider with the set values
        """
        cls._global_config = config_provider

    @classmethod
    def search_for_value(cls, key_name, default_value=None):
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
            cfg = cls._global_config.model_dump()
            delays = cls._global_config.TimeDelays.model_dump()

            return cfg.get(key_name, delays.get(key_name, default_value))

        return default_value

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

    def __init__(self, option_strings, dest, nargs=None, const=None,
                 default=None, type=None, choices=None, required=False,
                 help=None, metavar=None):
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

    def __call__(self, parser, args, values, option_string=None):
        """
        Function able to handle the arguments.

        :param object parser: Object in charge of processing the operation.
        :param dict dict: Dictionary of arguments.
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


def confirm(err: str, msg: str) -> None:
    """
    Function to confirm the message delivery and prints an error message if any.

    :param str err: Error message, if any.
    :param str msg: The message being confirmed.
    """
    if err:
        print("Error sending message: " + msg + " [" + err + "]")
    return None


def sendmsgtopic(producer: Producer, tsend: str, topic: str, source: str, dest: str,
                 action: str, payload: dict = None, vb: int = 0) -> None:
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
    mtxt = json.dumps(msg)
    try:
        producer.produce(value=mtxt, topic=tsend, on_delivery=confirm) # 30 seconds
        producer.flush()
    except Exception as e:
        error_message = traceback.format_exc()
        print("Captured error message:")
        print(error_message)  # Prints the traceback as a string
        print(f'Failed to deliver message: {str(e)} - Topic {topic} - Source {source} - Dest {dest}')
