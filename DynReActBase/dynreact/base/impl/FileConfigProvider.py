from dynreact.base.ConfigurationProvider import ConfigurationProvider

from dynreact.base.model import Site


class FileConfigProvider(ConfigurationProvider):
    """
    Read configuration from json files
    """
    def __init__(self, uri: str):
        super().__init__(uri)
        uri = uri.lower()
        if not uri.startswith("default+file:"):
            raise Exception("Unexpected URI for file config provider: " + str(uri))
        self._file = uri[len("default+file:"):]
        js = None
        with open(self._file, "r", encoding="utf-8") as file:
            js = file.read()
        self._site: Site = Site.model_validate_json(js)

    # @override
    def site_config(self) -> Site:
        return self._site


if __name__ == "__main__":
    provider = FileConfigProvider("default+file:./data/sample/site.json")
    print(provider.site_config())

