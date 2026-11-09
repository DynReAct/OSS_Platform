"""Short-term planning agent implementation for OSS_Platform/ShortTermPlanning/dynreact/shortterm/agents/agent.

The module is documented in English to make the short-term planning
workflow easier to maintain across OSS and RAS-specific integrations.
"""

from typing import Any, cast
import json
import re
import time
import sys
import os
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor

from confluent_kafka import Producer, Consumer, KafkaError
from dynreact.shortterm.common import sendmsgtopic, KeySearch, purge_topics, list_existing_topics
import traceback

REAPER_INTERVAL = 60.0
"Default seconds between two sweeps of the reaper of a parent agent"

current_partitions = 0
UNKNOWN_TOPIC_ERRORS = {-188, -191}

def on_assign(consumer: Any, partitions: Any) -> None:
    """On assign.
    
    This function is part of the short-term planning workflow and keeps
    the existing runtime behavior while documenting the public contract.
    
    Args:
        consumer: Input value for the `consumer` parameter.
        partitions: Input value for the `partitions` parameter.
    
    Returns:
        The value produced by the underlying planning, UI, or test helper logic.
    """
    global current_partitions
    print("Partitions assigned:", partitions)
    current_partitions = len(partitions)
    consumer.assign(partitions)

def on_revoke(consumer: Any, partitions: Any) -> None:
    """On revoke.
    
    This function is part of the short-term planning workflow and keeps
    the existing runtime behavior while documenting the public contract.
    
    Args:
        consumer: Input value for the `consumer` parameter.
        partitions: Input value for the `partitions` parameter.
    
    Returns:
        The value produced by the underlying planning, UI, or test helper logic.
    """
    global current_partitions
    print("Partitions revoked:", partitions)
    current_partitions = max(0, current_partitions - len(partitions))
    consumer.unassign()

