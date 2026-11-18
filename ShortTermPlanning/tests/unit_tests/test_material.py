"""Unit tests for the MATERIAL agent of the short-term planning auction.

The tests cover the pure helpers, the bidding price, and the three message handlers
(``BID``, ``ASKCONFIRM`` and ``CREATE``) of :class:`dynreact.shortterm.agents.material.Material`.
Kafka and Docker are replaced by mocks, so neither a broker nor a daemon is needed.

The auction protocol these tests protect:

* A material answers every ``BID`` of a compatible equipment with a ``COUNTERBID``.
* A material is assigned to at most one equipment. Once committed, it rejects every other
  equipment with ``ASSIGNED`` and its agent loop ends only on the first confirmation.
* Only the parent (manager) material may clone replicas.
"""
from datetime import datetime, timezone
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dynreact.shortterm.agents import material as material_module
from dynreact.shortterm.agents.material import (
    Material, _parse_utc_datetime, _resolve_material_origin, _transfer_seconds,
)
from dynreact.shortterm.common import KeySearch

TOPIC = "dynTEST"
EQUIPMENT_ID = f"EQUIPMENT:{TOPIC}:3:1"
PARAMS = {"order": {"allowed_equipment": [3, 4], "due_date": "2023-12-31T23:59:59"}, "current_equipment": 3}
BASE_DATE = datetime(2020, 1, 1, tzinfo=timezone.utc)


def _make(manager: bool = True, params: dict | None = None, **kwargs: Any) -> Material:
    """Builds a material whose Kafka and Docker clients are mocks."""
    with patch("dynreact.shortterm.agents.agent.Producer"), patch("dynreact.shortterm.agents.agent.Consumer"), \
            patch.object(material_module.DockerManager, "__init__", return_value=None):
        return Material(topic=TOPIC, agent=f"MATERIAL:{TOPIC}:7", params=params if params is not None else PARAMS,
                        manager=manager, **kwargs)


@pytest.fixture
def material() -> Material:
    """Parent material with the default order parameters."""
    return _make()


@pytest.fixture
def sent() -> Any:
    """Captures every message the material sends, as a list of keyword dictionaries."""
    with patch.object(material_module, "sendmsgtopic") as mock:
        yield mock


def _actions(sent_mock: MagicMock) -> list[str]:
    return [call.kwargs["action"] for call in sent_mock.call_args_list]


def _bid(**overrides: Any) -> dict:
    """A ``BID`` message from the equipment 3."""
    payload = {"id": EQUIPMENT_ID, "status": {"targets": {"equipment": 3}}, "previous_price": None}
    payload.update(overrides)
    return {"topic": TOPIC, "payload": payload}


# ---------------------------------------------------------------- helpers

@pytest.mark.parametrize("value, expected", [
    (None, None),
    ("", None),
    ("not a date", None),
    ("2024-01-01T10:00:00Z", datetime(2024, 1, 1, 10, tzinfo=timezone.utc)),
    ("2024-01-01T10:00:00", datetime(2024, 1, 1, 10, tzinfo=timezone.utc)),   # naive means UTC
    ("2024-01-01T12:00:00+02:00", datetime(2024, 1, 1, 10, tzinfo=timezone.utc)),
])
def test_parse_utc_datetime(value: str | None, expected: datetime | None) -> None:
    assert _parse_utc_datetime(value) == expected


def test_transfer_seconds_prefers_the_specific_route_over_the_default() -> None:
    matrix = {"1": {"2": 600}, "__default__": {"__default__": 900}}
    assert _transfer_seconds(matrix, "1", "1") == 0        # same equipment: instantaneous
    assert _transfer_seconds(matrix, "1", "2") == 600      # known route
    assert _transfer_seconds(matrix, "1", "9") == 900      # unknown route: default
    assert _transfer_seconds({"1": {"2": 600}}, "1", "9") is None   # no default at all


def test_resolve_material_origin_falls_back_step_by_step() -> None:
    assert _resolve_material_origin({"current_equipment": 5, "order": {"current_equipment": [6]}}, "9") == "5"
    assert _resolve_material_origin({"order": {"current_equipment": [6, 7]}}, "9") == "6"
    assert _resolve_material_origin({"order": {"current_equipment": 8}}, "9") == "8"
    assert _resolve_material_origin({"current_equipment": "", "order": {}}, "9") == "9"   # assume colocated
    assert _resolve_material_origin({}, "9") == "9"


# ---------------------------------------------------------------- bidding price

def test_bidding_price_is_none_for_a_not_allowed_equipment() -> None:
    status = {"targets": {"equipment": 99}}
    assert Material.calculate_bidding_price(PARAMS, status, None) is None


def test_bidding_price_accepts_status_without_targets() -> None:
    assert Material.calculate_bidding_price(PARAMS, {"targets": None}, None) is not None


def test_bidding_price_depends_on_the_due_date_and_adds_the_previous_price() -> None:
    status = {"targets": {"equipment": 3}}
    days = (datetime(2023, 12, 31, 23, 59, 59, tzinfo=timezone.utc) - BASE_DATE).days
    assert Material.calculate_bidding_price(PARAMS, status, None) == pytest.approx(150 / days)
    assert Material.calculate_bidding_price(PARAMS, status, 2.0) == pytest.approx(150 / days + 2.0)
    sooner = {"order": {"allowed_equipment": [3], "due_date": "2022-01-01T00:00:00"}}
    assert Material.calculate_bidding_price(sooner, status, None) > Material.calculate_bidding_price(PARAMS, status, None)


