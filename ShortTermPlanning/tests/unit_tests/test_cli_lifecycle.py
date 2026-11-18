"""Jenkins lifecycle regressions: LOG-only checks must not require REST snapshots."""
from unittest.mock import MagicMock, patch

import pytest
from requests.exceptions import HTTPError

from dynreact.shortterm import short_term_planning as planning


@pytest.fixture(autouse=True)
def isolate_runtime_environment(monkeypatch):
    for key in ("TOPIC_GEN", "TOPIC_CALLBACK", "KAFKA_TOPIC_PREFIX", "KAFKA_IP", "VB"):
        monkeypatch.delenv(key, raising=False)


def cli_args(general_agents, equipments):
    return dict(verbose=0, runningWait="0", cloningWait="0", auctionWait="0",
                exitWait="0", counterbidWait="0", smallWait="0",
                rungagents=general_agents, equipments=equipments,
                snapshot="2025-01-18T08:00:00Z", nmaterials=0, start_time=None)


def test_empty_order_scope_never_loads_a_snapshot():
    with patch.object(planning, "DataSetup", side_effect=HTTPError("snapshot service unavailable")) as data:
        assert planning._equipment_order_scope([], "unavailable-snapshot", 0) == {}
    data.assert_not_called()


@pytest.mark.parametrize("general_agents", [100, 111])
def test_jenkins_startup_scenarios_succeed_when_rest_is_unavailable(general_agents):
    """Reproduce scenarios 00/01 with a failing REST service and mocked Docker/Kafka."""
    handlers = [MagicMock() for _ in range(3)]
    for handler in handlers:
        handler.list_tracked_containers.return_value = [{"status": "running"}]
    with (patch.object(planning, "initialize_keysearch_from_runtime"),
          patch.object(planning, "Producer"),
          patch.object(planning, "run_general_agents", return_value=handlers) as launch,
          patch.object(planning, "sleep"),
          patch.object(planning, "create_callback_consumer") as reader,
          patch.object(planning, "create_auction", return_value=("DYN_TEST", 0)),
          patch.object(planning, "DataSetup", side_effect=HTTPError("HTTP 500")) as data,
          patch.object(planning, "start_auction") as start,
          patch.object(planning, "end_auction") as end,
          patch.object(planning, "clean_agents") as clean):
        assert planning.execute_short_term_planning(cli_args(general_agents, [])) == {}
    launch.assert_called_once()
    data.assert_not_called()
    start.assert_not_called()
    reader.return_value.close.assert_called_once()
    assert end.call_args.kwargs["topic"] == "DYN_TEST"
    assert clean.call_args.args[2] == str(general_agents)


@pytest.mark.parametrize("materials", [None, []])
def test_log_only_creation_has_no_snapshot_or_transport_dependency(materials):
    """Scenario 02 uses the real creator rather than the patched 00/01 creator."""
    admin = MagicMock()
    with (patch.object(planning, "DataSetup", side_effect=HTTPError("HTTP 500")) as data,
          patch.object(planning, "get_transport_times", side_effect=HTTPError("HTTP 500")) as transport,
          patch.object(planning, "topic_exist", return_value=False),
          patch.object(planning, "sendmsgtopic") as sent):
        topic, agents = planning.create_auction([], MagicMock(), 0, act="LOG-ONLY",
                                              materials=materials, admin_client=admin)
    assert agents == 1
    data.assert_not_called()
    transport.assert_not_called()
    admin.create_topics.assert_called_once()
    assert [(call.kwargs["action"], call.kwargs["dest"]) for call in sent.call_args_list] == [
        ("CREATE", "LOG:dynGEN"), ("WRITE", f"LOG:{topic}")]


def test_snapshot_error_in_real_auction_is_reported_and_cleans_the_lifecycle():
    """REST is still required for production auctions; a 500 must not become success."""
    with (patch.object(planning, "initialize_keysearch_from_runtime"),
          patch.object(planning, "Producer"),
          patch.object(planning, "sleep"),
          patch.object(planning, "create_callback_consumer") as reader,
          patch.object(planning, "create_auction", return_value=("dynAuction", 2)),
          patch.object(planning, "DataSetup", side_effect=HTTPError("HTTP 500")),
          patch.object(planning, "start_auction") as start,
          patch.object(planning, "end_auction") as end,
          patch.object(planning, "clean_agents") as clean):
        with pytest.raises(HTTPError, match="HTTP 500"):
            planning.execute_short_term_planning(cli_args(0, ["7"]))
    start.assert_not_called()
    reader.return_value.close.assert_called_once()
    assert end.call_args.kwargs["topic"] == "dynAuction"
    clean.assert_called_once()


def test_real_creation_still_loads_snapshot_and_transport_for_selected_materials():
    admin = MagicMock()
    with (patch.object(planning, "DataSetup") as data,
          patch.object(planning, "get_transport_times", return_value={}) as transport,
          patch.object(planning, "topic_exist", return_value=False),
          patch.object(planning, "sendmsgtopic") as sent):
        data.return_value.last_snapshot = "requested-snapshot"
        data.return_value.get_material_params.return_value = {"id": "MAT-1"}
        _, count = planning.create_auction(["7"], MagicMock(), 0, act="REAL",
                                          snapshot="requested-snapshot", materials=["MAT-1"], admin_client=admin)
    assert count == 3
    data.assert_called_once_with(verbose=0, snapshot_time="requested-snapshot")
    data.return_value.get_material_params.assert_called_once_with("MAT-1")
    transport.assert_called_once()
    equipment = next(call.kwargs for call in sent.call_args_list if call.kwargs["dest"] == "EQUIPMENT:dynGEN")
    assert equipment["payload"]["snapshot"] == "requested-snapshot"
