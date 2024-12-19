from dynreact.base.model import Site


class ConfigurationProvider:
    """
    Implementation expected in package dynreact.config.ConfigurationProviderImpl
    """

    def __init__(self, url: str):
        self._url = url

    def site_config(self) -> Site:
        raise Exception("not implemented")
