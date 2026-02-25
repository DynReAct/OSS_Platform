import os
from typing import Sequence

from dynreact.base.LotSink import LotSink
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.PermissionManager import PermissionManager
from dynreact.base.impl.PathUtils import PathUtils
from dynreact.base.model import Site, Lot, Snapshot, ServiceMetrics, PrimitiveMetric


class FileLotSink(LotSink):

    def __init__(self, uri: str, site: Site, permissions: PermissionManager):
        super().__init__(uri, site, permissions)
        uri_lower = uri.lower()
        if not uri_lower.startswith("default+file:"):
            raise NotApplicableException("Unexpected URI for file file lot sink: " + str(uri))
        folder = uri[len("default+file:"):]
        self._folder = os.path.join(folder, "lots") if not folder.lower().endswith("lots") else folder
        os.makedirs(self._folder, exist_ok=True)
        # keys: process id  #
        self._transfers: dict[str, int] = {}
        self._error_count: dict[str, int] = {}
        self._lots_count: dict[str, int] = {}

    def id(self) -> str:
        return self._url

    def label(self, lang: str="en") -> str:
        return "File lot storage"

    def description(self, lang: str="en") -> str|None:
        return "Stores lots in json files; mainly for dev purposes."

    @staticmethod
    def _increase_stat(process: str, stat: dict[str, int]):
        if process not in stat:
            stat[process] = 1
        else:
            stat[process] += 1

    def transfer_new(self, lot: Lot,
                 snapshot: Snapshot,
                 material: dict[str, Sequence[str]] | None = None,
                 external_id: str|None = None,
                 comment: str|None = None,
                 user: str|None = None):
        process = self._site.get_equipment(lot.equipment, do_raise=True).process
        FileLotSink._increase_stat(process, self._transfers)
        try:
            json_str = lot.model_dump_json(exclude_none=True, exclude_unset=True)
            if user is not None:
                json_str = json_str[:json_str.rindex("}")] + f", \"__user__\": \"{user}\"}}"
            id = external_id if external_id is not None else lot.id
            filename = PathUtils.to_valid_filename(id)
            filepath = os.path.join(self._folder, filename + ".json")
            with open(filepath, mode="w") as file:
                file.write(json_str)
            FileLotSink._increase_stat(process, self._lots_count)
            return id
        except:
            FileLotSink._increase_stat(process, self._error_count)
            raise

    def transfer_append(self, lot: Lot,
                        start_order: str,
                        snapshot: Snapshot,
                        material: dict[str, Sequence[str]] | None = None,
                        user: str|None = None):
        process = self._site.get_equipment(lot.equipment, do_raise=True).process
        FileLotSink._increase_stat(process, self._transfers)
        try:
            start_idx = lot.orders.index(start_order)
            filename = PathUtils.to_valid_filename(lot.id)
            filepath = os.path.join(self._folder, filename + ".json")
            with open(filepath, mode="r") as file:
                existing_lot = Lot.model_validate_json(file.read())
            existing_lot.orders = existing_lot.orders + lot.orders[start_idx:]
            json_str = existing_lot.model_dump_json(exclude_none=True, exclude_unset=True)
            if user is not None:
                json_str = json_str[:json_str.rindex("}")] + f", \"__user__\": \"{user}\"}}"
            with open(filepath, mode="w") as file:
                file.write(json_str)
            FileLotSink._increase_stat(process, self._lots_count)
            return existing_lot.id or lot.id
        except:
            FileLotSink._increase_stat(process, self._error_count)
            raise

    def metrics(self) -> ServiceMetrics:
        # it is recommended to have at least the following metrics (counters):
        # transfers_total, lots_transferred_total, transfer_errors_total
        labels = {"sink": "file"}
        metrics = []
        for proc, cnt in self._transfers.items():
            labs = {**labels, "process": proc}
            metrics.append(PrimitiveMetric(id="transfers_total", value=cnt, labels=labs))
        for proc, cnt in self._lots_count.items():
            labs = {**labels, "process": proc}
            metrics.append(PrimitiveMetric(id="lots_transferred_total", value=cnt, labels=labs))
        for proc, cnt in self._error_count.items():
            labs = {**labels, "process": proc}
            metrics.append(PrimitiveMetric(id="transfer_errors_total", value=cnt, labels=labs))
        return ServiceMetrics(service_id="midtermplanning_lotsink", metrics=metrics)
