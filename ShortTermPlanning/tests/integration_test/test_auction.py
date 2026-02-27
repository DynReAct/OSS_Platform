import os
from unittest.mock import patch, MagicMock

import pytest

from dynreact.shortterm.common import purge_topics, KeySearch
from dynreact.shortterm.common.handler import DockerManager
from dynreact.shortterm.short_term_planning import execute_short_term_planning
from dynreact.shortterm.shorttermtargets import ShortTermTargets

KeySearch.set_global(config_provider=ShortTermTargets())
topic_gen = KeySearch.search_for_value("TOPIC_GEN")
topic_callback = KeySearch.search_for_value("TOPIC_CALLBACK")

@pytest.fixture(autouse=True)
def initialize():
    print("Setting up for a test.")
    print("Purging topics.")
    purge_topics(topics=[topic_callback, topic_gen, 'DYN_TEST'])
    yield
    print("Tearing down after a test.")

@pytest.fixture
def run_agents_handler_spy():
    real_log_container = DockerManager(tag="logTEST", max_allowed=1)
    real_equipment_container = DockerManager(tag="equipmentTEST", max_allowed=1)
    real_material_container = DockerManager(tag="materialTEST", max_allowed=1)

    with patch("dynreact.shortterm.short_term_planning.DockerManager") as MockDockerManager:
        mock_log_handler = MagicMock(wraps=real_log_container)
        mock_equipment_handler = MagicMock(wraps=real_equipment_container)
        mock_material_handler = MagicMock(wraps=real_material_container)

        MockDockerManager.side_effect = [
            mock_log_handler,
            mock_equipment_handler,
            mock_material_handler
        ]

        yield mock_log_handler, mock_equipment_handler, mock_material_handler

def test_scenario_00(run_agents_handler_spy):
    """General LOG startup. message sending, and agent exiting"""

    args = {
        "verbose": 3,
        "runningWait": "0",
        "cloningWait": "0",
        "auctionWait": "0",
        "counterbidWait": "0",
        "smallWait": "5",
        "exitWait": "0",
        "equipments": [],
        "nmaterials": 0,
        "rungagents": 100,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-18T08:00:00Z")
    }

    with patch("dynreact.shortterm.short_term_planning.create_auction", return_value=("DYN_TEST", 0)):

        # Import it after mocking the methods
        from dynreact.shortterm.short_term_planning import execute_short_term_planning

        execute_short_term_planning(args)

    run_agents_handler_spy[0].launch_container.assert_called_once_with(name="Base", agent="log", mode="base", params={
        "verbose": args["verbose"],
        "kafka-ip": KeySearch.search_for_value("KAFKA_IP")
    }, auto_remove=False)

    # Only 1 was added
    assert len(run_agents_handler_spy[0].client.containers.list(filters={"label": f"owner=logTEST"}, all=True)) == 1
    assert run_agents_handler_spy[1].launch_container.call_count == 0
    assert run_agents_handler_spy[2].launch_container.call_count == 0

def test_scenario_01(run_agents_handler_spy):
    """Startup and exit ot all general agents"""

    args = {
        "verbose": 3,
        "runningWait": "0",
        "cloningWait": "0",
        "auctionWait": "0",
        "counterbidWait": "0",
        "smallWait": "5",
        "smallWait": "5",
        "exitWait": "0",
        "equipments": [],
        "nmaterials": 0,
        "rungagents": 111,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-18T08:00:00Z")
    }

    with patch("dynreact.shortterm.short_term_planning.create_auction", return_value=("DYN_TEST", 0)):

        # Import it after mocking the methods
        from dynreact.shortterm.short_term_planning import execute_short_term_planning

        execute_short_term_planning(args)

    run_agents_handler_spy[0].launch_container.assert_called_once_with(name="Base", agent="log", mode="base", params={
        "verbose": args["verbose"],
        "kafka-ip": KeySearch.search_for_value("KAFKA_IP")
    }, auto_remove=False)

    run_agents_handler_spy[1].launch_container.assert_called_once_with(name="Base", agent="equipment", mode="base", params={
        "verbose": args["verbose"],
        "kafka-ip": KeySearch.search_for_value("KAFKA_IP")
    }, auto_remove=False)

    run_agents_handler_spy[2].launch_container.assert_called_once_with(name="Base", agent="material", mode="base", params={
        "verbose": args["verbose"],
        "kafka-ip": KeySearch.search_for_value("KAFKA_IP")
    }, auto_remove=False)

    assert len(run_agents_handler_spy[0].client.containers.list(filters={"label": f"owner=logTEST"}, all=True)) == 1
    assert len(run_agents_handler_spy[1].client.containers.list(filters={"label": f"owner=equipmentTEST"}, all=True)) == 1
    assert len(run_agents_handler_spy[2].client.containers.list(filters={"label": f"owner=materialTEST"}, all=True)) == 1

def test_scenario_02(run_agents_handler_spy):
    """General LOG startup, agent cloning for an auction. message sending to the clone, and a ents exitin"""

    args = {
        "verbose": 3,
        "runningWait": "0",
        "cloningWait": "0",
        "auctionWait": "0",
        "counterbidWait": "0",
        "smallWait": "5",
        "exitWait": "0",
        "equipments": [],
        "nmaterials": 0,
        "rungagents": 100,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-18T08:00:00Z")
    }

    # Can't really mock a Docker container isolated execution. Luckly tagging ensure a single reference
    run_agents_handler_spy[0].clean_containers()

    execute_short_term_planning(args)

    assert len(run_agents_handler_spy[0].list_tracked_containers()) == 1

