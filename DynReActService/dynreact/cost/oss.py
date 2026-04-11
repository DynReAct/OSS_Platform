from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.impl.SimpleCostProvider import SimpleCostProvider
from dynreact.base.model import Site


class OssCostProvider(SimpleCostProvider):
    """
    Minimal OSS cost provider compatible with the unified profile loader.
    """

    def __init__(self, uri: str | None, site: Site):
        if uri is None:
            uri = "oss:costs"
        if not uri.startswith("oss:"):
            raise NotApplicableException(
                "Unexpected URI for OSS cost provider: " + str(uri)
            )

        super().__init__("simple:costs", site)
        self._url = uri
