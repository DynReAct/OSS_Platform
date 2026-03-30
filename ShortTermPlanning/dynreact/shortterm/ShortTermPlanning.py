from dynreact.shortterm.shorttermtargets import ShortTermTargets
from dynreact.shortterm.common import KeySearch

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
        KeySearch.set_global(config_provider=self._stpConfigParams)


    def stp_config_params(self) -> ShortTermTargets:
        return self._stpConfigParams

    def stp_context_params(self) -> tuple[object, object, object, object]:
        return (
            KeySearch.search_for_value("KAFKA_IP"),
            KeySearch.search_for_value("TOPIC_GEN"),
            KeySearch.search_for_value("TOPIC_CALLBACK"),
            KeySearch.search_for_value("VB"),
        )

    def stp_context_timing(self) -> tuple[object, object, object, object, object]:
        time_delays = self._stpConfigParams.TimeDelays
        return (
            time_delays.AUCTION_WAIT,
            time_delays.COUNTERBID_WAIT,
            time_delays.CLONING_WAIT,
            time_delays.EXIT_WAIT,
            time_delays.SMALL_WAIT,
        )

if __name__ == "__main__":
    provider = ShortTermPlanning("default+file:./data/stp_context.json")
    print(provider.stp_config_params())
