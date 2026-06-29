"""Test support and regression coverage for OSS_Platform/ShortTermPlanning/tests/unit_tests/test_common.

The module is documented in English to make the short-term planning
workflow easier to maintain across OSS and RAS-specific integrations.
"""

from typing import Any
import json
import os
from unittest.mock import patch, MagicMock

@patch("material.calculate_bidding_price", return_value=250.0)
@patch("material.sendmsgtopic", return_value=None)
def test_handle_bid_action_valid_bidding_price(mock_calculate_bidding_price: Any, mock_sendmsgtopic: Any, material_agent: Any) -> None:
    """Test handle bid action valid bidding price.
    
    This function is part of the short-term planning workflow and keeps
    the existing runtime behavior while documenting the public contract.
    
    Args:
        mock_calculate_bidding_price: Input value for the `mock_calculate_bidding_price` parameter.
        mock_sendmsgtopic: Input value for the `mock_sendmsgtopic` parameter.
        material_agent: Input value for the `material_agent` parameter.
    
    Returns:
        The value produced by the underlying planning, UI, or test helper logic.
    """
    dctmsg = {
        "topic": material_agent.topic,
        "payload": {
            "id": "equip1",
            "status": {"equipment": "equip1"},
            "previous_price": 200.0
        }
    }

    result = material_agent.handle_bid_action(dctmsg)

    assert result == "CONTINUE"

    mock_calculate_bidding_price.assert_called_once_with(
        equipment_status={'equipment': dctmsg["payload"]["id"]},
        material_params=material_agent.params,
        previous_price=dctmsg["payload"]["previous_price"]
    )

    mock_sendmsgtopic.assert_called_once_with(
        action='COUNTERBID',
        dest=dctmsg["payload"]["id"],
        payload={
            'id': material_agent.agent,
            'material_params': material_agent.params,
            'price': 250
        },
        producer=material_agent.producer,
        source=material_agent.agent,
        topic=material_agent.topic,
        tsend=material_agent.topic,
        vb=material_agent.verbose
    )

@patch("material.calculate_bidding_price", return_value=None)
@patch("material.sendmsgtopic", return_value=None)
def test_handle_bid_action_rejected_offer(mock_sendmsgtopic: Any, mock_calculate_bidding_price: Any, material_agent: Any) -> None:
    """Test handle bid action rejected offer.
    
    This function is part of the short-term planning workflow and keeps
    the existing runtime behavior while documenting the public contract.
    
    Args:
        mock_sendmsgtopic: Input value for the `mock_sendmsgtopic` parameter.
        mock_calculate_bidding_price: Input value for the `mock_calculate_bidding_price` parameter.
        material_agent: Input value for the `material_agent` parameter.
    
    Returns:
        The value produced by the underlying planning, UI, or test helper logic.
    """
    dctmsg = {
        "topic": material_agent.topic,
        "payload": {
            "id": "equip3",  # Equipment not allowed
            "status": {"equipment": "equip3"},
            "previous_price": 200.0
        }
    }

    result = material_agent.handle_bid_action(dctmsg)

    assert result == "CONTINUE"

    mock_calculate_bidding_price.assert_called_once_with(
        action='COUNTERBID',
        dest=dctmsg["payload"]["id"],
        payload={
            'id': material_agent.agent,
            'material_params': material_agent.params,
            'price': 250
        },
        producer=material_agent.producer,
        source=material_agent.agent,
        topic=material_agent.topic,
        tsend=material_agent.topic,
        vb=material_agent.verbose
    )

    mock_sendmsgtopic.assert_not_called()


@patch('material.calculate_bidding_price')
@patch('material.sendmsgtopic')
def test_handle_bid_action_with_no_previous_price(mock_calculate_bidding_price: Any, mock_sendmsgtopic: Any, material_agent: Any) -> None:
    """Test handle bid action with no previous price.
    
    This function is part of the short-term planning workflow and keeps
    the existing runtime behavior while documenting the public contract.
    
    Args:
        mock_calculate_bidding_price: Input value for the `mock_calculate_bidding_price` parameter.
        mock_sendmsgtopic: Input value for the `mock_sendmsgtopic` parameter.
        material_agent: Input value for the `material_agent` parameter.
    
    Returns:
        The value produced by the underlying planning, UI, or test helper logic.
    """
    mock_calculate_bidding_price.return_value = 150.0  # Mock bidding price
    mock_sendmsgtopic.return_value = None

    dctmsg = {
        "topic": "auction_topic",
        "payload": {
            "id": "equip1",
            "status": {"equipment": "equip1"},
            "previous_price": None
        }
    }

    result = material_agent.handle_bid_action(dctmsg)

    assert result == "CONTINUE"
    mock_calculate_bidding_price.assert_called_once_with(
        material_params=material_agent.params,
        equipment_status=dctmsg["payload"]["status"],
        previous_price=dctmsg["payload"]["previous_price"]
    )

    mock_sendmsgtopic.assert_called_once_with(
        producer=material_agent.producer,
        tsend="auction_topic",
        topic="auction_topic",
        source=material_agent.agent,
        dest="equip1",
        action="COUNTERBID",
        payload={
            "id": material_agent.agent,
            "material_params": material_agent.params,
            "price": 150.0
        },
        vb=material_agent.verbose
    )


from dynreact.shortterm.common import KeySearch
from dynreact.shortterm.shorttermtargets import ShortTermTargets
from dynreact.shortterm.short_term_planning import _format_container_diagnostics


def test_dump_model_can_skip_environment_overrides() -> None:
    """Replica payload variables must not be overwritten by stale container env."""
    KeySearch.set_global(ShortTermTargets(KAFKA_IP="expected-broker:9092", VB=3))

    with patch.dict(os.environ, {"KAFKA_IP": "stale-broker:9092"}, clear=False):
        dumped_with_env = KeySearch.dump_model()
        dumped_without_env = KeySearch.dump_model(include_env=False)

    assert dumped_with_env["KAFKA_IP"] == "stale-broker:9092"
    assert dumped_without_env["KAFKA_IP"] == "expected-broker:9092"


def test_format_container_diagnostics_includes_exit_reason() -> None:
    """Missing base-agent diagnostics should expose Docker termination details."""
    diagnostics = _format_container_diagnostics(
        "MATERIAL",
        [
            {
                "name": "MATERIAL_Base",
                "status": "exited",
                "exit_code": 137,
                "oom_killed": True,
                "error": "",
                "finished_at": "2026-06-03T13:51:00Z",
            },
            {
                "name": "MATERIAL_StillRunning",
                "status": "running",
            },
        ],
    )

    assert diagnostics == [
        "MATERIAL:MATERIAL_Base [exited] oom-killed, exit_code=137, finished_at=2026-06-03T13:51:00Z"
    ]
