import json
from unittest.mock import patch, MagicMock


@patch('material.Pool')  # Patch Pool inside material.py
def test_handle_create_action(mock_pool, material_agent):
    """
    Makes sure materials are created successfully.
    """
    # Mock apply_async to do nothing
    mock_instance = MagicMock()
    mock_pool.return_value = mock_instance
    mock_instance.apply_async.return_value = None  # Prevent actual execution
    mock_instance.apply_async.close = None  # Prevent actual execution

    dctmsg = {
        "topic": material_agent.topic,
        "payload": {
            "id": 101,
        }
    }

    result = material_agent.handle_create_action(dctmsg)

    assert result == "CONTINUE"
    mock_pool.assert_called_once()  # Ensure Pool was used
    mock_instance.apply_async.assert_called_once()  # Ensure apply_async was triggered

    assert material_agent.producer.produce.call_count == 2

    expected_msg = [
        "Finished creating the agent Material_Agent with parameters",  # Part of message
        "Creating material with configuration",  # Part of message
    ]

    actual_calls = [json.loads(call.kwargs["value"])["payload"]["msg"] for call in
                    material_agent.producer.produce.call_args_list]

    for idx, msg in enumerate(actual_calls):
        assert expected_msg[idx] in msg


@patch("material.calculate_bidding_price", return_value=250.0)
@patch("material.sendmsgtopic", return_value=None)
def test_handle_valid_bid_action(mock_sendmsgtopic, _, material_agent):
    """
    Test whether the bid action is handled correctly when you have a price.
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
def test_handle_invalid_bid_action(mock_sendmsgtopic, _, material_agent):
    """
    Test whether the bid action is handled correctly when you don't have a price.
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

    mock_sendmsgtopic.assert_not_called()


@patch("material.sendmsgtopic")
def test_handle_askconfirm_action(mock_sendmsgtopic, material_agent):
    """
    Test whether the ASKCONFIRM action is handled correctly.
    """
    dctmsg = {
        "topic": material_agent.topic,
        "payload": {
            "id": "equip1"
        }
    }

    result = material_agent.handle_askconfirm_action(dctmsg)

    assert result == "END"

    mock_sendmsgtopic.assert_called_once_with(
        producer=material_agent.producer,
        tsend=dctmsg['topic'],
        topic=dctmsg['topic'],
        source=material_agent.agent,
        dest=f'^(?!{dctmsg['payload']['id']})(EQUIPMENT:{material_agent.topic}:.*)$',
        action="ASSIGNED",
        payload={'id': material_agent.agent},
        vb=material_agent.verbose
    )

    assert material_agent.assigned_equipment == "equip1"
    material_agent.handle_sendassigned_action.assert_called_once()

    assert material_agent.producer.produce.call_count == 2

    expected_msg = [
        "Assigned material to equipment equip1. Sending ASSIGNED message...",
        "Assigned material to equipment equip1 and sent ASSIGNED message. Killing the agent..."
    ]

    actual_calls = [json.loads(call.kwargs["value"]) for call in material_agent.producer.produce.call_args_list]

    for idx, msg in enumerate(actual_calls):
        assert expected_msg[idx] in msg["payload"]["msg"]
