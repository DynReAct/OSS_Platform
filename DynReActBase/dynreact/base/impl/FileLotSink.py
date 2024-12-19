import os

from dynreact.base.LotSink import LotSink
from dynreact.base.impl.PathUtils import PathUtils
from dynreact.base.model import Site, Lot, Snapshot


class FileLotSink(LotSink):

    def __init__(self, uri: str, site: Site):
        super().__init__(uri, site)
        uri_lower = uri.lower()
        if not uri_lower.startswith("default+file:"):
            raise Exception("Unexpected URI for file file lot sink: " + str(uri))
        folder = uri[len("default+file:"):]
        self._folder = os.path.join(folder, "lots") if not folder.lower().endswith("lots") else folder
        os.makedirs(self._folder, exist_ok=True)

    def id(self) -> str:
        return self._url;

    def label(self, lang: str="en") -> str:
        return "File lot storage"

    def description(self, lang: str="en") -> str|None:
        return "Stores lots in json files; mainly for dev purposes."

    def transfer(self, lot: Lot,
                 snapshot: Snapshot,
                 external_id: str|None = None,
                 comment: str|None = None):
        json_str = lot.model_dump_json(exclude_none=True, exclude_unset=True)
        id = external_id if external_id is not None else lot.id
        filename = PathUtils.to_valid_filename(id)
        filepath = os.path.join(self._folder, filename + ".json")
        with open(filepath, mode="w") as file:
            file.write(json_str)

