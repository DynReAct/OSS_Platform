"""Test support and regression coverage for OSS_Platform/ShortTermPlanning/tests/unit_tests/test_common.

The module is documented in English to make the short-term planning
workflow easier to maintain across OSS and RAS-specific integrations.
"""

import os
from unittest.mock import patch

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
