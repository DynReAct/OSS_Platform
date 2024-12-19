
from pydantic import BaseModel, Field, ConfigDict

class TimeDelay(BaseModel):
    """_summary_
    Defines the different time delays which could be needed for Auction operation.

    Args:
        AW: auction wait
        BW: Counterbid wait
        CW: Cloning wait
        EW: Exit wait
        SMALL_WAIT: General purpose waiting period
    """
    AW: int | None = Field(None, description="Auction Wait to start in seconds")
    BW: int | None = Field(None, description="Counterbid Wait to decide in seconds")
    CW: int | None = Field(None, description="Agent cloninig Wait in seconds")
    EW: int | None = Field(None, description="Auction Wait to exit in seconds")
    SMALL_WAIT: int|None = Field(None, description="Small Wait to accomodate processes in seconds")    

    

