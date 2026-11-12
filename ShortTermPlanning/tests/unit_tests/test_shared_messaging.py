"""Concurrency regressions for shared parent channels; no broker or Docker needed."""
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from confluent_kafka import KafkaError, KafkaException

from dynreact.shortterm import common
from dynreact.shortterm import short_term_planning as planning
from dynreact.shortterm.agents import agent as agents
from dynreact.shortterm.agents import log as logs
from dynreact.shortterm.common.data.data_functions import cleanup_auction, end_auction


@pytest.fixture(autouse=True)
def isolate_runtime_environment(monkeypatch):
    """Image defaults must not override the deterministic unit-test context."""
    for key in ("TOPIC_GEN", "TOPIC_CALLBACK", "KAFKA_TOPIC_PREFIX", "KAFKA_IP", "VB"):
        monkeypatch.delenv(key, raising=False)


def record(source="LOG:auction-A", request_id="request-A", **overrides):
    envelope = dict(source=source, request_id=request_id, dest="UX", action="RESULTS", payload={"7": []})
    envelope.update(overrides)
    msg = MagicMock()
    msg.topic.return_value = "dynCB"
    msg.error.return_value = None
    msg.value.return_value = json.dumps(envelope).encode()
    return msg


@pytest.mark.parametrize("operation", [common.purge_topics, common.delete_topics])
def test_shared_deletion_rejects_whole_batch_before_broker_access(operation):
    with patch.object(common, "AdminClient") as admin, pytest.raises(ValueError, match="shared"):
        operation(["auction-A", "dynGEN", "dynCB"])
    admin.assert_not_called()


def test_offline_purge_requires_explicit_override():
    with patch.object(common, "AdminClient") as admin:
        admin.return_value.list_topics.return_value.topics = {
            "dynGEN": SimpleNamespace(partitions={0: None}),
            "dynCB": SimpleNamespace(partitions={0: None}),
        }
        admin.return_value.delete_records.return_value = {}
        common.purge_topics(["dynGEN", "dynCB"], allow_shared=True)
    admin.return_value.delete_records.assert_called_once()


@pytest.mark.parametrize("operation", [cleanup_auction, end_auction])
def test_shared_topic_cannot_be_used_as_an_auction(operation):
    kwargs = {"kafka_ip": "unused"} if operation == cleanup_auction else dict(producer=MagicMock(), verbose=0, wait_time=0)
    with patch.object(common, "AdminClient") as admin, pytest.raises(ValueError, match="shared"):
        operation("dynGEN", **kwargs)
    admin.assert_not_called()


def test_bulk_cleanup_is_disabled_during_normal_operation():
    admin = MagicMock()
    with pytest.raises(ValueError, match="offline=True"):
        planning.delete_all_topics(admin, 0)
    admin.list_topics.assert_not_called()


def test_offline_bulk_cleanup_preserves_shared_topics():
    admin = MagicMock()
    admin.list_topics.return_value.topics = {"dynGEN": None, "dynCB": None, "dynAuction-A": None}
    planning.delete_all_topics(admin, 0, offline=True)
    admin.delete_topics.assert_called_once_with(["dynAuction-A"])


def test_independent_callback_readers_start_at_fixed_offsets_before_requests():
    readers = [MagicMock(), MagicMock()]
    for reader in readers:
        reader.list_topics.return_value.topics = {"dynCB": SimpleNamespace(error=None, partitions={0: None, 1: None})}
        reader.get_watermark_offsets.side_effect = [(0, 12), (0, 25)]
    with patch.object(common, "AdminClient"), patch.object(common, "Consumer", side_effect=readers) as factory:
        assert common.create_callback_consumer("broker", "dynCB") is readers[0]
        assert common.create_callback_consumer("broker", "dynCB") is readers[1]
    assert factory.call_args_list[0].args[0]["group.id"] != factory.call_args_list[1].args[0]["group.id"]
    for reader in readers:
        positions = reader.assign.call_args.args[0]
        assert [(tp.topic, tp.partition, tp.offset) for tp in positions] == [("dynCB", 0, 12), ("dynCB", 1, 25)]
        reader.subscribe.assert_not_called()


