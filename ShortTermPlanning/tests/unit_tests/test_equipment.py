"""Unit tests for the EQUIPMENT agent of the short-term planning auction.

The tests cover the helpers and the handlers of
:class:`dynreact.shortterm.agents.equipment.Equipment`. Kafka and Docker are replaced by mocks.

The auction protocol these tests protect:

* On ``START`` the equipment invites every material of the auction to bid.
* Each ``COUNTERBID`` becomes a bid whose profit is the offered price minus the production cost.
* After ``COUNTERBID_WAIT`` seconds without new bids, the best bid is asked for confirmation, one
  material at a time. With no bids left, the equipment announces its end to the LOG and ends.
* A confirmed material moves the equipment to the next round. Reaching the target tonnage ends it.
"""
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dynreact.shortterm.agents import equipment as equipment_module
from dynreact.shortterm.agents.equipment import (
    Equipment, _coerce_float, _coerce_optional_float, material_weight_tons, parse_start_time,
)
from dynreact.shortterm.common import KeySearch

TOPIC = "dynTEST"
AGENT = f"EQUIPMENT:{TOPIC}:3:0"
START = datetime(2026, 1, 1, 8, 0, 0, tzinfo=timezone.utc)


def _make(manager: bool = False, **kwargs: Any) -> Equipment:
    """Builds an equipment whose Kafka and Docker clients are mocks."""
    values = dict(topic=TOPIC, agent=AGENT, status={"planning": {"cost": 1}, "targets": {"equipment": 3}},
                  operation_speed=2.0, start_time=START, target_tons=100.0, manager=manager)
    values.update(kwargs)
    with patch("dynreact.shortterm.agents.agent.Producer"), patch("dynreact.shortterm.agents.agent.Consumer"), \
            patch.object(equipment_module.DockerManager, "__init__", return_value=None):
        return Equipment(**values)


@pytest.fixture
def equipment() -> Equipment:
    return _make()


@pytest.fixture
def sent() -> Any:
    """Captures every message the equipment sends."""
    with patch.object(equipment_module, "sendmsgtopic") as mock, patch("dynreact.shortterm.agents.agent.sendmsgtopic"):
        yield mock


def _actions(sent_mock: MagicMock) -> list[str]:
    return [call.kwargs["action"] for call in sent_mock.call_args_list]


def _counterbid(material: str = f"MATERIAL:{TOPIC}:1", price: float = 10.0, **extra: Any) -> dict:
    payload = {"id": material, "material_params": {"order": {"id": 1}}, "price": price}
    payload.update(extra)
    return {"topic": TOPIC, "payload": payload}


# ---------------------------------------------------------------- helpers

@pytest.mark.parametrize("value, default, expected", [
    (None, 7.0, 7.0), ("", 7.0, 7.0), ("abc", 7.0, 7.0), ("2.5", 7.0, 2.5), (3, 7.0, 3.0),
])
def test_coerce_float(value: Any, default: float, expected: float) -> None:
    assert _coerce_float(value, default) == expected


@pytest.mark.parametrize("value, expected", [(None, None), ("", None), ("abc", None), ("2.5", 2.5), (0, 0.0)])
def test_coerce_optional_float(value: Any, expected: float | None) -> None:
    assert _coerce_optional_float(value) == expected


def test_material_weight_prefers_the_order_and_falls_back_to_the_top_level() -> None:
    assert material_weight_tons({"order": {"target_weight": 5.0, "actual_weight": 9.0}, "weight": 1.0}) == 5.0
    assert material_weight_tons({"order": {"actual_weight": 9.0}}) == 9.0
    assert material_weight_tons({"order": {}, "weight": 1.5}) == 1.5
    assert material_weight_tons({"actual_weight": 2.0}) == 2.0
    assert material_weight_tons({"order": {"id": 1}}) == 0.0      # OSS payloads carry no weight
    assert material_weight_tons("not a dict") == 0.0              # type: ignore[arg-type]


def test_parse_start_time_normalizes_to_utc() -> None:
    assert parse_start_time(None) is None
    assert parse_start_time("2026-01-01T08:00:00Z") == START
    assert parse_start_time("2026-01-01T08:00:00") == START                       # naive means UTC
    assert parse_start_time("2026-01-01T10:00:00+02:00") == START
    assert parse_start_time(datetime(2026, 1, 1, 8)) == START


def test_logical_equipment_id_is_stable_across_rounds() -> None:
    equipment = _make()
    assert equipment.logical_equipment_id() == "3"
    equipment.agent = f"EQUIPMENT:{TOPIC}:3:9"
    assert equipment.logical_equipment_id() == "3"


