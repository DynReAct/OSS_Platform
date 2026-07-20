import logging
import os
from urllib.parse import urlparse
from datetime import datetime, timedelta
from typing import Sequence, Mapping, Any

import requests
from dotenv import load_dotenv
from pydantic import TypeAdapter, BaseModel

from dynreact.base.EnergyService import EnergyServiceMetadata, EnergyService, EnergyPrediction, EnergyPredictionResults, \
    EnergyPredictionResultsFailed, EnergyPredictionResultsSuccess
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Site, Order, Material
from dynreact.base.monitoring import ServiceHealth


class EnergyServiceClientConfig(BaseModel, use_attribute_docstrings=True):

    token: str|None=None

    @staticmethod
    def init_from_env_vars(token: str|None=None):
        load_dotenv(override=True)
        if token is None:
            token = os.getenv("ENERGY_SERVICE_0_TOKEN")
        return EnergyServiceClientConfig(token=token)


class EnergyPredictionInput(BaseModel, use_attribute_docstrings=True, frozen=True):
    orders: Sequence[Mapping[str, Any]]
    "List of serialized order attributes"
    equipment: int
    "Equipment id"
    start_times: Sequence[datetime]
    "Order processing start times"
    model: str | None = None
    "Optional model specifier"


# TODO some results caching?
class EnergyServiceClientHttp(EnergyService):
    """
    Defines a client for an HTTP-based energy service.
    """

    def __init__(self, url: str, site: Site, config: EnergyServiceClientConfig|None = None):
        super().__init__(url, site)
        if not url or not url.lower().startswith("energy+http") or "://" not in url:
            raise NotApplicableException
        address = url[7:]
        if not EnergyServiceClientHttp._is_valid_url(address):
            raise ValueError(f"URL seems to be invalid: {address}")
        if not config:
            config = EnergyServiceClientConfig.init_from_env_vars()
        self._address = EnergyServiceClientHttp._fix_path(address)
        self._config = config
        self._token = config.token
        self._meta: EnergyServiceMetadata|None = None
        self._status_update_interval: timedelta = timedelta(minutes=2)
        self._last_status_update: datetime|None = None
        self._last_status: int = -1
        self._get_logger().info("Energy HTTP client starting")

    def _get_meta(self) -> EnergyServiceMetadata:
        if self._meta is None:
            # TODO error handling etc
            result = requests.get(self._address + "model",
                                  headers=EnergyServiceClientHttp._attach_token({"Accept": "application/json"}, self._token))
            result.raise_for_status()
            json = result.json()
            self._meta = EnergyServiceMetadata.model_validate(json)
        return self._meta

    def __str__(self):
        try:
            return f"EnergyServiceClientHttp[id={self.service().id}, label={self.service().label}, address={self._address}]"
        except:
            return f"EnergyServiceClientHttp[address={self._address}] (disconnected)"

    def service(self) -> EnergyServiceMetadata:
        return self._get_meta()

    def status(self) -> int:
        now = DatetimeUtils.now()
        if self._last_status_update is None or now - self._last_status_update > self._status_update_interval:
            try:
                result = requests.get(self._address + "health",
                                      headers=EnergyServiceClientHttp._attach_token({"Accept": "application/json"}, self._token))
                if not result.ok:
                    self._last_status = result.status_code
                else:
                    health = ServiceHealth.model_validate(result.json())
                    self._last_status = health.status
            except:
                self._last_status = 1
            self._last_status_update = now
        return self._last_status

    def energy_consumption(self,
                           order: Order,
                           equipment: int,
                           start_time: datetime,
                           *args,
                           process_id: int|None=None,
                           model: str|None=None,
                           missing_value_ensemble: Sequence[Order] | None = None,
                           **kwargs) -> EnergyPrediction|EnergyPredictionResultsFailed:
        results = self.bulk_energy_consumption([order], equipment, [start_time], *args, process_id=process_id,
                                               model=model, missing_value_ensemble=missing_value_ensemble, **kwargs)
        if isinstance(results, EnergyPredictionResultsFailed):
            return results
        return results.results[0]

    def bulk_energy_consumption(self,
                           orders: Sequence[Order],
                           equipment: int,
                           start_times: Sequence[datetime],
                           *args,
                           process_id: int|None=None,
                           model: str|None=None,
                           missing_value_ensemble: Sequence[Order] | None = None,
                           **kwargs) -> EnergyPredictionResults:
        service_meta = self.service()
        relevant_fields = service_meta.relevant_fields[equipment] if service_meta.relevant_fields is not None \
                                    and equipment in service_meta.relevant_fields else service_meta.relevant_fields
        serialized_orders: Sequence[dict[str, Any]] = [EnergyServiceClientHttp._serialize_order(o, relevant_fields, missing_value_ensemble) for o in orders]
        payload = EnergyPredictionInput(orders=serialized_orders, equipment=equipment, start_times=start_times, model=model)
        try:
            response = requests.post(self._address + "prediction",
                                   data=payload.model_dump_json(exclude_none=True, exclude_unset=True),
                                   headers=EnergyServiceClientHttp._attach_token({"Content-Type": "application/json", "Accept": "application/json"}, self._token))
            if not response.ok:
                jsn = None
                try:
                    jsn = response.json()
                except:
                    pass
                return EnergyPredictionResultsFailed(reason=response.status_code, message=response.reason, details=jsn)
            result = EnergyPredictionResultsSuccess.model_validate(response.json())
            return result
        except requests.exceptions.ConnectionError:
            return EnergyPredictionResultsFailed(reason=1, message="Service not available")
        except:
            self._get_logger().exception("Failed to contact energy service")  # TODO avoid too frequent error logs
            return EnergyPredictionResultsFailed(reason=500, message="Internal server error")  # ?

    def _get_logger(self) -> logging.Logger:
        return logging.getLogger(f"dynreact.base.impl.EnergyServiceClientHttp[{self._address}]")

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

    @staticmethod
    def _attach_token(headers: dict[str, any], token: str|None) -> dict[str, any]:
        if token:
            headers["X-Token"] = token
        return headers

    @staticmethod
    def _serialize_order(order: Order, relevant_fields: Mapping[str, str]|None, missing_value_ensemble: Sequence[Order]|None) -> dict[str, Any]:
        if relevant_fields is None:
            return order.model_dump(exclude_none=True, exclude_unset=True, mode="json")
        result = {}
        for attribute, field in relevant_fields.items():
            if field == "":
                result[attribute] = ""
                continue
            elif field == "---":  # FIXME
                result[attribute] = 1
                continue
            is_mat_prop = field.startswith("material_properties.")
            obj = order if not is_mat_prop else order.material_properties
            if is_mat_prop:
                field = field[20:]
            value = getattr(obj, field, None)
            if value is None and missing_value_ensemble is not None:
                other_values = []
                for o2 in missing_value_ensemble:
                    obj2 = o2.material_properties if is_mat_prop else o2
                    other_value = getattr(obj2, field, None)
                    if other_value is not None:
                        if not isinstance(other_value, float):
                            break
                        other_values.append(other_value)
                if len(other_values) > 0:
                    value = sum(other_values)/len(other_values)
            if value is not None:
                result[attribute] = value
        return result


# TODO move to CLI
if __name__ == "__main__":
    client = EnergyServiceClientHttp(EnergyServiceClientConfig(address="http://localhost:8051"))
    print(f"Energy service model: {client.service().label} ({client.service().id}: {client.service().description}), applicable processes: {client.service().processes}")
    raise Exception("unfinished")

