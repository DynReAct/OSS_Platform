import os
from unittest.mock import patch, MagicMock

import pytest
from confluent_kafka.admin import AdminClient

from common.handler import DockerManager
from short_term_planning import execute_short_term_planning

@pytest.fixture(autouse=True)
def initialize():
    print("Setting up for a test")
    admin_client = AdminClient({"bootstrap.servers": "138.100.82.173:9092"})
    admin_client.delete_topics(topics=['DynReact-TEST-Callback', 'DynReact-TEST-Gen', 'DYN_TEST'])
    print("Deleted test topics")
    yield
    print("Tearing down after a test")

@pytest.fixture
def log_handler_spy():
    real_log_container = DockerManager(tag="logTEST", max_allowed=1)
    with patch("short_term_planning.log_handler", MagicMock(wraps=real_log_container)) as mock:
        yield mock

@pytest.fixture
def equipment_handler_spy():
    real_equipment_container = DockerManager(tag="equipmentTEST", max_allowed=1)
    with patch("short_term_planning.equipment_handler", MagicMock(wraps=real_equipment_container)) as mock:
        yield mock

@pytest.fixture
def material_handler_spy():
    real_material_container = DockerManager(tag="materialTEST", max_allowed=1)
    with patch("short_term_planning.material_handler", MagicMock(wraps=real_material_container)) as mock:
        yield mock

def test_scenario_00(log_handler_spy, equipment_handler_spy, material_handler_spy):
    """General LOG startup. message sending, and agent exiting"""

    args = {
        "verbose": 3,
        "base": "../../shortterm",
        "runningWait": "0",
        "cloningWait": "0",
        "auctionWait": "0",
        "counterbidWait": "0",
        "exitWait": "0",
        "equipments": [],
        "nmaterials": 0,
        "rungagents": 100,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-31T22:00:00Z")
    }

    with patch("short_term_planning.create_auction", return_value=("DYN_TEST", 0)):

        # Import it after mocking the methods
        from short_term_planning import execute_short_term_planning

        execute_short_term_planning(args)

    log_handler_spy.launch_container.assert_called_once_with(name="Base", agent="log", mode="base", params={
        "verbose": args["verbose"]
    }, auto_remove=False)

    # Only 1 was added
    assert len(log_handler_spy.client.containers.list(filters={"label": f"owner=logTEST"}, all=True)) == 1
    assert equipment_handler_spy.launch_container.call_count == 0
    assert material_handler_spy.launch_container.call_count == 0

def test_scenario_01(log_handler_spy, equipment_handler_spy, material_handler_spy):
    """Startup and exit ot all general agents"""

    args = {
        "verbose": 3,
        "base": "../../shortterm",
        "runningWait": "0",
        "cloningWait": "0",
        "auctionWait": "0",
        "counterbidWait": "0",
        "exitWait": "0",
        "equipments": [],
        "nmaterials": 0,
        "rungagents": 111,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-31T22:00:00Z")
    }

    with patch("short_term_planning.create_auction", return_value=("DYN_TEST", 0)):

        # Import it after mocking the methods
        from short_term_planning import execute_short_term_planning

        execute_short_term_planning(args)

    log_handler_spy.launch_container.assert_called_once_with(name="Base", agent="log", mode="base", params={
        "verbose": args["verbose"]
    }, auto_remove=False)

    equipment_handler_spy.launch_container.assert_called_once_with(name="Base", agent="equipment", mode="base", params={
        "verbose": args["verbose"]
    }, auto_remove=False)

    material_handler_spy.launch_container.assert_called_once_with(name="Base", agent="material", mode="base", params={
        "verbose": args["verbose"]
    }, auto_remove=False)

    assert len(log_handler_spy.client.containers.list(filters={"label": f"owner=logTEST"}, all=True)) == 1
    assert len(equipment_handler_spy.client.containers.list(filters={"label": f"owner=equipmentTEST"}, all=True)) == 1
    assert len(material_handler_spy.client.containers.list(filters={"label": f"owner=materialTEST"}, all=True)) == 1

def test_scenario_02(log_handler_spy, equipment_handler_spy, material_handler_spy):
    """General LOG startup, agent cloning for an auction. message sending to the clone, and a ents exitin"""

    args = {
        "verbose": 3,
        "base": "../../shortterm",
        "runningWait": "0",
        "cloningWait": "0",
        "auctionWait": "0",
        "counterbidWait": "0",
        "exitWait": "0",
        "equipments": [],
        "nmaterials": 0,
        "rungagents": 100,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-31T22:00:00Z")
    }

    # Can't really mock a Docker container isolated execution. Luckly tagging ensure a single reference
    log_handler_spy.clean_containers()

    execute_short_term_planning(args)

    assert len(log_handler_spy.list_tracked_containers()) == 1

