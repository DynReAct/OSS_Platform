from dynreact.base.model import Lot, Site, Snapshot


class LotSink:
    """
    @beta
    Implementation expected in dynreact.lots.LotSinkImpl
    """

    def __init__(self, url: str, site: Site):
        self._url = url
        self._site = site

    def id(self) -> str:
        raise Exception("not implemented")

    def label(self, lang: str = "en") -> str:
        return self.id()

    def description(self, lang: str = "en") -> str | None:
        return None

    def transfer(self,
                 lot: Lot,
                 snapshot: Snapshot,
                 external_id: str|None = None,
                 comment: str|None = None):
        raise Exception("not implemented")
