"""Unit tests for the container reaper, the launch bookkeeping and the Kafka cleanup of an auction.

Docker and Kafka are replaced by mocks, so the tests need neither a daemon nor a broker.
"""
import time
from unittest.mock import MagicMock, patch

import pytest

from dynreact.shortterm.common import handler as handler_module
from dynreact.shortterm.common.data.data_functions import cleanup_auction
from dynreact.shortterm.common.handler import DockerManager, LABEL_CREATED, LABEL_TOPIC


def _container(name: str, status: str, topic: str | None, age: float, finished_ago: float | None = None) -> MagicMock:
    """Builds a fake Docker container created ``age`` seconds ago."""
    container = MagicMock()
    container.name = name
    container.status = status
    labels = {LABEL_CREATED: str(int(time.time() - age))}
    if topic:
        labels[LABEL_TOPIC] = topic
    container.labels = labels
    finished = "0001-01-01T00:00:00Z"
    if finished_ago is not None:
        finished = time.strftime("%Y-%m-%dT%H:%M:%S.123456789Z", time.gmtime(time.time() - finished_ago))
    container.attrs = {"Config": {"Labels": labels}, "Created": "2020-01-01T00:00:00Z",
                       "State": {"FinishedAt": finished, "ExitCode": 0}}
    return container


@pytest.fixture
def manager() -> DockerManager:
    with patch.object(handler_module.docker, "from_env", return_value=MagicMock()):
        return DockerManager(tag="material_replica")


def test_reap_applies_each_rule(manager: DockerManager) -> None:
    exited_old = _container("a", "exited", "T1", 500, finished_ago=500)
    exited_new = _container("b", "exited", "T1", 500, finished_ago=1)
    stuck = _container("c", "running", "T1", 50000)
    orphan = _container("d", "running", "GONE", 1000)
    young_orphan = _container("e", "running", "GONE", 10)
    live = _container("f", "running", "T1", 1000)
    manager.client.containers.list.return_value = [exited_old, exited_new, stuck, orphan, young_orphan, live]

    removed = manager.reap(exited_grace=60, max_age=10800, topic_grace=300, existing_topics={"T1"})

    assert removed == {"exited": 1, "stuck": 1, "orphan": 1}
    for container in (exited_old, stuck, orphan):
        container.remove.assert_called_once_with(force=True)
    for container in (exited_new, young_orphan, live):
        container.remove.assert_not_called()


def test_reap_never_kills_by_topic_when_kafka_is_unknown(manager: DockerManager) -> None:
    orphan = _container("d", "running", "GONE", 1000)
    manager.client.containers.list.return_value = [orphan]
    assert manager.reap(existing_topics=None) == {"exited": 0, "stuck": 0, "orphan": 0}
    orphan.remove.assert_not_called()


def test_reap_survives_failures(manager: DockerManager) -> None:
    broken = _container("a", "exited", "T1", 500, finished_ago=500)
    broken.remove.side_effect = RuntimeError("already gone")
    fine = _container("b", "exited", "T1", 500, finished_ago=500)
    manager.client.containers.list.return_value = [broken, fine]
    assert manager.reap(exited_grace=1)["exited"] == 1
    manager.client.containers.list.side_effect = RuntimeError("docker down")
    assert manager.reap() == {"exited": 0, "stuck": 0, "orphan": 0}


def test_launch_does_not_inspect_every_container(manager: DockerManager) -> None:
    manager.client.containers.list.return_value = []
    manager.client.containers.run.return_value = MagicMock(id="1", status="running", attrs={"State": {}})
    for i in range(20):
        manager.launch_container(name=f"t_{i}", agent="material", mode="replica", params={"topic": "T"})
    # One name lookup per launch, and no per-container inspection of the existing ones
    assert manager.client.containers.list.call_count == 20
    labels = manager.client.containers.run.call_args.kwargs["labels"]
    assert labels["owner"] == manager.tag and labels[LABEL_TOPIC] == "T" and LABEL_CREATED in labels


def test_launch_respects_max_allowed(manager: DockerManager) -> None:
    manager.max_allowed = 1
    manager.client.containers.list.return_value = [MagicMock()]
    assert manager.launch_container(name="x", agent="log", mode="base", params={}) is None
    manager.client.containers.run.assert_not_called()


