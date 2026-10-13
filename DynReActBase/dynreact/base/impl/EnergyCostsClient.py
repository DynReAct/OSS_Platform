import logging
import os
from datetime import timedelta, datetime
from urllib.parse import urlparse

import requests
from dotenv import load_dotenv
from pydantic import BaseModel

from dynreact.base.EnergyService import EnergyCostService, EnergyServiceMetadata, EnergyPriceCurve, ServiceResultsFailed
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.monitoring import ServiceHealth


class EnergyCostClientConfig(BaseModel, use_attribute_docstrings=True):

    token: str|None=None

    @staticmethod
    def init_from_env_vars(token: str|None=None):
        load_dotenv(override=True)
        if token is None:
            token = os.getenv("ENERGY_SERVICE_0_TOKEN")
        return EnergyCostClientConfig(token=token)


class EnergyCostClient(EnergyCostService):

    _FORMAT = "%Y-%m-%dT%H:%M%z"

    def __init__(self, url: str, config: EnergyCostClientConfig|None=None):
        super().__init__(url)
        address = url[7:]
        if not EnergyCostClient._is_valid_url(address):
            raise ValueError(f"URL seems to be invalid: {address}")
        if not config:
            config = EnergyCostClientConfig.init_from_env_vars()
        self._address = EnergyCostClient._fix_path(address)
        self._config = config
        self._token = config.token
        self._meta: EnergyServiceMetadata | None = None
        self._status_update_interval: timedelta = timedelta(minutes=2)
        self._last_status_update: datetime | None = None
        self._last_status: int = -1
        self._session: requests.Session|None = None
        self._get_logger().info("Energy cost HTTP client starting")

    def _get_meta(self) -> EnergyServiceMetadata:
        if self._meta is None:
            # TODO error handling etc
            self._init_session()
            result = self._session.get(self._address + "model", headers={"Accept": "application/json"})
            result.raise_for_status()
            json = result.json()
            self._meta = EnergyServiceMetadata.model_validate(json)
        return self._meta

    def __str__(self):
        try:
            return f"EnergyCostClientHttp[id={self.service().id}, label={self.service().label}, address={self._address}]"
        except:
            return f"EnergyCostClientHttp[address={self._address}] (disconnected)"

    def service(self) -> EnergyServiceMetadata:
        return self._get_meta()

    def energy_costs(self, start: datetime, end: datetime) -> EnergyPriceCurve|ServiceResultsFailed:
        start_str = start.strftime(EnergyCostClient._FORMAT)
        end_str = end.strftime(EnergyCostClient._FORMAT)
        self._init_session()
        try:
            response = self._session.get(self._address + f"costs?start={start_str}&end={end_str}", headers={"Accept": "application/json"})
            if not response.ok:
                jsn = None
                try:
                    jsn = response.json()
                except:
                    try:
                        jsn = response.text
                    except:
                        pass
                return ServiceResultsFailed(reason=response.status_code, message=response.reason, details=jsn)
            result = EnergyPriceCurve.model_validate(response.json())
            return result
        except requests.exceptions.ConnectionError:
            return ServiceResultsFailed(reason=1, message="Service not available")
        except:
            self._get_logger().exception("Failed to contact energy service")  # TODO avoid too frequent error logs
            return ServiceResultsFailed(reason=500, message="Internal server error")  # ?

    def status(self) -> int:
        now = DatetimeUtils.now()
        if self._last_status_update is None or now - self._last_status_update > self._status_update_interval:
            self._init_session()
            try:
                result = self._session.get(self._address + "health", headers={"Accept": "application/json"})
                if not result.ok:
                    self._last_status = result.status_code
                else:
                    health = ServiceHealth.model_validate(result.json())
                    self._last_status = health.status
            except:
                self._last_status = 1
            self._last_status_update = now
        return self._last_status

    def _get_logger(self) -> logging.Logger:
        return logging.getLogger(f"dynreact.base.impl.EnergyCostClientHttp[{self._address}]")

    def _init_session(self):
        if self._session is None:
            self._session = requests.Session()
            if self._token:
                self._session.headers.update({"X-Token": self._token})

    # https://stackoverflow.com/a/36283503
    @staticmethod
    def _is_valid_url(url: str, qualifying_attributes=("scheme", "netloc")):
        tokens = urlparse(url)
        return all(getattr(tokens, qualifying_attr) for qualifying_attr in qualifying_attributes)

    @staticmethod
    def _fix_path(pth: str) -> str:
        if len(pth) > 0 and not pth.endswith("/"):
            pth = pth + "/"
        return pth


