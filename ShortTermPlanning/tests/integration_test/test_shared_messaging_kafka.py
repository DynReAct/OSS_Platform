"""Broker-level concurrency checks, enabled explicitly by Jenkins or a local operator.

Only UUID-named topics created by this module are removed. No parent containers,
production topics, external REST services or registry operations are used.
"""
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from confluent_kafka import KafkaException, Producer
from confluent_kafka.admin import AdminClient, NewTopic

from dynreact.shortterm import common
from dynreact.shortterm import short_term_planning as planning
from dynreact.shortterm.agents.log import Log
from dynreact.shortterm.shorttermtargets import ShortTermTargets

pytestmark = pytest.mark.skipif(os.environ.get("MESSAGING_TEST_KAFKA") != "1", reason="explicit isolated Kafka verification only")


@pytest.fixture
def broker_context(monkeypatch):
    kafka_ip = os.environ["KAFKA_IP"]
    prefix = f"DynReact-MESSAGING-TEST-{uuid4().hex}"
    topics = [f"{prefix}-{suffix}" for suffix in ("Gen", "Callback", "A", "B")]
    previous = common.KeySearch._global_config
    for key, value in dict(KAFKA_IP=kafka_ip, TOPIC_GEN=topics[0], TOPIC_CALLBACK=topics[1], KAFKA_TOPIC_PREFIX=prefix).items():
        monkeypatch.setenv(key, value)
    common.KeySearch.set_global(ShortTermTargets(KAFKA_IP=kafka_ip, TOPIC_GEN=topics[0], TOPIC_CALLBACK=topics[1], KAFKA_TOPIC_PREFIX=prefix, VB=0))
    admin = AdminClient({"bootstrap.servers": kafka_ip})
    try:
        for future in admin.create_topics([NewTopic(topic, 1, 1) for topic in topics]).values():
            future.result(timeout=20)
        yield SimpleNamespace(kafka_ip=kafka_ip, topics=topics, admin=admin, prefix=prefix)
    finally:
        # This list is generated locally and cannot include someone else's topics.
        for future in admin.delete_topics(topics).values():
            future.result(timeout=20)
        common.KeySearch._global_config = previous


def test_two_readers_receive_only_their_own_replies_without_deleting_history(broker_context):
    ctx = broker_context
    general, callback, auction_a, auction_b = ctx.topics
    producer = Producer({"bootstrap.servers": ctx.kafka_ip})
    def reply(topic, request_id):
        log = Log.__new__(Log)
        log.producer = producer; log.topic = topic; log.agent = f"LOG:{topic}"
        log.topic_callback = callback; log.results = {topic: []}; log.verbose = 0; log.auction_completed = False
        Log.handle_askresults_action(log, dict(topic=topic, source="UX", request_id=request_id))
    reply(auction_a, "historical")
    readers = [common.create_callback_consumer(ctx.kafka_ip, callback) for _ in range(2)]
    try:
        # Pending parent commands survive creation/use/shutdown of another reader.
        common.sendmsgtopic(producer, general, auction_a, "UX", f"MATERIAL:{general}", "CREATE")
        with pytest.raises(ValueError):
            common.purge_topics([general, callback])
        reply(auction_b, "request-B")
        reply(auction_a, "delayed-other-request")
        reply(auction_a, "request-A")
        first = list(planning.wait_for_callback(callback, "RESULTS", readers[0], 0, max_iters=3,
                     expected_source=f"LOG:{auction_a}", expected_request_id="request-A"))
        second = list(planning.wait_for_callback(callback, "RESULTS", readers[1], 0, max_iters=3,
                      expected_source=f"LOG:{auction_b}", expected_request_id="request-B"))
        assert [m["payload"] for m in first] == [{auction_a: []}]
        assert [m["payload"] for m in second] == [{auction_b: []}]
        from confluent_kafka import TopicPartition
        low, high = readers[0].get_watermark_offsets(TopicPartition(general, 0), timeout=10, cached=False)
        assert (low, high) == (0, 1)
    finally:
        for reader in readers:
            reader.close()


def test_duplicate_topic_reservation_cannot_publish_another_auctions_creates(broker_context):
    ctx = broker_context
    producer = Producer({"bootstrap.servers": ctx.kafka_ip})
    # Force the advisory existence check to miss; the broker's atomic reservation
    # must still win the race and reject the second creator before any CREATE.
    with patch.object(planning, "DataSetup"), patch.object(planning, "topic_exist", return_value=False), patch.object(planning, "sendmsgtopic") as sent:
        with pytest.raises(KafkaException):
            planning.create_auction([], producer, 0, act="A", materials=[], admin_client=ctx.admin)
    sent.assert_not_called()