def test_callback_reader_closes_if_metadata_fails():
    with patch.object(common, "AdminClient"), patch.object(common, "Consumer") as factory:
        factory.return_value.list_topics.side_effect = RuntimeError("broker unavailable")
        with pytest.raises(RuntimeError):
            common.create_callback_consumer("broker", "dynCB")
    factory.return_value.close.assert_called_once()


def test_existing_callback_topic_does_not_get_reconfigured():
    with patch.object(common, "AdminClient") as admin, patch.object(common, "Consumer") as factory:
        admin.return_value.create_topics.return_value["dynCB"].result.side_effect = KafkaException(KafkaError(KafkaError.TOPIC_ALREADY_EXISTS))
        factory.return_value.list_topics.return_value.topics = {"dynCB": SimpleNamespace(error=None, partitions={0: None})}
        factory.return_value.get_watermark_offsets.return_value = (0, 10)
        assert common.create_callback_consumer("broker", "dynCB") is factory.return_value


def test_interleaved_callbacks_accept_only_the_current_request():
    consumer = MagicMock()
    bad = record(); bad.value.return_value = b"not JSON"
    consumer.poll.side_effect = [record(source="LOG:auction-B"), record(request_id="old-request"),
                                 record(dest=".*"), bad, record()]
    with patch.object(planning.time, "monotonic", side_effect=[0, 1, 2, 3, 4, 5, 11]):
        replies = list(planning.wait_for_callback("dynCB", "RESULTS", consumer, 0,
                       expected_source="LOG:auction-A", expected_request_id="request-A"))
    assert len(replies) == 1 and replies[0]["request_id"] == "request-A"
    consumer.commit.assert_not_called()


def test_unrelated_callback_traffic_cannot_extend_the_deadline():
    consumer = MagicMock()
    consumer.poll.return_value = record(source="LOG:auction-B")
    with patch.object(planning.time, "monotonic", side_effect=[0, 1, 2, 3]):
        assert list(planning.wait_for_callback("dynCB", "RESULTS", consumer, 0, max_iters=3,
                    expected_source="LOG:auction-A")) == []
    assert consumer.poll.call_count == 2


@pytest.mark.parametrize("method, action", [("handle_is_auction_started_action", "AUCTIONSTARTED"), ("handle_askresults_action", "RESULTS")])
def test_log_echoes_request_id_without_changing_callback_payload(method, action):
    log = logs.Log.__new__(logs.Log)
    log.topic = "auction-A"; log.topic_callback = "dynCB"; log.agent = "LOG:auction-A"
    log.producer = MagicMock(); log.verbose = 0; log.results = {"7": []}
    log.total_num_agents = 0; log.auction_start = False; log.present_agents = set()
    log.auction_completed = False; log.write_log = MagicMock()
    with patch.object(logs, "sendmsgtopic") as sent:
        getattr(log, method)({"topic": "auction-A", "source": "UX", "request_id": "request-A"})
    assert sent.call_args.kwargs["request_id"] == "request-A"
    assert sent.call_args.kwargs["action"] == action


@pytest.fixture
def parent():
    with patch.object(agents, "Producer"), patch.object(agents, "Consumer"):
        parent = agents.Agent("dynGEN", "MATERIAL:dynGEN")
        parent._startup_offsets = {("dynGEN", 0): 10}
        return parent


def parent_message(action="CREATE", topic="auction-A"):
    msg = record(dest="MATERIAL:dynGEN", action=action, topic=topic,
                 payload={"variables": {"TOPIC_GEN": "dynGEN", "TOPIC_CALLBACK": "dynCB"}})
    msg.topic.return_value = "dynGEN"
    msg.partition.return_value = 0
    msg.offset.return_value = 5
    return msg


def test_parent_does_not_discard_old_create_for_a_still_existing_auction(parent):
    msg = parent_message()
    parent.consumer.poll.return_value = msg
    handler = MagicMock(return_value="CONTINUE"); parent.action_methods["CREATE"] = handler
    with patch.object(agents, "list_existing_topics", return_value={"auction-A", "auction-B"}):
        assert parent.read_message() == "CONTINUE"
    handler.assert_called_once()
    parent.consumer.commit.assert_called_once_with(msg, asynchronous=False)


def test_parent_skips_abandoned_create_without_affecting_other_auctions(parent):
    msg = parent_message(); parent.consumer.poll.return_value = msg
    handler = MagicMock(); parent.action_methods["CREATE"] = handler
    with patch.object(agents, "list_existing_topics", return_value={"auction-B"}):
        parent.read_message()
    handler.assert_not_called()
    parent.consumer.commit.assert_called_once_with(msg, asynchronous=False)


