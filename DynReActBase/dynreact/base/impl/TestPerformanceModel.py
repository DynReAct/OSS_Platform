import os.path
from datetime import datetime
from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field, BeforeValidator

from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.PlantPerformanceModel import PlantPerformanceModel, PerformanceEstimation
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Site, Order, Material


class BaseCondition(BaseModel):

    field: str
    condition: Literal["=", "<", "<=", ">", ">=", "!="]
    value: str|bool|float|datetime
    satisfied_if_unset: bool = False


class Concatenation(BaseModel, arbitrary_types_allowed=True):

    operator: Literal["AND", "OR"]
    items: list[Union["BaseCondition", "Concatenation"]]   # actually list[Condition|Concatenation], but this does not work


Condition = BaseCondition|Concatenation


class PlantPerformanceBasic(BaseModel):

    equipment: int
    performance: Annotated[float, Field(ge=0, le=1, description="The performance value of the plant")]
    start: Annotated[datetime, Field(description="Start time"), BeforeValidator(DatetimeUtils.parse_datetime_str)]
    end: Annotated[datetime, Field(description="End time"), BeforeValidator(DatetimeUtils.parse_datetime_str)]
    affected_orders: Annotated[Condition | None, Field(description="Optional conditions on the orders affected")] = None


class TestPerformanceConfig(BaseModel):

    id: str
    label: str|None = None
    description: str|None = None
    equipment: dict[int, list[PlantPerformanceBasic]]


# TODO HttpPerformanceModel + corresponding server
class TestPerformanceModel(PlantPerformanceModel):

    def __init__(self, url: str, site: Site, config: TestPerformanceConfig | None = None):
        super().__init__(url, site)
        uri_lower = url.lower()
        if config is not None:
            self._config = config
        elif uri_lower.startswith("test+file:"):
            file = url[len("test+file:"):]
            if not os.path.isfile(file):
                raise Exception("File not found " + file)
            content = None
            with open(file, "r") as f:
                content = f.read()
            self._config: TestPerformanceConfig = TestPerformanceConfig.model_validate_json(content)
        elif uri_lower.startswith("test+data:"):
            data = url[len("test+data:"):]
            self._config: TestPerformanceConfig = TestPerformanceConfig.model_validate_json(data)
        else:
            raise NotApplicableException("Unexpected URI for test performance model: " + str(url))

    def id(self):
        return self._config.id

    def label(self, lang: str = "en"):
        return self._config.label if self._config.label is not None else self._config.id

    def description(self, lang: str = "en"):
        return self._config.description if self._config.description is not None else "A dummy plant performance model for testing"

    def performance(self, equipment: int, order: Order, coil: Material | None = None) -> PerformanceEstimation:
        """
        Note: the performance is always evaluated at the query time
        :param equipment:
        :param order:
        :param coil:
        :return:
        """
        coil_id = coil.id if coil is not None else None
        if equipment not in self._config.equipment:
            return PerformanceEstimation(performance=1, equipment=equipment, order=order.id, material=coil_id)
        now = DatetimeUtils.now()
        first_applicable: PlantPerformanceBasic|None = next((config for config in self._config.equipment[equipment] if TestPerformanceModel._applies(config, equipment, order, coil, now)), None)
        performance = first_applicable.performance if first_applicable is not None else 1
        return PerformanceEstimation(performance=performance, equipment=equipment, order=order.id, material=coil_id)

    @staticmethod
    def _applies(config: PlantPerformanceBasic, plant: int, order: Order, coil: Material | None, timestamp: datetime) -> bool:
        if plant != config.equipment:
            return False
        if config.start > timestamp or config.end < timestamp:
            return False
        if config.affected_orders is None:
            return True
        return TestPerformanceModel._condition_applies(config.affected_orders, order)

    @staticmethod
    def _condition_applies(condition: Condition, order: Order):
        if isinstance(condition, Concatenation):
            if condition.operator == "AND":
                first_violation = next((subcond for subcond in condition.items if not TestPerformanceModel._condition_applies(subcond, order)), None)
                return first_violation is None
            else:
                first_applicable = next((subcond for subcond in condition.items if TestPerformanceModel._condition_applies(subcond, order)), None)
                return first_applicable is not None
        else:
            field = condition.field
            value = getattr(order, field) if hasattr(order, field) else None
            if value is None:  # is hasattr the right method for checking?
                return condition.satisfied_if_unset
            if condition.condition == "==" or condition.condition == "=":
                return value == condition.value
            elif condition.condition == ">":
                return value > condition.value
            elif condition.condition == ">=":
                return value >= condition.value
            elif condition.condition == "<":
                return value < condition.value
            elif condition.condition == "<=":
                return value <= condition.value
            elif condition.condition == "!=":
                return value != condition.value
            else:
                raise ValueError("Unsupported operand " + str(condition.condition))



