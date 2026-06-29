from typing import Sequence

from dynreact.base.PermissionManager import PermissionManager
from dynreact.base.model import Lot, Site, Snapshot
from dynreact.base.monitoring import ServiceMetrics


class LotSink:

    def __init__(self, url: str, site: Site, permissions: PermissionManager):
        self._url = url
        self._site = site
        self._permissions = permissions

    def id(self) -> str:
        raise Exception("not implemented")

    def label(self, lang: str = "en") -> str:
        return self.id()

    def description(self, lang: str = "en") -> str | None:
        return None

    def transfer_new(self,
                 lot: Lot,
                 snapshot: Snapshot,
                 material: dict[str, Sequence[str]]|None=None,
                 external_id: str|None = None,
                 comment: str|None = None,
                 user: str|None=None) -> str:
        """
        Parameters:
            lot: the lot to be transferred
            snapshot: the snapshot the new lots are based on
            material: optional dictionary order id -> list of material ids
            external_id: optional external id
            comment: optional lot comment
            user: user id responsible for the lot transfer

        Returns:
            New lot id
        """
        raise Exception("not implemented")

    def transfer_append(self,
                        lot: Lot,
                        start_order: str,
                        snapshot: Snapshot,
                        material: dict[str, Sequence[str]] | None = None,
                        user: str|None=None) -> str:
        """
        Parameters:
            lot: the lot to be transferred
            start_order: first order to be transferred
            snapshot: the snapshot the new lots are based on
            material: optional dictionary order id -> list of material ids
            user: user id responsible for the lot transfer

        Returns:
            New lot id
        """
        raise Exception("not implemented")

    def required_permission(self) -> str|None:
        return None

    def metrics(self) -> ServiceMetrics:
        # Overwrite in derived sink; it is recommended to have at least the following metrics (counters):
        # transfers_total, lots_transferred_total, transfer_errors_total
        # use labels to distinguish different types of lot sinks
        return ServiceMetrics(service_id="midtermplanning_lotsink", metrics=[])