def test_unknown_metadata_retries_without_acknowledging_create(parent):
    msg = parent_message(); parent.consumer.poll.return_value = msg
    handler = MagicMock(); parent.action_methods["CREATE"] = handler
    with patch.object(agents, "list_existing_topics", return_value=None), patch.object(agents.time, "sleep"):
        parent.read_message()
    handler.assert_not_called(); parent.consumer.commit.assert_not_called(); parent.consumer.seek.assert_called_once()


def test_foreign_context_cannot_reconfigure_a_parent(parent):
    msg = parent_message(); payload = json.loads(msg.value()); payload["payload"]["variables"]["TOPIC_GEN"] = "another-GEN"
    msg.value.return_value = json.dumps(payload).encode(); parent.consumer.poll.return_value = msg
    handler = MagicMock(); parent.action_methods["CREATE"] = handler
    parent.read_message()
    handler.assert_not_called()


def test_historical_exit_does_not_kill_restarted_parent(parent):
    msg = parent_message(action="EXIT", topic="dynGEN"); parent.consumer.poll.return_value = msg
    assert parent.read_message() == "CONTINUE"
    parent.consumer.commit.assert_called_once_with(msg, asynchronous=False)


def test_current_exit_is_persisted_before_the_parent_closes(parent):
    msg = parent_message(action="EXIT", topic="dynGEN")
    msg.offset.return_value = 11
    parent.consumer.poll.return_value = msg
    with patch.object(parent, "write_log"):
        assert parent.read_message() == "END"
    parent.consumer.commit.assert_called_once_with(msg, asynchronous=False)


def test_topic_reservation_failure_publishes_no_create():
    producer = MagicMock(); admin = MagicMock()
    with patch.object(planning, "DataSetup"), patch.object(planning, "topic_exist", return_value=False), patch.object(planning, "sendmsgtopic") as sent:
        admin.create_topics.return_value["Dynreact_OSS-A"].result.side_effect = RuntimeError("topic already reserved")
        with pytest.raises(RuntimeError, match="reserved"):
            planning.create_auction([], producer, 0, act="A", materials=[], admin_client=admin)
    sent.assert_not_called()


def test_rebalance_keeps_initial_exit_boundary_without_skipping_pending_creates(parent):
    from confluent_kafka import TopicPartition
    parent._startup_offsets = {}
    parent.consumer.get_watermark_offsets.side_effect = [(0, 10), (0, 999)]
    partitions = [TopicPartition("dynGEN", 0)]
    parent.assign_partitions(parent.consumer, partitions)
    parent.assign_partitions(parent.consumer, partitions)
    assert parent._startup_offsets == {("dynGEN", 0): 10}
    parent.consumer.get_watermark_offsets.assert_called_once()
    assert parent.consumer.assign.call_count == 2


def test_purging_absent_private_scratch_topic_is_a_noop():
    with patch.object(common, "AdminClient") as admin:
        admin.return_value.list_topics.return_value.topics = {}
        common.purge_topics(["DYN_TEST"])
    admin.return_value.delete_records.assert_not_called()


def test_parent_shutdown_drains_accepted_launches_instead_of_cancelling_them(parent):
    parent._launch_executor = MagicMock()
    parent.read_message = MagicMock(return_value="END")
    parent.collect_launches = MagicMock()
    parent.follow_topic()
    parent._launch_executor.shutdown.assert_called_once_with(wait=True, cancel_futures=False)
    parent.collect_launches.assert_called_once()
    parent.consumer.close.assert_called_once()


@pytest.mark.parametrize("body", [None, [], {"variables": []}])
def test_malformed_create_cannot_stop_a_shared_parent(parent, body):
    msg = parent_message()
    envelope = json.loads(msg.value()); envelope["payload"] = body
    msg.value.return_value = json.dumps(envelope).encode(); parent.consumer.poll.return_value = msg
    handler = MagicMock(); parent.action_methods["CREATE"] = handler
    assert parent.read_message() == "CONTINUE"
    handler.assert_not_called()
    parent.consumer.commit.assert_called_once_with(msg, asynchronous=False)
