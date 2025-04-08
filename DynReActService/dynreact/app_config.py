import os
from typing import Literal

from dotenv import load_dotenv


class DynReActSrvConfig:

    config_provider: str = "default+file:./data/site.json"
    snapshot_provider: str = "default+file:./data/snapshots"
    downtime_provider: str = "default+file:./data/downtimes.json"
    cost_provider: str|None = None  # needs to be specified
    "If None, an arbitrary cost provider will be used, if available"
    long_term_provider: str = "default:8h"
    short_term_planning: str = "default+file:./data/stp_context.json"
    results_persistence: str = "default+file:./results"
    availability_persistence: str = "default+file:./config"
    lot_sinks: list[str] = ["default+file:./results"]
    max_snapshot_caches: int = 3
    max_snapshot_solutions_caches: int = 10
    out_directory: str = "./out"
    cors: bool = False
    auth_method: Literal["dummy", "ldap", "ldap_simple"]|None = None
    auth_max_user_length: int = 20
    ldap_address: str|list[str] = "ldap://localhost:1389"
    # for ldap_simple mode
    ldap_user_extension: str | None = None
    # for ldap mode
    ldap_query_user: str|None = None
    ldap_query_pw: str|None = None
    ldap_search_base: str|None = None
    ldap_query: str = "(sAMAccountName={user})"
    # expected format: ["dynreact.custom.SomePlantPerformanceModel:uri"],
    # where the first component identifies a class name (sub class of PlantPerformanceModel) and uri may contain
    # model-specific initialization data
    plant_performance_models: list[str]|None = None
    stp_frontend: str = "default"  # default is the frontend provided in this module

    def __init__(self,
                 config_provider: str | None = None,
                 snapshot_provider: str|None = None,
                 downtime_provider: str|None = None,
                 results_persistence: str|None = None,
                 availability_persistence: str|None = None,
                 lot_sinks: list[str]|str|None = None,
                 cost_provider: str|None = None,
                 long_term_provider: str|None = None,
                 short_term_planning: str|None = None,
                 out_directory: str|None = None,
                 max_snapshot_caches: int|None = None,
                 max_snapshot_solutions_caches: int|None = None,
                 cors: bool|None = None,
                 auth_method: Literal["dummy", "ldap", "ldap_simple"]|None = None,
                 auth_max_user_length: int|None = None,
                 ldap_user_extension: str | None = None,
                 ldap_address: str|list[str] | None = None,
                 ldap_query_user: str | None = None,
                 ldap_query_pw: str | None = None,
                 ldap_search_base: str | None = None,
                 ldap_query: str | None = None,
                 plant_performance_models: list[str]|None = None,
                 stp_frontend: str|None = None):
        load_dotenv()
        if config_provider is None:
            config_provider = os.getenv("CONFIG_PROVIDER", DynReActSrvConfig.config_provider)
        if snapshot_provider is None:
            snapshot_provider = os.getenv("SNAPSHOT_PROVIDER", DynReActSrvConfig.snapshot_provider)
        if downtime_provider is None:
            downtime_provider = os.getenv("DOWNTIME_PROVIDER", DynReActSrvConfig.downtime_provider)
        if cost_provider is None:
            cost_provider = os.getenv("COST_PROVIDER", DynReActSrvConfig.cost_provider)
        if long_term_provider is None:
            long_term_provider = os.getenv("LONG_TERM_PLANNING", DynReActSrvConfig.long_term_provider)
        if short_term_planning is None:
            short_term_planning = os.getenv("SHORT_TERM_PLANNING_PARAMS", DynReActSrvConfig.short_term_planning)
        if results_persistence is None:
            results_persistence = os.getenv("RESULTS_PERSISTENCE", DynReActSrvConfig.results_persistence)
        if availability_persistence is None:
            availability_persistence = os.getenv("AVAILABILITY_PERSISTENCE", DynReActSrvConfig.availability_persistence)
        if lot_sinks is None:
            lot_sinks = [sink.strip() for sink in os.getenv("LOT_SINKS", DynReActSrvConfig.lot_sinks[0]).split(",")]
        elif isinstance(lot_sinks, str):
            lot_sinks = [lot_sinks]
        self.config_provider: str = config_provider
        self.snapshot_provider: str = snapshot_provider
        self.downtime_provider = downtime_provider
        self.cost_provider: str = cost_provider
        self.long_term_provider: str = long_term_provider
        self.short_term_planning: str = short_term_planning
        self.results_persistence = results_persistence
        self.availability_persistence = availability_persistence
        self.lot_sinks = lot_sinks
        if out_directory is None:
            out_directory = os.getenv("OUT_DIRECTORY", DynReActSrvConfig.out_directory)
        self.out_directory: str = out_directory
        if max_snapshot_caches is None:
            max_snapshot_caches = int(os.getenv("MAX_SNAPSHOT_CACHES", DynReActSrvConfig.max_snapshot_caches))
        self.max_snapshot_caches = max_snapshot_caches
        if max_snapshot_solutions_caches is None:
            max_snapshot_solutions_caches = int(os.getenv("MAX_SNAPSHOT_SOLUTIONS_CACHES", DynReActSrvConfig.max_snapshot_solutions_caches))
        self.max_snapshot_solutions_caches = max_snapshot_solutions_caches
        if cors is None:
            cors = os.getenv("CORS", "false").lower() == "true"
        self.cors = cors
        if auth_method is None:
            auth_method = os.getenv("AUTH_METHOD", DynReActSrvConfig.auth_method)
        if auth_max_user_length is None:
            auth_max_user_length = int(os.getenv("AUTH_MAX_USER_LENGTH", DynReActSrvConfig.auth_max_user_length))
        if auth_method is not None:
            auth_method = auth_method.lower()
            if auth_method.startswith("ldap"):
                if ldap_address is None:
                    ldap_address = os.getenv("LDAP_ADDRESS", DynReActSrvConfig.ldap_address)
                if auth_method == "ldap_simple":
                    if ldap_user_extension is None:
                        ldap_user_extension = os.getenv("LDAP_USER_EXTENSION")
                else:
                    if ldap_query_user is None:
                        ldap_query_user = os.getenv("LDAP_QUERY_USER")
                    if ldap_search_base is None:
                        ldap_search_base = os.getenv("LDAP_SEARCH_BASE")
                    if ldap_query is None:
                        ldap_query = os.getenv("LDAP_QUERY", DynReActSrvConfig.ldap_query)
        elif auth_method == "none":
            auth_method = None
        self.auth_method = auth_method
        self.auth_max_user_length = auth_max_user_length
        self.ldap_user_extension = ldap_user_extension
        if ldap_address is not None and "," in ldap_address:
            ldap_address = [add for add in (add.strip() for add in ldap_address.split(",")) if len(add) > 0]
        self.ldap_address = ldap_address
        self.ldap_query_user = ldap_query_user
        self.ldap_query_pw = ldap_query_pw
        self.ldap_query = ldap_query
        self.ldap_search_base = ldap_search_base
        idx = 0
        if plant_performance_models is None:
            plant_performance_models = []
            while True:
                ppm_uri = os.getenv("PLANT_PERFORMANCE_MODEL_" + str(idx))
                if ppm_uri is None:
                    break
                plant_performance_models.append(ppm_uri)
                idx += 1
        if len(plant_performance_models) > 0:
            self.plant_performance_models = plant_performance_models
        if stp_frontend is None:
            stp_frontend = os.getenv("STP_FRONTEND", DynReActSrvConfig.stp_frontend)
        self.stp_frontend = stp_frontend


class ConfigProvider:
    """
    This class is required for testing... by first importing this class and modifying the config field,
    it is possible to adapt settings before starting the app
    """

    config = DynReActSrvConfig()


