import json
import os
import re
import time
import sys
from confluent_kafka import Producer, Consumer
from common import sendmsgtopic


class Agent:
    """
    Class Generic Agent. supporting the basic concepts.

    Attributes:
        topic     (str): Topic driving the relevant converstaion.
        agent     (str): Name of the agent creating the object.
        kafka_ip  (str): IP address and TCP port of the broker.
        verbose   (int): Level of details being saved.

    .. _Google Python Style Guide:
       https://google.github.io/styleguide/pyguide.html
    """

    def __init__(self, topic: str, agent: str, kafka_ip: str, verbose: int = 1):
        """
           Constructor function for the Log Class

        :param str topic: Topic driving the relevant converstaion.
        :param str agent: Name of the agent creating the object.
        :param str kafka_ip: IP address and TCP port of the broker.
        :param int verbose: Level of details being saved.
        """

        self.topic = topic
        self.agent = agent
        self.kafka_ip = kafka_ip
        self.verbose = verbose

        self.iter_no_msg = 0
        self.min_verbose = 1
        self.action_methods = {
            'PING': self.handle_ping_action, 'EXIT': self.handle_exit_action
        }

        # Each agent must be in an independent consumer group so
        # the message consumed by one AGENT can also be consumed by other AGENTs
        self.producer = Producer({"bootstrap.servers": self.kafka_ip})
        self.consumer = Consumer(
            {"bootstrap.servers": self.kafka_ip, "group.id": self.agent, "auto.offset.reset": "earliest"}
        )
        self.consumer.subscribe([self.topic])

    def write_log(self, msg: str):
        """
        Write the given message in the topic's LOG

        :param str msg: Message sent by the agent
        """
        sendmsgtopic(
            producer=self.producer, tsend=self.topic, topic=self.topic, source=self.agent,
            dest="LOG:" + self.topic, action="WRITE", payload=dict(msg=msg), vb=self.verbose
        )

    def handle_ping_action(self, dctmsg: dict) -> str:
        """
        Send a message to the pinging agent (the LOG) to confirm the presence of this AGENT

        :param dict dctmsg: Message Dictionary

        :returns: Logger object
        :rtype:  Logger object
        """
        topic = dctmsg['topic']
        pinging_agent = dctmsg['source']
        sendmsgtopic(
            producer=self.producer,
            tsend=topic,
            topic=topic,
            source=self.agent,
            dest=pinging_agent,
            action="PINGANSWER",
            payload=dict(),
            vb=self.verbose
        )
        return 'CONTINUE'

    def handle_exit_action(self, dctmsg: dict = None) -> str:
        """
        Handles the EXIT action.

        :param dict dctmsg: Message dictionary

        :returns: Status of the handling
        :rtype:  str
        """
        return 'END'

    def process_message(self, action: str, dctmsg: dict) -> str:
        """
        Processes a Kafka message.

        :param str action: Action to be performed
        :param dict dctmsg: Message dictionary

        :returns: Status of the handling
        :rtype:  str
        """
        if action in self.action_methods:
            try:
                return self.action_methods[action](dctmsg)
            except KeyboardInterrupt:
                self.write_log("Program stopped by user")
                raise KeyboardInterrupt
            except Exception as e:
                self.write_log(f"ERROR: Raised error {type(e)} with message {e}")
                return 'ERROR'
        else:
            return 'UNKNOWN-ACTION'

    def callback_before_message(self) -> str:
        """
        Function executed before a message is polled.

        :returns: Status of the callback.
        :rtype:  str
        """
        return 'CONTINUE'

    def callback_on_topic_not_available(self, topic: str = None):
        """
        Function executed when 'Subscribed topic not available'
        
        """

    def callback_on_not_match(self, dctmsg: dict):
        """
        Function executed when the agent is not the destination of the message
        
        """
        pass

    def read_message(self) -> str:
        """
        Poll and read a Kafka message

        :returns: Status after reading the message
        :rtype:  str
        """
        self.iter_no_msg += 1

        status = self.callback_before_message()
        if status != 'CONTINUE':
            return status

        # Get a message
        message_obj = self.consumer.poll(timeout=1)

        # If there is no message, go to the next iteration
        if message_obj.__str__() == 'None':
            #if (self.verbose > self.min_verbose) and ((self.iter_no_msg - 1) % 5 == 0):
                #self.write_log(f"Iteration {self.iter_no_msg - 1}. No message found.")
            time.sleep(1)
            return 'CONTINUE'

        # Extract the information from the message
        # topic - in our case, it can be the general topic or an auction's topic
        # vals - the information inside the message
        # part (partition) - the group of messages that the message belongs to within the topic
        # key - an optional argument to keep messages with the same key in the same partition
        # offst (offset) - identifier of the message inside the topic
        # More information: https://chat.openai.com/share/5e324c3f-26e6-4053-a798-79cfa1b89460
        messtpc = message_obj.topic()
        vals = message_obj.value()
        part = message_obj.partition()
        key = message_obj.key()
        offst = message_obj.offset()

        # If the subscribed topic does not exist, go to the next iteration
        # This must be done before checking message_obj.error()
        if message_obj.error() is not None:
            self.callback_on_topic_not_available()
            return 'CONTINUE'
        else:
            # Commit the message to indicate Kafka that it has already been processed,
            # so the same message is not received again
            self.consumer.commit(message_obj)

        # If the topic of the message doesn't match this topic, go to the next iteration
        if messtpc != self.topic:
            return 'CONTINUE'

        # If the message contains an error, raise it
        if message_obj.error():
            # End of partition event
            if self.verbose > 1:
                self.write_log("Error encountered.")
            sys.stderr.write('%% %s [%d] reached end at offset %d\n' %
                             (message_obj.topic(), message_obj.partition(),
                              message_obj.offset()))

        # If the destinations of the message do not include this AGENT, go to the next iteration
        dctmsg = json.loads(vals)
        match = re.search(dctmsg['dest'], self.agent)
        if not match:
            self.callback_on_not_match(dctmsg)
            return 'CONTINUE'

        # Reset the count of empty checks
        self.iter_no_msg = 0

        # At this point, the message is valid and destined to this agent
        # You can only notify the log now; otherwise Kafka will be cluttered with messages in an infinite loop
        if self.verbose > self.min_verbose:
            self.write_log(
                f"Polled message with topic {messtpc}, values {vals}, partition {part}, "
                f"offset {offst} and key {key}"
            )

        # Perform the action and get the corresponding status
        action = dctmsg['action'].upper()
        if self.verbose > self.min_verbose:
            self.write_log(f"Performing action {action}...")
        status = self.process_message(action=action, dctmsg=dctmsg)
        if self.verbose > self.min_verbose:
            self.write_log(f"Resulting status: {status}")

        return status

    def follow_topic(self) -> None:
        """
        Loop in which an AGENT follows the general topic or an auction's topic.
        The AGENT can act both as a producer and a consumer.

        """

        if self.verbose > 1:
            self.write_log(f"Spawned a process for agent {self.agent} to follow topic {self.topic}.")

        status = 'GO'
        while status != 'END':
            status = self.read_message()

        # We close the consumer to release any equipment it is using
        # The producer does not need to be closed, since it is automatically garbage collected:
        # https://github.com/confluentinc/confluent-kafka-python/issues/127
        self.consumer.close()
        if self.verbose > 1:
            self.write_log(f"Ending spawned process for agent {self.agent} in topic {self.topic}.")
