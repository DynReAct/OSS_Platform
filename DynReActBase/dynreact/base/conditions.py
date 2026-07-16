from __future__ import annotations

from datetime import datetime, date
from types import MappingProxyType
from typing import Sequence, Literal, TypeVar, Any, Mapping, Generic

from pydantic import BaseModel

#type
ConditionOperator = Literal["=", "<", "<=", ">", ">=", "!="]
#type
LowerOperator = Literal["<", "<="]
#type
ConditionValue = str | int | float | bool | datetime | date | None
#type
NumericValue = int | float | datetime | date


CV = TypeVar("CV", bound=ConditionValue)


class ParameterValue(BaseModel, Generic[CV], use_attribute_docstrings=True):
    parameter_type: Literal["string", "int", "float", "bool", "datetime", "date"]
    default_value: CV|None = None
    allowed_range: tuple[CV|None, CV|None]|None = None


class BaseCondition(BaseModel, use_attribute_docstrings=True):
    type: str


class PropertyCondition(BaseCondition):
    attribute: str


V = TypeVar("V", bound=ConditionValue|ParameterValue)
N = TypeVar("N", bound=NumericValue|ParameterValue)


class ThresholdCondition(PropertyCondition, Generic[V]):
    type: Literal["threshold"] = "threshold"
    operator: ConditionOperator
    value: V


class ListCondition(PropertyCondition, Generic[V]):
    type: Literal["list"] = "list"
    operator: Literal["in", "not_in"] = "in"
    values: Sequence[V]


class RangeCondition(PropertyCondition, Generic[N]):
    type: Literal["range"] = "range"
    value_range: tuple[N, N]
    operators: tuple[LowerOperator, LowerOperator]


class MaterialCondition(BaseCondition):
    type: Literal["material"] = "material"
    material_class: str
    relevant_attributes: tuple[str, ...]|None = None
    "For display to the user only"


#type
LeafCondition = ThresholdCondition | ListCondition | RangeCondition | MaterialCondition


class NotCondition(BaseCondition):
    type: Literal["not"] = "not"
    base: Condition


class CompositeCondition(BaseCondition):
    conditions: Sequence[Condition]


class And(CompositeCondition):
    type: Literal["and"] = "and"


class Or(CompositeCondition):
    type: Literal["or"] = "or"


#type
Condition = LeafCondition | NotCondition | And | Or


class ConditionUtils:

    _TYPES: dict[str, type[Condition]] = MappingProxyType({
        "threshold": ThresholdCondition, "list": ListCondition, "range": RangeCondition, "material": MaterialCondition,
        "not": NotCondition, "and": And, "or": Or
    })

    @staticmethod
    def deserialize(content: dict[str, Any]) -> Condition:
        if not content or "type" not in content or content["type"] not in ConditionUtils._TYPES:
            raise ValueError(f"Invalid condition: {content}")
        tp = ConditionUtils._TYPES.get(content["type"])
        instance: Condition = tp.model_validate(content)
        return instance

    @staticmethod
    def applies(condition: Condition, obj: Any):
        """
        Note: the passed condition must not be parametrized, i.e., all ParameterValues must be replaced by actual values first
        :param condition:
        :param obj:
        :return:
        """
        if isinstance(condition, And):
            return all(ConditionUtils.applies(c, obj) for c in condition.conditions)
        if isinstance(condition, Or):
            return any(ConditionUtils.applies(c, obj) for c in condition.conditions)
        if isinstance(condition, NotCondition):
            return not ConditionUtils.applies(condition.base, obj)
        if isinstance(condition, MaterialCondition):
            cl = condition.material_class
            value = getattr(obj, "material_classes", None)
            return cl in value.values() if isinstance(value, Mapping) else False
        value = ConditionUtils._extract_value(obj, condition)
        if isinstance(condition, ListCondition):
            return value in condition.values
        if isinstance(condition, ThresholdCondition):
            operator = condition.operator
            target_value = condition.value
            if value is None:
                return (operator == "=" and target_value is None) or (operator == "!=" and target_value is not None)
            if operator == "=":
                return value == target_value
            if operator == "<":
                return value < target_value
            if operator == "<=":
                return value <= target_value
            if operator == ">":
                return value > target_value
            if operator == ">=":
                return value >= target_value
            if operator == "!=":
                return value != target_value
            raise ValueError(f"Unsupported operator {operator} in condition {condition}")
        if isinstance(condition, RangeCondition):
            rng = condition.value_range
            if value is None or value < rng[0] or value > rng[1]:
                return False
            if (value == rng[0] and condition.operators[0] == "<=") or (value == rng[1] and condition.operators[1] == "<="):
                return True
            return True
        raise ValueError(f"Condition type not supported: {type(condition)}")

    @staticmethod
    def _extract_value(obj: Any, condition: PropertyCondition):
        attributes = condition.attribute.split(".")
        for attr in attributes:
            obj = getattr(obj, attr, None) if not isinstance(obj, Mapping) else obj.get(attr)
            if obj is None:
                return None
        return obj

    @staticmethod
    def condition_has_parameters(condition: Condition) -> bool:
        if isinstance(condition, NotCondition):
            return ConditionUtils.condition_has_parameters(condition.base)
        if isinstance(condition, CompositeCondition):
            return any(ConditionUtils.condition_has_parameters(c) for c in condition.conditions)
        if isinstance(condition, ThresholdCondition):
            return isinstance(condition.value, ParameterValue)
        if isinstance(condition, ListCondition):
            return any(isinstance(v, ParameterValue) for v in condition.values)
        if isinstance(condition, RangeCondition):
            return any(isinstance(v, ParameterValue) for v in condition.value_range)
        return False

    @staticmethod
    def apply_parameters(condition: Condition, parameter_values: list[ConditionValue]|None, _list_safe: bool=False) -> Condition:
        """
        Parameters:
            condition:
            parameter_values:

        Returns:
            a new condition with all ParameterValue fields replaced by actual values

        Raises:
            ValueError if the length of parameter_values does not match the number of parameters in condition
        """
        if not parameter_values or len(parameter_values) == 0:
            if not ConditionUtils.condition_has_parameters(condition):
                return condition
            raise ValueError("No or insufficient parameter values supplied, cannot apply them to parametrized rule")
        parameter_values = list(parameter_values) if not _list_safe else parameter_values
        if isinstance(condition, NotCondition):
            return condition.model_copy(update={"base": ConditionUtils.apply_parameters(condition.base, parameter_values, _list_safe=True)})
        if isinstance(condition, CompositeCondition):
            return condition.model_copy(update={"conditions": [ConditionUtils.apply_parameters(c, parameter_values, _list_safe=True) for c in condition.conditions]})
        if isinstance(condition, ThresholdCondition):
            if not isinstance(condition.value, ParameterValue):
                return condition
            value = parameter_values.pop(0)
            return condition.model_copy(update={"value": value})
        if isinstance(condition, ListCondition):
            if not any(isinstance(v, ParameterValue) for v in condition.values):
                return condition
            values = [parameter_values.pop(0) if isinstance(v, ParameterValue) else v for v in condition.values]
            return condition.model_copy(update={"values": values})
        if isinstance(condition, RangeCondition):
            if not any(isinstance(v, ParameterValue) for v in condition.value_range):
                return condition
            values = tuple([parameter_values.pop(0) if isinstance(v, ParameterValue) else v for v in condition.value_range])
            return condition.model_copy(update={"value_range": values})
        return condition


