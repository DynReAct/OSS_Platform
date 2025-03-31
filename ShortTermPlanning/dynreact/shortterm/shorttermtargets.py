from pydantic import BaseModel, Field, ConfigDict
from .timedelay import TimeDelay

class ShortTermTargets(BaseModel):
    """_summary_
    It aims to collect mainly configuration parameters required for the Auction System 
    to work, such as the kafka broker address, etc.

    Args:
        BaseModel (_type_): _description_
        IP: Kafka broker address
        TD: Timedelay
        TOPIC_GEN: Main topic for general clhannel comms
        VB: verbosity level
    """

    IP: str|None = Field(None, description="Kafka broker address.")
    TimeDelays: TimeDelay|None = Field(None, description="Delay recordset for Auction")
    TOPIC_GEN: str|None = Field(None, description="General Kafka topic for comm.")
    VB: int|None = Field(None, description="Verbosity Levels [0=> Nothing ... ]")

