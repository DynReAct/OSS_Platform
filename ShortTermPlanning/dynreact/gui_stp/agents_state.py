from dynreact.shortterm.common import KeySearch
from dynreact.shortterm.ShortTermPlanning import ShortTermPlanning


class AgentsState:

    def __init__(self):
        self._short_term_planning: Any | None = None
        self._auction_obj: Any | None = None  # auction.Auction | None = None
        self._stp: Any | None = None  # ShortTermPlanning | None = None

    def get_auction_obj(self):
        if self._auction_obj is not None:
            return(self._auction_obj)
        return None

    def set_auction_obj(self, auction) -> None:
        if self._auction_obj is None:
            self._auction_obj = auction

    def set_stp_config(self) -> None:
        if self._stp is None:
            self._stp = self.get_stp_config_params()

    #def get_stp_context_params(self):
    #    self.set_stp_config()
    #    return (self._stp._stpConfigParams.KAFKA_IP, self._stp._stpConfigParams.TOPIC_GEN,
    #            self._stp._stpConfigParams.VB)

    def get_stp_context_params(self):
        self.set_stp_config()
        return (KeySearch.search_for_value("KAFKA_IP"), KeySearch.search_for_value("TOPIC_GEN"),
                KeySearch.search_for_value("TOPIC_CALLBACK"), KeySearch.search_for_value("VB"))

    def get_stp_context_timing(self):
        self.set_stp_config()
        return (self._stp._stpConfigParams.TimeDelays.AUCTION_WAIT,
                self._stp._stpConfigParams.TimeDelays.COUNTERBID_WAIT,
                self._stp._stpConfigParams.TimeDelays.CLONING_WAIT,
                self._stp._stpConfigParams.TimeDelays.EXIT_WAIT,
                self._stp._stpConfigParams.TimeDelays.SMALL_WAIT)

    def get_stp_config_params(self) -> ShortTermPlanning:
        if not self._short_term_planning:
            self._short_term_planning = ShortTermPlanning()
        return self._short_term_planning
        ## previously in DynReActService -> plugins.py; but is this apparatus needed, at all?
        #if self._short_term_planning is None:
        #    if self._config.short_term_planning.startswith("default+file:"):
        #        self._short_term_planning = ShortTermPlanning(self._config.short_term_planning)
        #    else:
        #        self._short_term_planning = Plugins._load_module("dynreact.shorttermplanning", ShortTermPlanning, self._config.short_term_planning)
        #return self._short_term_planning
