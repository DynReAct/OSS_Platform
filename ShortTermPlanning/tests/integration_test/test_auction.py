import os
from unittest.mock import patch, MagicMock

import pytest
from confluent_kafka.admin import AdminClient

from common.data.load_url import DOCKER_REPLICA
from common.handler import DockerManager
from short_term_planning import execute_short_term_planning, delete_all_topics


@pytest.fixture(autouse=True)
def initialize():
    # Initialization code that runs before each test function
    print("Setting up for a test")
    # admin_client = AdminClient({"bootstrap.servers": "138.100.82.173:9092"})
    # delete_all_topics(admin_client, verbose=3)
    print("Deleted all topics")
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
        "base": "../../dynreact/shortterm",
        "runningWait": "0",
        "cloningWait": "0",
        "auctionWait": "0",
        "counterbidWait": "0",
        "exitWait": "0",
        "equipments": "",
        "nmaterials": 0,
        "rungagents": 100
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
        "base": "../../dynreact/shortterm",
        "runningWait": "0",
        "cloningWait": "0",
        "auctionWait": "0",
        "counterbidWait": "0",
        "exitWait": "0",
        "equipments": "",
        "nmaterials": 0,
        "rungagents": 111
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
        "base": "../../dynreact/shortterm",
        "runningWait": "0",
        "cloningWait": "0",
        "auctionWait": "0",
        "counterbidWait": "0",
        "exitWait": "0",
        "equipments": "",
        "nmaterials": 0,
        "rungagents": 100
    }

    # Can't really mock a Docker container isolated execution. Luckly tagging ensure a single reference
    real_replica_log_container = DockerManager(tag=f"log{DOCKER_REPLICA}", max_allowed=-1)
    real_replica_log_container.clean_containers()

    execute_short_term_planning(args)

    assert len(real_replica_log_container.list_tracked_containers()) == 1

def test_scenario_03(log_handler_spy, equipment_handler_spy, material_handler_spy):
    """General LOG and RESOURCES startup. Agents cloning for an auction, and agents exiting"""

    args = {
        "verbose": 3,
        "base": "../../dynreact/shortterm",
        "runningWait": "0",
        "cloningWait": "0",
        "auctionWait": "0",
        "counterbidWait": "0",
        "exitWait": "0",
        "equipments": "9",
        "nmaterials": 1,
        "rungagents": 111
    }

    # Can't really mock a Docker container isolated execution. Luckly tagging ensure a single reference
    real_replica_equipment_container = DockerManager(tag=f"equipment{DOCKER_REPLICA}", max_allowed=-1)
    real_replica_equipment_container.clean_containers()

    # Can't really mock a Docker container isolated execution. Luckly tagging ensure a single reference
    real_replica_log_container = DockerManager(tag=f"log{DOCKER_REPLICA}", max_allowed=-1)
    real_replica_log_container.clean_containers()

    real_replica_material_container = DockerManager(tag=f"material{DOCKER_REPLICA}", max_allowed=-1)
    real_replica_material_container.clean_containers()

    execute_short_term_planning(args)

    assert len(real_replica_log_container.list_tracked_containers()) == 1
    assert len(real_replica_equipment_container.list_tracked_containers()) == 1
    assert len(real_replica_material_container.list_tracked_containers()) == 1


def test_scenario_05():
    """Test the return value of short_term_planning()."""

    args = {
        "verbose": 3,
        "base": "../../dynreact/shortterm",
        "runningWait": "10",
        "cloningWait": "30",
        "auctionWait": "50",
        "counterbidWait": "15",
        "exitWait": "10",
        "equipments": "6",
        "nmaterials": 1,
        "rungagents": 111
    }


    result = execute_short_term_planning(args)

    list_equipments = args["equipments"].split(" ")
    assert len(list_equipments) == len(result.keys())

    for equipment in list_equipments:
        current_equipment = result[equipment]

        assert len(current_equipment) == args["nmaterials"]
