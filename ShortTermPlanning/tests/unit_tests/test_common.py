import json
from unittest.mock import patch, MagicMock

@patch("material.calculate_bidding_price", return_value=250.0)
@patch("material.sendmsgtopic", return_value=None)
def test_handle_bid_action_valid_bidding_price(mock_calculate_bidding_price, mock_sendmsgtopic, material_agent):
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
def test_handle_bid_action_rejected_offer(mock_sendmsgtopic, mock_calculate_bidding_price, material_agent):
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
def test_handle_bid_action_with_no_previous_price(mock_calculate_bidding_price, mock_sendmsgtopic, material_agent):
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
