"""Regression tests for order-level short-term equipment accounting."""

from datetime import datetime, timezone
from unittest.mock import patch

from dynreact.shortterm.agents.equipment import Equipment, material_weight_tons


def test_material_weight_tons_prefers_order_weight_over_coil_weight() -> None:
    """Target tonnage must be accumulated with the confirmed order weight."""
    material_params = {
        "weight": 8.5,
        "order": {
            "id": "order-1",
            "actual_weight": 23.0,
        },
    }

    assert material_weight_tons(material_params) == 23.0


def test_move_to_next_round_advances_time_with_total_order_length() -> None:
    """Equipment timing must advance with the full confirmed order length."""
    start_time = datetime(2026, 6, 27, 4, 0, 0, tzinfo=timezone.utc)
    equipment = Equipment(
        topic="auction-topic",
        agent="EQUIPMENT:auction-topic:VEA10:0",
        status={"planning": {}, "targets": {"equipment": 10}},
        operation_speed=2.0,
        start_time=start_time,
        current_order_length=12.0,
        target_tons=999.0,
        accumulated_tons=0.0,
        manager=False,
    )
    equipment.producer = None

    with patch("dynreact.shortterm.agents.equipment.get_new_equipment_status", return_value=equipment.status), patch.object(equipment, "handle_start_action", return_value="CONTINUE"):
        result = equipment.move_to_next_round({
            "id": "coil-1",
            "order": {
                "id": "order-1",
                "actual_weight": 20.0,
            }
        })

    assert result == "CONTINUE"
    assert equipment.accumulated_tons == 20.0
    assert equipment.start_time == datetime(2026, 6, 27, 4, 0, 6, tzinfo=timezone.utc)
    assert equipment.round_number == 1
    assert equipment.agent == "EQUIPMENT:auction-topic:VEA10:1"
