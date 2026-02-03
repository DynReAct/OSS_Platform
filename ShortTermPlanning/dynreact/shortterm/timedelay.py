from pydantic import BaseModel, Field, ConfigDict

class TimeDelay(BaseModel):
    """_summary_
    Defines the different time delays which could be needed for Auction operation.

    Args:
        AUCTION_WAIT: Auction wait after starting
        RUNNING_WAIT: Running wait after launching base agents
        COUNTERBID_WAIT: Counterbid wait
        CLONING_WAIT: Cloning wait after launching the auction
        EXIT_WAIT: Exit wait before removing the base agents
        SMALL_WAIT: General purpose waiting period
    """
    AUCTION_WAIT: int | None = Field(None, description="Auction Wait to start in seconds")
    COUNTERBID_WAIT: int | None = Field(None, description="Counterbid Wait to decide in seconds")
    CLONING_WAIT: int | None = Field(None, description="Agent cloninig Wait in seconds")
    EXIT_WAIT: int | None = Field(None, description="Auction Wait to exit in seconds")
    RUNNING_WAIT: int | None = Field(None, description="Running wait in seconds")
    SMALL_WAIT: int | None = Field(5, description="Small Wait to accomodate processes in seconds")