def test_target_tonnage_is_reached_at_or_above_the_target() -> None:
    equipment = _make(target_tons=10.0)
    assert not equipment.has_reached_target_tons()
    equipment.accumulated_tons = 10.0
    assert equipment.has_reached_target_tons()


# ---------------------------------------------------------------- START / COUNTERBID

def test_start_invites_every_material_of_the_auction_to_bid(equipment: Equipment, sent: MagicMock) -> None:
    assert equipment.handle_start_action({"topic": TOPIC, "payload": {"price": 4.0}}) == "CONTINUE"
    kwargs = sent.call_args.kwargs
    assert kwargs["action"] == "BID" and kwargs["dest"] == f"MATERIAL:{TOPIC}:.*"
    assert kwargs["payload"]["id"] == AGENT and kwargs["payload"]["previous_price"] == 4.0
    assert kwargs["payload"]["start_time"] == "2026-01-01T08:00:00Z"
    assert equipment.last_bid_time is not None and equipment.iter_post_bid == 0


def test_counterbid_becomes_a_bid_with_profit_price_minus_cost(equipment: Equipment) -> None:
    with patch.object(equipment_module, "calculate_production_cost", return_value=4.0):
        assert equipment.handle_counterbid_action(_counterbid(price=10.0)) == "CONTINUE"
    assert len(equipment.bids) == 1
    bid = equipment.bids[0]
    assert bid["material"] == f"MATERIAL:{TOPIC}:1" and bid["profit"] == 6.0 and bid["price"] == 10.0
    assert bid["is_tardy"] is False and equipment.last_bid_time is not None


def test_counterbid_arriving_after_the_start_is_tardy(equipment: Equipment) -> None:
    with patch.object(equipment_module, "calculate_production_cost", return_value=0.0):
        equipment.handle_counterbid_action(_counterbid(arrival_time="2026-01-01T09:00:00Z", lateness_seconds=3600))
    assert equipment.bids[0]["is_tardy"] is True and equipment.bids[0]["lateness_seconds"] == 3600.0


def test_counterbid_without_a_valid_transition_is_discarded(equipment: Equipment) -> None:
    with patch.object(equipment_module, "calculate_production_cost", return_value=None):
        assert equipment.handle_counterbid_action(_counterbid()) == "CONTINUE"
    assert equipment.bids == [] and equipment.last_bid_time is None


def test_bids_are_ordered_so_that_the_best_is_popped_last(equipment: Equipment) -> None:
    equipment.bids = [
        {"material": "tardy-rich", "profit": 99.0, "is_tardy": True, "lateness_seconds": 100.0},
        {"material": "ontime-poor", "profit": 1.0, "is_tardy": False, "lateness_seconds": 0.0},
        {"material": "ontime-rich", "profit": 5.0, "is_tardy": False, "lateness_seconds": 0.0},
        {"material": "tardy-less-late", "profit": 1.0, "is_tardy": True, "lateness_seconds": 10.0},
    ]
    equipment.sort_bids()
    order = [bid["material"] for bid in equipment.bids]
    # On-time bids win over tardy ones, then the highest profit; among tardy ones the least late
    assert order == ["tardy-rich", "tardy-less-late", "ontime-poor", "ontime-rich"]


# ---------------------------------------------------------------- bidding loop

def test_loop_does_nothing_before_the_first_bid(equipment: Equipment, sent: MagicMock) -> None:
    assert equipment.callback_before_message() == "CONTINUE"
    sent.assert_not_called()


def test_loop_waits_for_new_counterbids(equipment: Equipment, sent: MagicMock) -> None:
    equipment.last_bid_time = time.perf_counter()          # a bid has just arrived: COUNTERBID_WAIT is 5 s
    equipment.bids = [{"material": "m", "profit": 1.0}]
    assert equipment.callback_before_message() == "CONTINUE"
    sent.assert_not_called()
    assert len(equipment.bids) == 1


def test_loop_asks_the_best_material_for_confirmation_once(equipment: Equipment, sent: MagicMock) -> None:
    equipment.last_bid_time = time.perf_counter() - 60
    equipment.bids = [{"material": "poor", "profit": 1.0}, {"material": "rich", "profit": 9.0}]
    assert equipment.callback_before_message() == "CONTINUE"
    assert _actions(sent) == ["ASKCONFIRM"] and sent.call_args.kwargs["dest"] == "rich"
    assert sent.call_args.kwargs["payload"] == {"id": AGENT, "costs": equipment.status["planning"]}
    assert equipment.bid_to_confirm["material"] == "rich"
    # While the answer is pending nobody else is asked
    sent.reset_mock()
    equipment.callback_before_message()
    sent.assert_not_called()