def test_order_length_is_the_sum_of_the_coils() -> None:
    assert _make(coil_lengths=[10.0, 5.5]).calculate_order_length() == 15.5
    assert _make(coil_lengths=7).calculate_order_length() == 7.0
    assert _make().calculate_order_length() == 0.0


# ---------------------------------------------------------------- BID

def test_bid_is_answered_with_a_counterbid_to_that_equipment(material: Material, sent: MagicMock) -> None:
    assert material.handle_bid_action(_bid()) == "CONTINUE"
    sent.assert_called_once()
    kwargs = sent.call_args.kwargs
    assert kwargs["action"] == "COUNTERBID" and kwargs["dest"] == EQUIPMENT_ID
    assert kwargs["source"] == material.agent and kwargs["tsend"] == TOPIC
    assert kwargs["payload"]["id"] == material.agent and kwargs["payload"]["price"] > 0
    assert kwargs["payload"]["material_params"] == PARAMS


def test_bid_from_a_not_allowed_equipment_is_ignored(material: Material, sent: MagicMock) -> None:
    message = _bid(status={"targets": {"equipment": 99}}, id=f"EQUIPMENT:{TOPIC}:99:1")
    assert material.handle_bid_action(message) == "CONTINUE"
    sent.assert_not_called()


def test_bid_after_commitment_is_rejected_with_assigned(material: Material, sent: MagicMock) -> None:
    material.assigned_equipment = f"EQUIPMENT:{TOPIC}:4:1"
    assert material.handle_bid_action(_bid()) == "CONTINUE"
    assert _actions(sent) == ["ASSIGNED"]
    assert sent.call_args.kwargs["dest"] == EQUIPMENT_ID


def test_bid_without_a_known_route_is_ignored(sent: MagicMock) -> None:
    material = _make(params={**PARAMS, "current_equipment": 1}, transport_times={"1": {"2": 60}})
    assert material.handle_bid_action(_bid()) == "CONTINUE"
    sent.assert_not_called()


def test_counterbid_reports_arrival_and_lateness(sent: MagicMock) -> None:
    material = _make(params={**PARAMS, "current_equipment": 1}, transport_times={"1": {"3": 3600}})
    start = (datetime.now(timezone.utc)).strftime("%Y-%m-%dT%H:%M:%SZ")
    material.handle_bid_action(_bid(start_time=start))
    payload = sent.call_args.kwargs["payload"]
    assert payload["transfer_seconds"] == 3600
    assert payload["lateness_seconds"] == pytest.approx(3600, abs=5)   # arrives one hour after the equipment starts
    assert "arrival_time" in payload


# ---------------------------------------------------------------- ASKCONFIRM

def _askconfirm(equipment: str = EQUIPMENT_ID) -> dict:
    return {"topic": TOPIC, "payload": {"id": equipment, "costs": 1.5}}


def test_first_confirmation_commits_the_material_and_ends_its_loop(material: Material, sent: MagicMock) -> None:
    assert material.handle_askconfirm_action(_askconfirm()) == "END"
    assert material.assigned_equipment == EQUIPMENT_ID
    assert _actions(sent) == ["CONFIRM", "ASSIGNED"]
    confirm, assigned = (call.kwargs for call in sent.call_args_list)
    assert confirm["dest"] == EQUIPMENT_ID and confirm["payload"]["costs"] == 1.5
    # The broadcast must reach every other equipment of the auction, and not the winner
    import re
    assert re.search(assigned["dest"], f"EQUIPMENT:{TOPIC}:4:1")
    assert not re.search(assigned["dest"], EQUIPMENT_ID)


def test_confirmation_of_another_equipment_is_rejected(material: Material, sent: MagicMock) -> None:
    material.handle_askconfirm_action(_askconfirm())
    sent.reset_mock()
    other = f"EQUIPMENT:{TOPIC}:4:1"
    assert material.handle_askconfirm_action(_askconfirm(other)) == "CONTINUE"
    assert material.assigned_equipment == EQUIPMENT_ID           # the first commitment is kept
    assert _actions(sent) == ["ASSIGNED"] and sent.call_args.kwargs["dest"] == other


def test_repeated_confirmation_of_the_same_equipment_is_idempotent(material: Material, sent: MagicMock) -> None:
    material.handle_askconfirm_action(_askconfirm())
    assert material.handle_askconfirm_action(_askconfirm()) == "END"
    assert material.assigned_equipment == EQUIPMENT_ID


# ---------------------------------------------------------------- CREATE

def _create_message() -> dict:
    return {"topic": "dynAUCTION", "payload": {
        "id": "42", "params": PARAMS, "transport_times": {"1": {"2": 60}}, "coil_lengths": [3.0], "variables": {},
    }}


def test_create_launches_one_replica_container_for_the_auction(material: Material) -> None:
    material.handler = MagicMock()
    with patch.object(KeySearch, "assign_values"), patch.object(KeySearch, "dump_model", return_value={}):
        assert material.handle_create_action(_create_message()) == "CONTINUE"
    material.handler.launch_container.assert_called_once()
    kwargs = material.handler.launch_container.call_args.kwargs
    assert kwargs["auto_remove"] is True
    assert kwargs["name"] == "dynAUCTION_42" and kwargs["agent"] == "material" and kwargs["mode"] == "replica"
    assert kwargs["params"]["topic"] == "dynAUCTION" and kwargs["params"]["agent"] == "MATERIAL:dynAUCTION:42"
    assert kwargs["params"]["coil_lengths"] == [3.0]


def test_replicas_cannot_create_replicas() -> None:
    replica = _make(manager=False)
    assert replica.handler is None
    with pytest.raises(Exception, match="Replicas can't create new instances"):
        replica.handle_create_action(_create_message())
