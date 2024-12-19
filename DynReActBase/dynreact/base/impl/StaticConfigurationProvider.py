from dynreact.base.ConfigurationProvider import ConfigurationProvider
from dynreact.base.model import Site


class StaticConfigurationProvider(ConfigurationProvider):

    def __init__(self, site: Site):
        super().__init__("static")
        self._site = site

    def site_config(self) -> Site:
        return self._site
