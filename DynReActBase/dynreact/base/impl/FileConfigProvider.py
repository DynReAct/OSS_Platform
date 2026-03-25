from dynreact.base.ConfigurationProvider import ConfigurationProvider
from dynreact.base.NotApplicableException import NotApplicableException

from dynreact.base.model import Site


class FileConfigProvider(ConfigurationProvider):
    """
    Read configuration from json files
    """
    def __init__(self, uri: str):
        super().__init__(uri)
        # Only lowercase the scheme part, NOT the file path (which is case-sensitive)
        scheme_part = "default+file:"
        if uri.lower().startswith(scheme_part):
            # Extract path preserving its original case
            file_path = uri[len(scheme_part):]
        else:
            raise NotApplicableException("Unexpected URI for file config provider: " + str(uri))
        
        self._file = file_path
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

