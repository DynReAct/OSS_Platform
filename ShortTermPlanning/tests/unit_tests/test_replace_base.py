"""Unit tests for replace_base safety guards."""

import pytest

from dynreact.shortterm.replace_base import _validate_safe_replace_base_context


def test_validate_safe_replace_base_context_accepts_oss_test_profile() -> None:
    """OSS test contexts should remain eligible for replace_base."""
    resolved_profile = _validate_safe_replace_base_context(
        topic_gen="DynReact-OSS-TEST-Gen",
        topic_callback="DynReact-OSS-TEST-Callback",
        topic_prefix="Dynreact_OSS",
        expected_profile="oss",
    )

    assert resolved_profile == "oss"


def test_validate_safe_replace_base_context_accepts_ras_test_profile() -> None:
    """RAS test contexts should remain eligible for replace_base."""
    resolved_profile = _validate_safe_replace_base_context(
        topic_gen="Dynreact-RAS-TEST-Gen",
        topic_callback="Dynreact-RAS-TEST-Callback",
        topic_prefix="Dynreact_RAS",
        expected_profile="ras",
    )

    assert resolved_profile == "ras"


def test_validate_safe_replace_base_context_rejects_non_test_topics() -> None:
    """Production-like topics must never be cleaned by replace_base."""
    with pytest.raises(RuntimeError, match="restricted to TEST contexts"):
        _validate_safe_replace_base_context(
            topic_gen="Dynreact-RAS-Gen",
            topic_callback="Dynreact-RAS-Callback",
            topic_prefix="Dynreact_RAS",
            expected_profile="ras",
        )


def test_validate_safe_replace_base_context_rejects_profile_mismatch() -> None:
    """One OSS Jenkins job must not act on a RAS test context."""
    with pytest.raises(RuntimeError, match="profile mismatch"):
        _validate_safe_replace_base_context(
            topic_gen="Dynreact-RAS-TEST-Gen",
            topic_callback="Dynreact-RAS-TEST-Callback",
            topic_prefix="Dynreact_RAS",
            expected_profile="oss",
        )
