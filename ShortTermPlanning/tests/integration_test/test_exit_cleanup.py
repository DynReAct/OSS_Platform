"""Offline regression: shutting down a parent must preserve concurrent auction traffic."""
from unittest.mock import MagicMock, patch

import pytest

from dynreact.shortterm.agents.agent import Agent


@pytest.mark.parametrize("kind", ["LOG", "EQUIPMENT", "MATERIAL"])
def test_parent_shutdown_preserves_general_and_callback_history(kind):
    agent = Agent.__new__(Agent)
    agent.agent = f"{kind}:Dynreact-RAS-TEST-Gen"
    agent.topic = agent.topic_gen = "Dynreact-RAS-TEST-Gen"
    agent.topic_callback = "Dynreact-RAS-TEST-Callback"
    agent.verbose = 2
    agent.consumer = MagicMock()
    agent.write_log = MagicMock()
    agent.read_message = MagicMock(return_value="END")
    with patch("dynreact.shortterm.common.AdminClient") as admin:
        agent.follow_topic()
        agent.purge_exit_history_if_needed()
    agent.consumer.close.assert_called_once()
    admin.assert_not_called()
    assert agent.should_purge_exit_history() is False
