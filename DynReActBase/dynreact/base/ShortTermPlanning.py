from pydantic import BaseModel, Field, ConfigDict
from dynreact.shortterm.shorttermtargets import ShortTermTargets
from dynreact.shortterm.timedelay import TimeDelay

class ShortTermPlanning:
    """
    Handling needed params to properly setup the STP context.
    """

    def __init__(self, uri: str):
        self._uri = uri
        uri = uri.lower()
        if not uri.startswith("default+file:"):
            raise Exception("Unexpected URI for file config provider: " + str(uri))
        self._file = uri[len("default+file:"):]
        js = None
        with open(self._file, "r", encoding="utf-8") as file:
            js = file.read()
        self._stpConfigParams: ShortTermTargets = ShortTermTargets.model_validate_json(js)


    def stp_config_params(self) -> ShortTermTargets:
        raise Exception("not implemented")

if __name__ == "__main__":
    provider = ShortTermPlanning("default+file:./data/stp_cotnext.json")
    print(provider.stp_config_params())