def test_loop_ends_and_notifies_the_log_when_no_bids_are_left(equipment: Equipment, sent: MagicMock) -> None:
    equipment.last_bid_time = time.perf_counter() - 60
    assert equipment.callback_before_message() == "END"
    kwargs = sent.call_args.kwargs
    assert kwargs["action"] == "EQUIPMENTFINISHED" and kwargs["dest"] == f"LOG:{TOPIC}"
    assert kwargs["payload"] == {"equipment": "3", "reason": "no_more_bids"}


# ---------------------------------------------------------------- ASKCONFIRM / CONFIRM / ASSIGNED

def _confirm(material: str, params: dict | None = None) -> dict:
    return {"topic": TOPIC, "payload": {"id": material, "material_params": params or {"order": {"actual_weight": 20.0}},
                                       "order_length": 12.0}}


def test_confirmation_from_the_asked_material_moves_to_the_next_round(equipment: Equipment, sent: MagicMock) -> None:
    equipment.bid_to_confirm = {"material": "m1", "price": 8.0}
    with patch.object(equipment_module, "get_new_equipment_status", return_value=equipment.status):
        assert equipment.handle_confirm_action(_confirm("m1")) == "CONTINUE"
    assert equipment.previous_price == 8.0 and equipment.accumulated_tons == 20.0
    assert equipment.round_number == 1 and equipment.agent == f"EQUIPMENT:{TOPIC}:3:1"
    assert equipment.bids == [] and equipment.bid_to_confirm == {}
    assert "BID" in _actions(sent)                          # the next round starts bidding again


def test_confirmation_from_another_material_is_an_error(equipment: Equipment, sent: MagicMock) -> None:
    equipment.bid_to_confirm = {"material": "m1", "price": 8.0}
    with pytest.raises(RuntimeError, match="does not match"):
        equipment.handle_confirm_action(_confirm("intruder"))
    assert equipment.round_number == 0


def test_reaching_the_target_tonnage_ends_the_equipment(sent: MagicMock) -> None:
    equipment = _make(target_tons=15.0)
    equipment.bid_to_confirm = {"material": "m1", "price": 8.0}
    with patch.object(equipment_module, "get_new_equipment_status", return_value=equipment.status):
        assert equipment.handle_confirm_action(_confirm("m1")) == "END"
    kwargs = sent.call_args_list[0].kwargs
    assert kwargs["action"] == "EQUIPMENTFINISHED" and kwargs["payload"]["reason"] == "target_tons_reached"
    assert equipment.round_number == 0                       # it does not start another round


def test_assigned_elsewhere_clears_the_pending_confirmation(equipment: Equipment) -> None:
    equipment.bid_to_confirm = {"material": "m1", "price": 8.0}
    assert equipment.handle_assigned_action({"payload": {"id": "m1"}}) == "CONTINUE"
    assert equipment.bid_to_confirm == {}


def test_assigned_removes_the_material_from_the_open_bids(equipment: Equipment) -> None:
    equipment.bids = [{"material": "m1"}, {"material": "m2"}]
    equipment.handle_assigned_action({"payload": {"id": "m1"}})
    assert [bid["material"] for bid in equipment.bids] == ["m2"]


# ---------------------------------------------------------------- CREATE

def _create_message(**payload: Any) -> dict:
    values = {"id": 3, "snapshot": "2026-01-01T00:00:00Z", "operation_speed": "1.5", "variables": {}}
    values.update(payload)
    return {"topic": "dynAUCTION", "payload": values}


def test_create_launches_one_replica_container_per_equipment() -> None:
    parent = _make(manager=True)
    parent.handler = MagicMock()
    with patch.object(KeySearch, "assign_values"), patch.object(KeySearch, "dump_model", return_value={}), \
            patch.object(equipment_module, "get_equipment_status", return_value={"planning": {}}):
        assert parent.handle_create_action(_create_message(user_start_time="2026-01-01T09:00:00Z")) == "CONTINUE"
    kwargs = parent.handler.launch_container.call_args.kwargs
    assert kwargs["auto_remove"] is True
    assert kwargs["name"] == "dynAUCTION_3" and kwargs["agent"] == "equipment" and kwargs["mode"] == "replica"
    params = kwargs["params"]
    assert params["agent"] == "EQUIPMENT:dynAUCTION:3:0" and params["operation_speed"] == 1.5
    assert params["status"]["targets"] == {"equipment": 3}   # filled in when the status has no targets
    assert params["start_time"] == "2026-01-01T09:00:00Z"    # the user's start time wins


def test_replicas_cannot_create_replicas() -> None:
    replica = _make(manager=False)
    with pytest.raises(Exception, match="Replicas can't create new instances"):
        replica.handle_create_action(_create_message())
