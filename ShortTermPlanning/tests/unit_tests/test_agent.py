"""Unit tests for the generic :class:`dynreact.shortterm.agents.agent.Agent` message loop.

The base agent is shared by LOG, EQUIPMENT and MATERIAL, so these tests protect the behaviour
all of them rely on: routing of messages by destination, dispatch of actions, survival of a
failing handler, and the end of the loop. Kafka is replaced by mocks.
"""
import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dynreact.shortterm.agents import agent as agent_module
from dynreact.shortterm.agents.agent import Agent, _reaper_interval
from dynreact.shortterm.common import KeySearch

TOPIC = "dynTEST"


@pytest.fixture
def agent() -> Agent:
    with patch.object(agent_module, "Producer"), patch.object(agent_module, "Consumer"):
        return Agent(topic=TOPIC, agent=f"MATERIAL:{TOPIC}:7")


def _message(dest: str, action: str, topic: str = TOPIC) -> MagicMock:
    """A Kafka message carrying the given destination regex and action."""
    message = MagicMock()
    message.topic.return_value = topic
    message.error.return_value = None
    message.value.return_value = json.dumps(
        {"source": "UX", "dest": dest, "topic": topic, "action": action, "payload": {}}).encode()
    return message


def test_a_new_agent_has_no_docker_manager(agent: Agent) -> None:
    assert agent.handler is None


def test_ping_is_answered_to_the_pinging_agent(agent: Agent) -> None:
    with patch.object(agent_module, "sendmsgtopic") as sent:
        assert agent.handle_ping_action({"topic": TOPIC, "source": f"LOG:{TOPIC}"}) == "CONTINUE"
    assert sent.call_args.kwargs["action"] == "PINGANSWER" and sent.call_args.kwargs["dest"] == f"LOG:{TOPIC}"


def test_exit_ends_the_loop(agent: Agent) -> None:
    assert agent.handle_exit_action({"source": "UX", "dest": agent.agent, "topic": TOPIC}) == "END"


def test_unknown_actions_are_reported_not_raised(agent: Agent) -> None:
    assert agent.process_message("NOPE", {}) == "UNKNOWN-ACTION"


def test_a_failing_handler_reports_the_error_and_keeps_the_agent_alive(agent: Agent) -> None:
    agent.action_methods["BOOM"] = MagicMock(side_effect=ValueError("bad payload"))
    with patch.object(agent_module, "sendmsgtopic") as sent:
        assert agent.process_message("BOOM", {}) == "ERROR"
    actions = [call.kwargs["action"] for call in sent.call_args_list]
    assert "RECIEVEERROR" in actions            # the LOG of the auction is told about it


def test_messages_are_dispatched_only_to_matching_destinations(agent: Agent) -> None:
    handler = MagicMock(return_value="CONTINUE")
    agent.action_methods["HELLO"] = handler
    agent.consumer.poll.return_value = _message(f"EQUIPMENT:{TOPIC}:.*", "HELLO")   # not for a material
    assert agent.read_message() == "CONTINUE"
    handler.assert_not_called()
    agent.consumer.poll.return_value = _message(f"MATERIAL:{TOPIC}:.*", "HELLO")    # regex covering this agent
    assert agent.read_message() == "CONTINUE"
    handler.assert_called_once()


def test_messages_of_another_topic_are_ignored(agent: Agent) -> None:
    handler = MagicMock(return_value="CONTINUE")
    agent.action_methods["HELLO"] = handler
    agent.consumer.poll.return_value = _message(".*", "HELLO", topic="dynOTHER")
    assert agent.read_message() == "CONTINUE"
    handler.assert_not_called()


def test_the_loop_ends_with_the_end_status_and_closes_the_consumer(agent: Agent) -> None:
    agent.consumer.poll.return_value = _message(".*", "EXIT")
    with patch.object(agent_module, "sendmsgtopic"), patch.object(agent, "purge_exit_history_if_needed"):
        agent.follow_topic()
    agent.consumer.close.assert_called_once()


def test_an_empty_poll_continues_the_loop(agent: Agent) -> None:
    agent.consumer.poll.return_value = None
    with patch.object(agent_module.time, "sleep"):
        assert agent.read_message() == "CONTINUE"


@pytest.mark.parametrize("raw, expected", [
    (None, agent_module.REAPER_INTERVAL), ("", agent_module.REAPER_INTERVAL), ("abc", agent_module.REAPER_INTERVAL),
    ("15", 15.0), ("0", float("inf")), ("-5", float("inf")),
])
def test_reaper_interval_from_the_environment(monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: float) -> None:
    if raw is None:
        monkeypatch.delenv("DYNREACT_REAPER_INTERVAL", raising=False)
    else:
        monkeypatch.setenv("DYNREACT_REAPER_INTERVAL", raw)
    assert _reaper_interval() == expected


def test_replicas_never_sweep(agent: Agent) -> None:
    agent._next_reap = 0.0
    with patch.object(agent_module, "list_existing_topics") as topics:
        agent.reap_if_due()
    topics.assert_not_called()


def test_launch_queue_captures_parameters_and_reports_background_failure(agent):
    import threading
    agent.handler = MagicMock(remote_workers=['ssh://oss@one'])
    release = threading.Event()
    received = []
    def launch(**kwargs):
        assert release.wait(timeout=3)
        received.append(kwargs['params']['variables']['value'])
        raise RuntimeError('Docker unavailable')
    agent.handler.launch_container.side_effect = launch
    params = {'topic': 'auction-A', 'variables': {'value': 'original'}}
    try:
        agent.enqueue_replica(name='child', params=params)
        params['variables']['value'] = 'changed'
        release.set()
        agent._launch_executor.shutdown(wait=True)
        with patch.object(agent_module, 'sendmsgtopic') as sent:
            agent.collect_launches()
        assert received == ['original']
        assert sent.call_args.kwargs['topic'] == 'auction-A'
        assert sent.call_args.kwargs['action'] == 'RECIEVEERROR'
        assert 'Docker unavailable' in sent.call_args.kwargs['payload']['msg']
        assert agent._launch_futures == []
    finally:
        release.set()
        agent._launch_executor.shutdown(wait=True)
