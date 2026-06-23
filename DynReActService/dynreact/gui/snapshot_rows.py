from __future__ import annotations

from datetime import datetime
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


def require_snapshot_rows_provider(provider: Any) -> SnapshotRowsProvider:
    """Accept RAS providers by type or by capability for compatibility bridges."""
    if RasSnapshotProvider is not None and isinstance(provider, RasSnapshotProvider):
        return cast(SnapshotRowsProvider, provider)
    if callable(getattr(provider, "get_snapshot_rows", None)):
        return cast(SnapshotRowsProvider, provider)
    raise ValueError(
        "The HTTP energy backend requires a snapshot provider exposing get_snapshot_rows()."
    )
