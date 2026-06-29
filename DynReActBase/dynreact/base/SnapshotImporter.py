from datetime import datetime, timedelta

from dynreact.base.SnapshotProvider import SnapshotProvider


class SnapshotImporter(SnapshotProvider):
    """
    This class provides additional methods that a SnapshotProvider can choose to implement, indicating that it
    regularly imports snapshots from some external source. The methods allow the user to
    check for the next scheduled snapshot import time and to trigger a new import. The SnapshotProvider need not
    extend this base class for this purpose.
    """

    def interval(self) -> timedelta:
        """
        Returns:
            The import interval
        """
        raise Exception("not implemented")

    def next_scheduled_import(self) -> datetime|None:
        """
        Returns:
            the timestamp of the next scheduled import, if any
        """
        raise Exception("not implemented")

    def trigger_import(self) -> datetime:
        """
        The implementation may choose to raise a SnapshotImportError if the import is not currently possible,
        e.g., because a connection to the database could not be established, an import is already ongoing (in which case
        the currently retrieved snapshot should ideally be returned) or another import had been triggered too recently.
        This is a blocking operation.

        Returns:
            the new snapshot timestamp
        """
        raise Exception("not implemented")

    def pause(self):
        """Pause the imports."""
        raise Exception("not implemented")

    def resume(self):
        """Resume imports, if paused."""
        raise Exception("not implemented")

    def is_paused(self) -> bool:
        """
        Returns:
            a boolean flag indicating whether imports are currently paused
        """
        raise Exception("not implemented")

    def import_running(self) -> bool:
        """
        Returns:
            a boolean flag indicating whether an import is currently active/running.
        """
        raise Exception("not implemented")


class SnapshotImportError(BaseException):
    pass