def test_cleanup_auction_deletes_topic_and_matching_groups() -> None:
    admin = MagicMock()
    ok = MagicMock()
    admin.delete_topics.return_value = {"T": ok}
    groups = [MagicMock(group_id="EQUIPMENT:T:1"), MagicMock(group_id="LOG:T"), MagicMock(group_id="MATERIAL:OTHER:1")]
    admin.list_consumer_groups.return_value.result.return_value.valid = groups
    admin.delete_consumer_groups.return_value = {"EQUIPMENT:T:1": ok, "LOG:T": ok}
    with patch("dynreact.shortterm.common.data.data_functions.AdminClient", return_value=admin):
        assert cleanup_auction("T", "k:9092") == {"topics": 1, "groups": 2}
    admin.delete_consumer_groups.assert_called_once_with(["EQUIPMENT:T:1", "LOG:T"])


def test_cleanup_auction_never_raises() -> None:
    with patch("dynreact.shortterm.common.data.data_functions.AdminClient", side_effect=RuntimeError("no broker")):
        assert cleanup_auction("T", "k:9092") == {"topics": 0, "groups": 0}
    assert cleanup_auction("", "k:9092") == {"topics": 0, "groups": 0}


def test_reap_records_removed_names(manager: DockerManager) -> None:
    manager.client.containers.list.return_value = [_container("old", "exited", "T1", 500, finished_ago=500)]
    manager.reap(exited_grace=1)
    assert manager.last_reaped == ["old (exited)"]


def test_parent_agent_logs_what_the_reaper_removes() -> None:
    from dynreact.shortterm.agents.agent import Agent
    agent = Agent.__new__(Agent)
    agent.agent, agent.kafka_ip = "MATERIAL:G", "k:9092"
    agent.handler = MagicMock(last_reaped=["c1 (exited)"])
    agent.handler.reap.return_value = {"exited": 1, "stuck": 0, "orphan": 0}
    agent._next_reap, agent.reaper_interval = 0.0, 60.0
    agent.write_log = MagicMock()
    with patch("dynreact.shortterm.agents.agent.list_existing_topics", return_value={"G"}):
        agent.reap_if_due()
    assert "c1 (exited)" in agent.write_log.call_args.args[0]
    # Nothing is logged when nothing was removed, and the sweep is rate limited
    agent.write_log.reset_mock()
    agent._next_reap = 0.0
    agent.handler.reap.return_value = {"exited": 0, "stuck": 0, "orphan": 0}
    with patch("dynreact.shortterm.agents.agent.list_existing_topics", return_value=None):
        agent.reap_if_due()
        agent.reap_if_due()
    agent.write_log.assert_not_called()
    assert agent.handler.reap.call_count == 2


@pytest.mark.parametrize('mode,expected',[('replica',True),('base',False)])
def test_default_auto_remove_matches_lifecycle(manager,mode,expected):
    manager.client.containers.list.return_value=[]
    manager.launch_container(name='auto',agent='material',mode=mode,params={})
    assert manager.client.containers.run.call_args.kwargs['auto_remove'] is expected


def test_persistent_parent_cannot_be_auto_removed(manager):
    with pytest.raises(ValueError,match='Persistent base agents'):
        manager.launch_container(name='base',agent='log',mode='base',params={},auto_remove=True)
    manager.client.containers.run.assert_not_called()


def test_fast_auto_removed_child_does_not_turn_into_create_failure(manager,capsys):
    manager.client.containers.list.return_value=[]
    child=MagicMock()
    child.reload.side_effect=handler_module.docker.errors.NotFound('already removed')
    manager.client.containers.run.return_value=child
    assert manager.launch_container(name='fast',agent='material',mode='replica',params={}) is child
    assert 'exit status unavailable' in capsys.readouterr().out
    assert manager.tracked_containers==[]


def test_bulk_cleanup_continues_when_stop_already_auto_removed_a_child(manager):
    first,second=MagicMock(),MagicMock()
    first.remove.side_effect=handler_module.docker.errors.NotFound('auto-removed after stop')
    manager.client.containers.list.return_value=[first,second]
    manager.stop_tracked_containers()
    second.stop.assert_called_once()
    second.remove.assert_called_once_with(force=False)


def test_listing_skips_children_removed_between_list_and_reload(manager):
    missing,present=MagicMock(),MagicMock()
    missing.reload.side_effect=handler_module.docker.errors.NotFound('auto-removed')
    present.id='still-running'
    manager.client.containers.list.return_value=[missing,present]
    assert [row['id'] for row in manager.list_tracked_containers()]==['still-running']
