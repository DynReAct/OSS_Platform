from pydantic import BaseModel, Field

from dynreact.shortterm.timedelay import TimeDelay

class ColumnDefinitions(BaseModel):
    headerName: str | None = Field(None, description="Name of the field")
    path: str | None = Field(None, description="Path to the resulting JSON")
    pinned: bool | None = Field(False, description="Whether the field is pinned in the Table")

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
        TABLE_MAPPINGS: Struct of columns to be shown for auctions
        REST_URL: REST API URL
        VB: verbosity level
        PERF_URL: REST API PERF URL  (http://192.168.110.68:5017)
    """

    model_config = {
        "extra": "forbid",
        "validate_assignment": True,
        "frozen": False
    }

    KAFKA_IP: str | None = Field(None, description="Kafka broker address.")
    TimeDelays: TimeDelay | None = Field(TimeDelay(), description="Delay recordset for Auction")
    TOPIC_GEN: str | None = Field("DynReact-Gen", description="General Kafka topic for comm.")
    TOPIC_CALLBACK: str | None = Field("DynReact-Callback", description="General Kafka topic for callbacks.")
    LOG_FILE_PATH: str | None = Field("/var/log/dynreact-logs/", description="Log file path.")
    TableMappings: list[ColumnDefinitions] | None = Field(None, description="Column description recordset for RAS Auction")
    REST_URL: str | None = Field(None, description="REST API URL.")
    PERF_URL: str | None = Field(None, description="REST API PERF URL.")
    VB: int | None = Field(None, description="Verbosity Levels [0=> Nothing ... ]")