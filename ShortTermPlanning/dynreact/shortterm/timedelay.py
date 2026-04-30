"""Short-term planning integration module for OSS_Platform/ShortTermPlanning/dynreact/shortterm/timedelay.

The module is documented in English to make the short-term planning
workflow easier to maintain across OSS and RAS-specific integrations.
"""

from pydantic import BaseModel, Field

class TimeDelay(BaseModel):
    """Time delays used by the short-term planning orchestration.

    Attributes:
        AUCTION_WAIT: Delay before the auction starts.
        COUNTERBID_WAIT: Delay allowed for counter-bids.
        CLONING_WAIT: Delay after launching agent replicas.
        EXIT_WAIT: Delay before stopping the agents.
        RUNNING_WAIT: Delay after launching base agents.
        SMALL_WAIT: Small generic wait used to settle background activity.
    """

    AUCTION_WAIT: int | None = Field(default=None, description="Auction wait to start in seconds.")
    COUNTERBID_WAIT: int | None = Field(default=None, description="Counterbid wait in seconds.")
    CLONING_WAIT: int | None = Field(default=None, description="Agent cloning wait in seconds.")
    EXIT_WAIT: int | None = Field(default=None, description="Auction wait to exit in seconds.")
    RUNNING_WAIT: int | None = Field(default=None, description="Running wait in seconds.")
    SMALL_WAIT: int | None = Field(default=5, description="General-purpose wait in seconds.")
