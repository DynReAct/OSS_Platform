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
    SMALL_WAIT: int | None = Field(5, description="Small Wait to accomodate processes in seconds")

class ColumnDef(BaseModel):
    """_summary_
    Defines the columns to be shown.

    Args:
       pos01: First column
       pos02: Second column
       ...
       pos20: Twenty column
    """
    pos01: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos02: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos03: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos04: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos05: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos06: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos07: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos08: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos09: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos10: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos11: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos12: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos13: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos14: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos15: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos16: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos17: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos18: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos19: dict | None = Field(None, description="First column definition with headerName, field, pinned")
    pos20: dict | None = Field(None, description="First column definition with headerName, field, pinned")