def test_scenario_03(log_handler_spy, equipment_handler_spy, material_handler_spy):
    """General LOG and RESOURCES startup. Agents cloning for an auction, and agents exiting"""

    args = {
        "verbose": 3,
        "base": "../../shortterm",
        "runningWait": "0",
        "cloningWait": "0",
        "auctionWait": "0",
        "counterbidWait": "0",
        "exitWait": "0",
        "equipments": ["9"],
        "nmaterials": 1,
        "rungagents": 111,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-31T22:00:00Z")
    }

    # Can't really mock a Docker container isolated execution. Luckly tagging ensure a single reference
    equipment_handler_spy.clean_containers()
    material_handler_spy.clean_containers()
    log_handler_spy.clean_containers()

    execute_short_term_planning(args)

    assert len(equipment_handler_spy.list_tracked_containers()) == 1
    assert len(material_handler_spy.list_tracked_containers()) == 1
    assert len(log_handler_spy.list_tracked_containers()) == 1


def test_scenario_05():
    """Test the return value of short_term_planning()."""

    args = {
        "verbose": 3,
        "base": "../../shortterm",
        "runningWait": "10",
        "cloningWait": "30",
        "auctionWait": "50",
        "counterbidWait": "15",
        "exitWait": "10",
        "equipments": os.environ.get("SCENARIO_5_EQUIPMENT", "9").split(" "),
        "nmaterials": 1,
        "rungagents": 000,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-31T22:00:00Z")
    }

    result = execute_short_term_planning(args)

    list_equipments = args["equipments"].split(" ")
    assert len(list_equipments) == len(result.keys())

    for equipment in list_equipments:
        current_equipment = result[equipment]

        assert len(current_equipment) == args["nmaterials"]

    print(result)

def test_scenario_06():
    """Test the return value of short_term_planning()."""

    args = {
        "verbose": 3,
        "base": "../../shortterm",
        "runningWait": "10",
        "cloningWait": "30",
        "auctionWait": "50",
        "counterbidWait": "15",
        "exitWait": "10",
        "equipments": os.environ.get("SCENARIO_6_EQUIPMENT", "9").split(" "),
        "nmaterials": 2,
        "rungagents": 000,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-31T22:00:00Z")
    }

    result = execute_short_term_planning(args)

    list_equipments = args["equipments"].split(" ")
    assert len(list_equipments) == len(result.keys())

    for equipment in list_equipments:
        current_equipment = result[equipment]

        assert len(current_equipment) == args["nmaterials"]

    print(result)

def test_scenario_07():
    """Test the return value of short_term_planning()."""

    args = {
        "verbose": 3,
        "base": "../../shortterm",
        "runningWait": "10",
        "cloningWait": "30",
        "auctionWait": "200",
        "counterbidWait": "15",
        "exitWait": "10",
        "equipments": os.environ.get("SCENARIO_7_EQUIPMENT", "9 10").split(" "),
        "nmaterials": 1,
        "rungagents": 000,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-31T22:00:00Z")
    }

    result = execute_short_term_planning(args)

    list_equipments = args["equipments"]
    assert len(list_equipments) == len(result.keys())

    for equipment in list_equipments:
        current_equipment = result[equipment]

        assert len(current_equipment) == args["nmaterials"]

    print(result)

def test_scenario_08():
    """Test the return value of short_term_planning()."""

    args = {
        "verbose": 3,
        "base": "../../shortterm",
        "runningWait": "10",
        "cloningWait": "30",
        "auctionWait": "200",
        "counterbidWait": "15",
        "exitWait": "10",
        "equipments": os.environ.get("SCENARIO_8_EQUIPMENT", "9 11").split(" "),
        "nmaterials": 2,
        "rungagents": 000,
        "snapshot": os.environ.get("SNAPSHOT_VERSION", "2025-01-31T22:00:00Z")
    }

    result = execute_short_term_planning(args)

    list_equipments = args["equipments"]
    assert len(list_equipments) == len(result.keys())

    for equipment in list_equipments:
        current_equipment = result[equipment]

        assert len(current_equipment) == args["nmaterials"]

    orders_ids = []

    for equipment in result.values():
        orders_ids += list(map(lambda x: x["id"], equipment))

    assert os.environ.get("SCENARIO_8_ORDER_ID", "1199061") in orders_ids

    print(result)