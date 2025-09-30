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

    def transfer_new(self,
                 lot: Lot,
                 snapshot: Snapshot,
                 external_id: str|None = None,
                 comment: str|None = None) -> str:
        raise Exception("not implemented")

    def transfer_append(self,
                        lot: Lot,
                        start_order: str,
                        snapshot: Snapshot) -> str:
        """
        :param lot:
        :param start_order: first order to be transferred
        :param snapshot:
        :return: lot id
        """
        raise Exception("not implemented")

