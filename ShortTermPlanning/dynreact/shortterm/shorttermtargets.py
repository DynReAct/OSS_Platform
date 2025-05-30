from pydantic import BaseModel, Field, ConfigDict

from dynreact.shortterm.timedelay import TimeDelay


class ShortTermTargets(BaseModel):
    """_summary_
    It aims to collect mainly configuration parameters required for the Auction System 
    to work, such as the kafka broker address, etc.

    Args:
        BaseModel (_type_): _description_
        IP: Kafka broker address
        TD: Timedelay
        TOPIC_GEN: Main topic for general channel comms
        TOPIC_CALLBACK: Main topic for general channel callbacks
        LOG_FILE_PATH: Log file path
        REST_URL: REST API URL
        VB: verbosity level
    """

    IP: str | None = Field(None, description="Kafka broker address.")
    TimeDelays: TimeDelay | None = Field(TimeDelay(), description="Delay recordset for Auction")
    TOPIC_GEN: str | None = Field("DynReact-Gen", description="General Kafka topic for comm.")
    TOPIC_CALLBACK: str | None = Field("DynReact-Callback", description="General Kafka topic for callbacks.")
    LOG_FILE_PATH: str | None = Field(None, description="Log file path.")
    REST_URL: str | None = Field(None, description="REST API URL.")
    VB: int | None = Field(None, description="Verbosity Levels [0=> Nothing ... ]")
