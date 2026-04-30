"""Short-term planning integration module for OSS_Platform/ShortTermPlanning/dynreact/shortterm/shorttermtargets.

The module is documented in English to make the short-term planning
workflow easier to maintain across OSS and RAS-specific integrations.
"""

import os
from pydantic import BaseModel, Field

from dynreact.shortterm.timedelay import TimeDelay

class ColumnDefinitions(BaseModel):
    """Column definition metadata used by the auction tables.

    Attributes:
        headerName: Label displayed in the table header.
        path: JSON path used to read the value from an auction payload.
        pinned: Whether the column remains pinned in the grid.
    """

    headerName: str | None = Field(default=None, description="Name of the field.")
    path: str | None = Field(default=None, description="Path to the resulting JSON.")
    pinned: bool | None = Field(default=False, description="Whether the field is pinned in the table.")

class ShortTermTargets(BaseModel):
    """Short-term planning runtime configuration.

    Attributes:
        KAFKA_IP: Kafka broker address.
        TimeDelays: Delay values used by the auction lifecycle.
        TOPIC_GEN: Main Kafka topic for general communication.
        TOPIC_CALLBACK: Main Kafka topic for callbacks.
        LOG_FILE_PATH: Folder where agent logs are stored.
        TableMappings: Column definitions exposed by the auction UI.
        REST_URL: Base URL for the OSS REST API.
        PERF_URL: Base URL for the performance API.
        TRANSPORT_TIMES_URL: Endpoint used to retrieve transport times.
        VB: Verbosity level used by agents and helper scripts.
    """

    model_config = {
        "extra": "forbid",
        "validate_assignment": True,
        "frozen": False
    }

    KAFKA_IP: str | None = Field(default=None, description="Kafka broker address.")
    TimeDelays: TimeDelay = Field(default_factory=TimeDelay, description="Delay recordset for auctions.")
    TOPIC_GEN: str | None = Field(default="DynReact-OSS-Gen", description="General Kafka topic for communication.")
    TOPIC_CALLBACK: str | None = Field(default="DynReact-OSS-Callback", description="General Kafka topic for callbacks.")
    LOG_FILE_PATH: str | None = Field(default="/var/log/dynreact-logs/", description="Log file path.")
    TableMappings: list[ColumnDefinitions] | None = Field(default=None, description="Column description recordset for the auction UI.")
    REST_URL: str | None = Field(default=None, description="REST API URL.")
    PERF_URL: str | None = Field(default=None, description="REST API performance URL.")
    TRANSPORT_TIMES_URL: str | None = Field(default=None, description="Transport-times source URL.")
    VB: int | None = Field(default=None, description="Verbosity level.")
