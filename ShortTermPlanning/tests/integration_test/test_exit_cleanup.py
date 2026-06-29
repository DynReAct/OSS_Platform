from unittest.mock import MagicMock, patch

from dynreact.shortterm.agents.agent import Agent
from dynreact.shortterm.agents.log import Log


def test_general_log_follow_topic_purges_general_and_callback_topics_on_shutdown() -> None:
    agent = Log.__new__(Log)
    agent.agent = "LOG:Dynreact-RAS-TEST-Gen"
    agent.topic = "Dynreact-RAS-TEST-Gen"
    agent.topic_gen = "Dynreact-RAS-TEST-Gen"
    agent.topic_callback = "Dynreact-RAS-TEST-Callback"
    agent.verbose = 2
    agent.consumer = MagicMock()
    agent.write_log = MagicMock()
    agent.read_message = MagicMock(return_value="END")

    with patch("dynreact.shortterm.agents.agent.purge_topics") as purge_topics_mock:
        agent.follow_topic()

    agent.consumer.close.assert_called_once()
    agent.write_log.assert_called()
    purge_topics_mock.assert_called_once_with(
        topics=["Dynreact-RAS-TEST-Gen", "Dynreact-RAS-TEST-Callback"]
    )


def test_non_log_exit_does_not_purge_topics() -> None:
    agent = Agent.__new__(Agent)
    agent.agent = "EQUIPMENT:Dynreact-RAS-TEST-Gen"
    agent.topic = "Dynreact-RAS-TEST-Gen"
    agent.topic_gen = "Dynreact-RAS-TEST-Gen"
    agent.topic_callback = "Dynreact-RAS-TEST-Callback"

    with patch("dynreact.shortterm.agents.agent.purge_topics") as purge_topics_mock:
        status = Agent.handle_exit_action(agent)

    assert status == "END"
    purge_topics_mock.assert_not_called()
