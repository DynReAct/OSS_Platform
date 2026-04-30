"""Test support and regression coverage for OSS_Platform/ShortTermPlanning/tests/unit_tests/conftest.

The module is documented in English to make the short-term planning
workflow easier to maintain across OSS and RAS-specific integrations.
"""

from collections.abc import Generator
from typing import Any
import pytest
import re
import sys
from datetime import datetime
from unittest.mock import patch, MagicMock


# Define a function to return different responses based on input URL
def mock_load_url_json_get(url: Any, *args: Any, **kwargs: Any) -> Any:
    """Mock load url json get.
    
    This function is part of the short-term planning workflow and keeps
    the existing runtime behavior while documenting the public contract.
    
    Args:
        url: Input value for the `url` parameter.
        *args: Input value for the `args` parameter.
        **kwargs: Input value for the `kwargs` parameter.
    
    Returns:
        The value produced by the underlying planning, UI, or test helper logic.
    """
    if re.search(r"/snapshots$", url) is not None:
        return ["mock"]
    elif re.search(r"/snapshots/*", url) is not None:
        return {
            "orders": [
                {
                    "id": 1
                }
            ],
            "material": [
                {
                    "id": 101,
                    "order": 1,
                    "current_equipment": 201
                }
            ]
        }
    elif re.search("/costs/status/*", url) is None:
        return {"default": "response"}
    else:
        dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
        raise Exception(f"{dt} | ERROR: URL is not defined: {url}")

# ================ MATERIAL ================

# Apply patches at module level BEFORE importing `Material`
with patch("dynreact.shortterm.common.data.load_url.load_url_json_get", side_effect=mock_load_url_json_get):
    with patch("confluent_kafka.Producer") as mock_producer_class:
        with patch("confluent_kafka.Consumer") as mock_consumer_class:  # Fixed syntax

            mock_producer_instance = MagicMock()
            mock_consumer_instance = MagicMock()

            mock_producer_class.return_value = mock_producer_instance
            mock_consumer_class.return_value = mock_consumer_instance

            # Now import Material AFTER Kafka is patched
            from dynreact.shortterm.agents import material as material_module

            sys.modules.setdefault("material", material_module)
            Material = material_module.Material

            from dynreact.shortterm.common import KeySearch
            from dynreact.shortterm.shorttermtargets import ShortTermTargets

            KeySearch.set_global(
                ShortTermTargets(
                    KAFKA_IP="127.0.0.1:9092",
                    REST_URL="http://localhost",
                    PERF_URL="http://localhost",
                    TRANSPORT_TIMES_URL="http://localhost",
                    VB=3,
                )
            )


@pytest.fixture
def mock_kafka() -> Generator[tuple[MagicMock, MagicMock], None, None]:
    """Fixture to provide mocked Kafka objects to tests."""
    yield mock_producer_instance, mock_consumer_instance

@pytest.fixture
def material_agent(mock_kafka: Any) -> Any:
    """Fixture to create a Material agent instance for testing."""
    topic = "topic1"
    agent = "Material_Agent"
    params = {"param1": "value1", "order": {"allowed_equipment": ["equip1", "equip2"], "due_date": "2023-12-31T23:59:59"}}
    material = Material(topic=topic, agent=agent, params=params)

    # Assign mocked Kafka objects so they can be traced in tests
    material.producer = mock_kafka[0]
    material.consumer = mock_kafka[1]

    return material
