from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

try:
    from dynreact.snapshot.ras import RasSnapshotProvider
except Exception:
    RasSnapshotProvider = None


class SnapshotRowsProvider(Protocol):
    """Snapshot provider protocol for raw RAS row access."""

    def get_snapshot_rows(self, snapshot: datetime | None = None) -> list[dict[str, str]]:
        """Return raw snapshot rows for an optional snapshot timestamp."""
        ...


class _LegacySnapshotRowsProvider:
    """Compatibility adapter for RAS providers without get_snapshot_rows()."""

    def __init__(self, provider: Any):
        self._provider = provider

    def get_snapshot_rows(self, snapshot: datetime | None = None) -> list[dict[str, str]]:
        snapshot_id = self._resolve_snapshot_id(snapshot)
        if snapshot_id is None:
            return []
        file_name = self._resolve_snapshot_file(snapshot_id)
        if file_name is None:
            return []
        with Path(file_name).open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            return [
                {str(key): "" if value is None else str(value) for key, value in row.items()}
                for row in reader
            ]

    def _resolve_snapshot_id(self, snapshot: datetime | None) -> datetime | None:
        find_time = getattr(self._provider, "_find_time", None)
        if callable(find_time):
            return find_time(snapshot)
        current_snapshot_id = getattr(self._provider, "current_snapshot_id", None)
        if callable(current_snapshot_id):
            return current_snapshot_id() if snapshot is None else snapshot
        return snapshot

    def _resolve_snapshot_file(self, snapshot_id: datetime) -> str | None:
        snapshot_files = getattr(self._provider, "_snapshot_files", None)
        if not isinstance(snapshot_files, dict) or snapshot_id not in snapshot_files:
            snapshots = getattr(self._provider, "snapshots", None)
            if callable(snapshots):
                list(
                    snapshots(
                        datetime.fromtimestamp(0, tz=snapshot_id.tzinfo),
                        datetime.fromtimestamp(9_999_999_999, tz=snapshot_id.tzinfo),
                    )
                )
                snapshot_files = getattr(self._provider, "_snapshot_files", None)
        if isinstance(snapshot_files, dict):
            file_name = snapshot_files.get(snapshot_id)
            if file_name:
                return str(file_name)
        file_name = getattr(self._provider, "_file", None)
        return str(file_name) if file_name else None


def require_snapshot_rows_provider(provider: Any) -> SnapshotRowsProvider:
    """Accept RAS providers by type or by capability for compatibility bridges."""
    if RasSnapshotProvider is not None and isinstance(provider, RasSnapshotProvider):
        return cast(SnapshotRowsProvider, provider)
    if callable(getattr(provider, "get_snapshot_rows", None)):
        return cast(SnapshotRowsProvider, provider)
    if callable(getattr(provider, "_find_time", None)) and (
        isinstance(getattr(provider, "_snapshot_files", None), dict) or getattr(provider, "_file", None) is not None
    ):
        return cast(SnapshotRowsProvider, _LegacySnapshotRowsProvider(provider))
    raise ValueError(
        "The HTTP energy backend requires a snapshot provider exposing get_snapshot_rows()."
    )
