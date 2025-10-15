import os

from dynreact.base.LotSink import LotSink
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.impl.PathUtils import PathUtils
from dynreact.base.model import Site, Lot, Snapshot, ServiceMetrics, PrimitiveMetric


class FileLotSink(LotSink):

    def __init__(self, uri: str, site: Site):
        super().__init__(uri, site)
        uri_lower = uri.lower()
        if not uri_lower.startswith("default+file:"):
            raise NotApplicableException("Unexpected URI for file file lot sink: " + str(uri))
        folder = uri[len("default+file:"):]
        self._folder = os.path.join(folder, "lots") if not folder.lower().endswith("lots") else folder
        os.makedirs(self._folder, exist_ok=True)
        self._transfers: int = 0
        self._error_count: int = 0
        self._lots_count: int = 0

    def id(self) -> str:
        return self._url

    def label(self, lang: str="en") -> str:
        return "File lot storage"

    def description(self, lang: str="en") -> str|None:
        return "Stores lots in json files; mainly for dev purposes."

    def transfer_new(self, lot: Lot,
                 snapshot: Snapshot,
                 external_id: str|None = None,
                 comment: str|None = None):
        self._transfers += 1
        try:
            json_str = lot.model_dump_json(exclude_none=True, exclude_unset=True)
            id = external_id if external_id is not None else lot.id
            filename = PathUtils.to_valid_filename(id)
            filepath = os.path.join(self._folder, filename + ".json")
            with open(filepath, mode="w") as file:
                file.write(json_str)
            self._lots_count += 1
            return id
        except:
            self._error_count += 1
            raise

    def transfer_append(self, lot: Lot,
                        start_order: str,
                        snapshot: Snapshot):
        self._transfers += 1
        try:
            start_idx = lot.orders.index(start_order)
            filename = PathUtils.to_valid_filename(lot.id)
            filepath = os.path.join(self._folder, filename + ".json")
            with open(filepath, mode="r") as file:
                existing_lot = Lot.model_validate_json(file.read())
            existing_lot.orders = existing_lot.orders + lot.orders[start_idx:]
            json_str = existing_lot.model_dump_json(exclude_none=True, exclude_unset=True)
            with open(filepath, mode="w") as file:
                file.write(json_str)
            self._lots_count += 1
            return existing_lot.id or lot.id
        except:
            self._error_count += 1
            raise

    def metrics(self) -> ServiceMetrics:
        # it is recommended to have at least the following metrics (counters):
        # transfers_total, lots_transferred_total, transfer_errors_total
        labels = {"sink": "file"}
        metrics = (
            PrimitiveMetric(id="transfers_total", value=self._transfers, labels=labels),
            PrimitiveMetric(id="lots_transferred_total", value=self._lots_count, labels=labels),
            PrimitiveMetric(id="transfer_errors_total", value=self._error_count, labels=labels),
        )
        return ServiceMetrics(service_id="midtermplanning_lotsink", metrics=metrics)