def test_scenario_03(run_agents_handler_spy):
    """General LOG and RESOURCES startup. Agents cloning for an auction, and agents exiting"""

    args = {
        "verbose": 3,
        "runningWait": "10",
        "cloningWait": "30",
        "auctionWait": "0",
        "counterbidWait": "0",
        "smallWait": "5",
        "exitWait": "0",
        "equipments": ["7"],
        "nmaterials": 1,
        "rungagents": 111,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-18T08:00:00Z")
    }

    # Can't really mock a Docker container isolated execution. Luckly tagging ensure a single reference
    run_agents_handler_spy[1].clean_containers()
    run_agents_handler_spy[2].clean_containers()
    run_agents_handler_spy[0].clean_containers()

    execute_short_term_planning(args)

    assert len(run_agents_handler_spy[1].list_tracked_containers()) == 1
    assert len(run_agents_handler_spy[2].list_tracked_containers()) == 1
    assert len(run_agents_handler_spy[0].list_tracked_containers()) == 1

def test_scenario_04():
    """Test the return value of short_term_planning() locally."""

    args = {
        "verbose": 3,
        "runningWait": "10",
        "cloningWait": "30",
        "auctionWait": "50",
        "counterbidWait": "15",
        "smallWait": "5",
        "exitWait": "10",
        "equipments": os.environ.get("SCENARIO_4_5_EQUIPMENT", "7").split(" "),
        "nmaterials": 1,
        "rungagents": 111,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-18T08:00:00Z")
    }

    result = execute_short_term_planning(args)

    list_equipments = args["equipments"]
    assert len(list_equipments) == len(result.keys())

    for equipment in list_equipments:
        current_equipment = result[equipment]

        assert len(current_equipment) == args["nmaterials"]

    print(result)

def test_scenario_05():
    """Test the return value of short_term_planning() remotely with One Equipment, One Material."""

    args = {
        "verbose": 3,
        "runningWait": "10",
        "cloningWait": "30",
        "auctionWait": "50",
        "counterbidWait": "15",
        "smallWait": "5",
        "exitWait": "10",
        "equipments": os.environ.get("SCENARIO_4_5_EQUIPMENT", "7").split(" "),
        "nmaterials": 1,
        "rungagents": 000,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-18T08:00:00Z")
    }

    result = execute_short_term_planning(args)

    list_equipments = args["equipments"]
    assert len(list_equipments) == len(result.keys())

    for equipment in list_equipments:
        current_equipment = result[equipment]

        assert len(current_equipment) == args["nmaterials"]

    print(result)

def test_scenario_06():
    """Test the return value of short_term_planning() remotely with One Equipment, Two Material."""

    args = {
        "verbose": 3,
        "runningWait": "10",
        "cloningWait": "30",
        "auctionWait": "200",
        "counterbidWait": "15",
        "smallWait": "5",
        "exitWait": "10",
        "equipments": os.environ.get("SCENARIO_6_EQUIPMENT", "7").split(" "),
        "nmaterials": 2,
        "rungagents": 000,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-18T08:00:00Z")
    }

    result = execute_short_term_planning(args)

    assert result is not None

    list_equipments = args["equipments"]
    assert len(list_equipments) == len(result.keys())

    for equipment in list_equipments:
        current_equipment = result[equipment]

        assert len(current_equipment) == args["nmaterials"]

    print(result)

def test_scenario_07():
    """Test the return value of short_term_planning() remotely with Two Equipments, One Material."""

    args = {
        "verbose": 3,
        "runningWait": "10",
        "cloningWait": "30",
        "auctionWait": "200",
        "counterbidWait": "15",
        "smallWait": "5",
        "exitWait": "10",
        "equipments": os.environ.get("SCENARIO_7_EQUIPMENTS", "6 7").split(" "),
        "nmaterials": 1,
        "rungagents": 000,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-18T08:00:00Z")
    }

    result = execute_short_term_planning(args)

    assert result is not None

    list_equipments = args["equipments"]
    assert len(list_equipments) == len(result.keys())

    for equipment in list_equipments:
        current_equipment = result[equipment]

        assert len(current_equipment) == args["nmaterials"]

    print(result)

def test_scenario_08():
    """Test the return value of short_term_planning() remotely with Two Equipments, Two Materials."""

    args = {
        "verbose": 3,
        "runningWait": "10",
        "cloningWait": "30",
        "auctionWait": "200",
        "counterbidWait": "15",
        "smallWait": "5",
        "exitWait": "10",
        "equipments": os.environ.get("SCENARIO_8_EQUIPMENTS", "6 7").split(" "),
        "nmaterials": 2,
        "rungagents": 000,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-18T08:00:00Z")
    }

    result = execute_short_term_planning(args)

    assert result is not None

    list_equipments = args["equipments"]
    assert len(list_equipments) == len(result.keys())

    for equipment in list_equipments:
        current_equipment = result[equipment]

        assert len(current_equipment) == args["nmaterials"]

    orders_ids = []

    for equipment in result.values():
        orders_ids += list(map(lambda x: x["id"], equipment))

    assert os.environ.get("SCENARIO_8_ORDER_ID", "1181267") in orders_ids

    print(result)