def _reaper_interval() -> float:
    """Reads ``REAPER_INTERVAL`` (seconds) from the environment. Zero or negative disables the reaper.

    Returns:
        Seconds between sweeps, ``inf`` when the reaper is disabled.
    """
    import os
    raw = os.environ.get("DYNREACT_REAPER_INTERVAL")
    if raw is None or raw == "":
        return REAPER_INTERVAL
    try:
        value = float(raw)
    except ValueError:
        return REAPER_INTERVAL
    return value if value > 0 else float("inf")


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

    def __init__(self, topic: str, agent: str) -> None:
        """
           Constructor function for the Log Class

        :param str topic: Topic driving the relevant converstaion.
        :param str agent: Name of the agent creating the object.
        """

        self.topic = topic
        self.agent = agent
        self.topic_callback = KeySearch.search_for_value("TOPIC_CALLBACK")
        self.topic_gen = KeySearch.search_for_value("TOPIC_GEN")
        raw_verbose = KeySearch.search_for_value("VB", 1)
        try:
            self.verbose = int(raw_verbose)
        except (TypeError, ValueError):
            self.verbose = 1
        self.kafka_ip = KeySearch.search_for_value("KAFKA_IP")
        if not isinstance(self.topic_callback, str) or not isinstance(self.topic_gen, str) or not isinstance(self.kafka_ip, str):
            raise RuntimeError("Kafka configuration is incomplete. Expected TOPIC_CALLBACK, TOPIC_GEN, and KAFKA_IP.")

        self.iter_no_msg = 0
        self.min_verbose = 1
        # Only parent (manager) agents set a DockerManager here; replicas keep it as None
        self.handler: Any = None
        self.reaper_interval = _reaper_interval()
        self._next_reap = time.monotonic() + self.reaper_interval
        self.action_methods = {
            'PING': self.handle_ping_action, 'EXIT': self.handle_exit_action
        }

        # Each agent must be in an independent consumer group so
        # the message consumed by one AGENT can also be consumed by other AGENTs
        self.producer = Producer({"bootstrap.servers": self.kafka_ip})
        self.consumer = Consumer(
            {
                "bootstrap.servers": self.kafka_ip,
                "group.id": self.agent,
                "auto.offset.reset": "earliest",
                'error_cb': cast(Any, self.kafka_error_callback)
            }
        )
        self.consumer.subscribe([self.topic], on_assign=on_assign, on_revoke=on_revoke)

    def enqueue_replica(self, **kwargs) -> None:
        """Prepare on the consumer thread; only Docker I/O runs concurrently.

        The outstanding queue is bounded. Errors are collected on the consumer
        thread, where Kafka reporting and agent state remain serialized.
        """
        if not hasattr(self, "_launch_executor"):
            per_worker = int(os.getenv("DYNREACT_LAUNCHES_PER_WORKER", "2"))
            if per_worker < 1:
                raise ValueError("DYNREACT_LAUNCHES_PER_WORKER must be positive")
            workers = per_worker * max(1, len(self.handler.remote_workers))
            # Local Docker keeps its previous serial behavior by default.
            if not self.handler.remote_workers:
                workers = 1
            self._launch_executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="replica")
            self._launch_futures = []
            self._launch_queue_limit = 2 * workers
        self.collect_launches()
        if len(self._launch_futures) >= self._launch_queue_limit:
            self.collect_launches(wait_one=True)
        # Capture configuration before the next CREATE mutates KeySearch.
        kwargs = deepcopy(kwargs)
        envs = dict(kwargs.get("envs") or {})
        for key in ("KAFKA_TOPIC_PREFIX", "TOPIC_GEN", "TOPIC_CALLBACK"):
            envs[key] = KeySearch.search_for_value(key)
        kwargs["envs"] = envs
        future = self._launch_executor.submit(self.handler.launch_container, **kwargs)
        self._launch_futures.append((future, kwargs["params"]["topic"], kwargs["name"]))

    def collect_launches(self, wait_one=False) -> None:
        pending = getattr(self, "_launch_futures", [])
        if wait_one and pending:
            from concurrent.futures import wait, FIRST_COMPLETED
            wait([item[0] for item in pending], return_when=FIRST_COMPLETED)
        remaining = []
        for future, topic, name in pending:
            if not future.done():
                remaining.append((future, topic, name))
                continue
            try:
                if future.result() is None:
                    raise RuntimeError("Container limit reached")
            except Exception as exc:
                message = f"Failed to launch {name}: {exc}"
                print(message)
                sendmsgtopic(producer=self.producer, tsend=topic, topic=topic,
                             source=self.agent, dest="LOG:" + topic,
                             action="RECIEVEERROR", payload=dict(msg=message), vb=self.verbose)
        self._launch_futures = remaining

    def reap_if_due(self) -> None:
        """Sweeps the containers of this parent agent when the reaper interval has elapsed.

        Only parent agents own a ``DockerManager``; for replicas this is a no-op. The sweep
        removes exited replicas, stuck replicas and replicas of auctions whose Kafka topic no
        longer exists. It never raises, so a Docker or Kafka failure cannot stop the agent.
        """
        if getattr(self, "_launch_futures", []) or self.handler is None or time.monotonic() < self._next_reap:
            return
        self._next_reap = time.monotonic() + self.reaper_interval
        try:
            removed = self.handler.reap(existing_topics=list_existing_topics(self.kafka_ip))
            if any(removed.values()):
                # Leave a trace in the LOG, so the removal of containers can be audited
                self.write_log(
                    f"Reaper of {self.agent} removed {sum(removed.values())} containers {removed}: "
                    f"{', '.join(self.handler.last_reaped)}",
                    "0b6d3c1e-5f7a-4c58-9a52-3d6a8f1e7c42",
                    to_stdout=True
                )
        except Exception as e:
            print(f"Reaper sweep failed: {e}")

    def write_log(self, msg: str, identifier: str, to_stdout: bool = False) -> None:
        """
        Write the given message in the topic's LOG

        :param str msg: Message sent by the agent
        :param str identifier: Unique Identifier for traceability
        :param str to_stdout: Print message also to console
        """

        if to_stdout:
            print(msg)

        sendmsgtopic(
            producer=self.producer, tsend=self.topic, topic=self.topic, source=self.agent,
            dest="LOG:" + self.topic, action="WRITE", payload=dict(msg=msg, identifier=identifier), vb=self.verbose
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

    def handle_exit_action(self, dctmsg: dict | None = None) -> str:
        """
        Handles the EXIT action.

        :param dict dctmsg: Message dictionary

        :returns: Status of the handling
        :rtype:  str
        """
        payload = dctmsg or {}
        exit_source = payload.get("source", self.agent)
        exit_dest = payload.get("dest", self.agent)
        exit_topic = payload.get("topic", self.topic)
        exit_msg = (
            f"Received EXIT from {exit_source} to {exit_dest} on topic {exit_topic}. "
            "Ending agent loop."
        )
        print(exit_msg)
        if self.verbose > 0:
            self.write_log(
                exit_msg,
                "2eea5d7b-2539-4c3b-8dfb-d4ed8ece26b0",
                to_stdout=True
            )
        return 'END'

    def should_purge_exit_history(self) -> bool:
        """
        Return whether processing ``EXIT`` should purge stale messages.

        Purging too early from EQUIPMENT or MATERIAL can delete the pending
        ``EXIT`` intended for sibling base agents. The safe point is the
        general LOG shutdown, which clean_agents() already sends last.
        """
        return self.topic == self.topic_gen and str(self.agent).startswith("LOG:")

    def purge_exit_history_if_needed(self) -> None:
        """Purge stale general and callback messages when the shutdown point is safe."""
        if not self.should_purge_exit_history():
            return
        purge_topics(topics=[self.topic, self.topic_callback])

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
                self.write_log("Program stopped by user", "93df3b98-63e4-4fdf-ac31-49487666e32a")
                raise KeyboardInterrupt
            except Exception as e:
                error_message = traceback.format_exc()
                print("Captured error message:")
                print(error_message)  # Prints the traceback as a string
                self.write_log(f"ERROR: Raised error {type(e)} with message {e}", "1f5b666a-0ee6-4309-b8ea-71c744eb8065")
                sendmsgtopic(
                    producer=self.producer,
                    tsend=self.topic,
                    topic=self.topic,
                    source=self.agent,
                    dest="LOG:" + self.topic,
                    action="RECIEVEERROR",
                    payload=dict(msg=f"ERROR: Raised error {type(e)} with message {error_message}"),
                    vb=self.verbose
                )
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

    def callback_on_topic_not_available(self, topic: str | None = None) -> None:
        """
        Function executed when 'Subscribed topic not available'
        
        """

    def callback_on_not_match(self, dctmsg: dict) -> None:
        """
        Function executed when the agent is not the destination of the message
        
        """
        pass

    def kafka_error_callback(self, err: KafkaError) -> None:
        """Kafka error callback.
        
        This function is part of the short-term planning workflow and keeps
        the existing runtime behavior while documenting the public contract.
        
        Args:
            err: Input value for the `err` parameter.
        
        Returns:
            The value produced by the underlying planning, UI, or test helper logic.
        """
        error_code = err.code() if hasattr(err, "code") else None
        if error_code in UNKNOWN_TOPIC_ERRORS:
            print("WARNING: Topic or partition is temporarily unavailable", err)
            return
        print("WARNING: Kafka consumer callback reported an error", err)

    def read_message(self) -> str:
        """
        Poll and read a Kafka message

        :returns: Status after reading the message
        :rtype:  str
        """
        self.iter_no_msg += 1

        self.collect_launches()
        self.reap_if_due()
        status = self.callback_before_message()
        if status != 'CONTINUE':
            return status

        # Get a message
        message_obj = self.consumer.poll(timeout=1)

        # If there is no message, go to the next iteration
        if message_obj is None:
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
            error_obj = message_obj.error()
            # End of partition event
            if self.verbose > 1:
                self.write_log("Error encountered.", "41e40c2f-f4fb-4903-aa32-1931e8fb0d40")
            sys.stderr.write('%% %s [%d] reached end at offset %d with code %s\n' %
                             (message_obj.topic(), message_obj.partition(),
                              message_obj.offset(), error_obj.code() if error_obj is not None else "unknown"))

        # If the destinations of the message do not include this AGENT, go to the next iteration
        if vals is None:
            return 'CONTINUE'
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
                f"offset {offst} and key {key}",
                "9a1a3eb2-dbb6-42cb-b2f2-05c53a982ff9"
            )

        # Perform the action and get the corresponding status
        action = dctmsg['action'].upper()
        if self.verbose > self.min_verbose:
            self.write_log(f"Performing action {action}...", "91a4b9b6-8ed0-4fce-b5c2-196e764280af")
        status = self.process_message(action=action, dctmsg=dctmsg)
        if self.verbose > self.min_verbose:
            self.write_log(f"Resulting status: {status}", "b3d9c000-ed40-4cfd-a5f6-57a3d980c184")

        return status

    def follow_topic(self) -> None:
        """
        Loop in which an AGENT follows the general topic or an auction's topic.
        The AGENT can act both as a producer and a consumer.

        """

        if self.verbose > 1:
            self.write_log(f"Spawned a process for agent {self.agent} to follow topic {self.topic}.", "affc0902-8218-4dd1-9df7-8bfed516c57c")

        status = 'GO'
        try:
            while status != 'END':
                status = self.read_message()
        finally:
            if hasattr(self, "_launch_executor"):
                self._launch_executor.shutdown(wait=True, cancel_futures=True)
                self.collect_launches()
            self.consumer.close()

        # We close the consumer to release any equipment it is using
        # The producer does not need to be closed, since it is automatically garbage collected:
        # https://github.com/confluentinc/confluent-kafka-python/issues/127
        print(f"Closing consumer received status {status}")
        if self.verbose > 1:
            self.write_log(f"Ending spawned process for agent {self.agent} in topic {self.topic}.", "8dc03f6b-dce4-4a52-a427-900547dd7a5a")
        # Purge only after the general LOG has fully shut down so late EXIT
        # traces from sibling base agents do not survive into the next startup.
        self.purge_exit_history_if_needed()
