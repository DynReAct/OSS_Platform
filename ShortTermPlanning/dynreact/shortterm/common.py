import json
import argparse
from confluent_kafka import Producer


TOPIC_GEN = "DynReact-Gen"


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
    producer.produce(value=mtxt, topic=tsend, on_delivery=confirm)
    producer.flush()
