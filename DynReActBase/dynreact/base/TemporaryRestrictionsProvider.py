from __future__ import annotations

from typing import Sequence, Any, Mapping

from pydantic import BaseModel

from dynreact.base.conditions import Condition, ConditionUtils, ConditionValue
from dynreact.base.model import Site, Order


class EquipmentRestriction(BaseModel, use_attribute_docstrings=True):
    """
    A restriction for a subset of orders that excludes certain equipment from processing them.
    There are essentially two types of restrictions, static ones (fixed values in condition) and parametrizable
    ones (ParameterValue values in condition).
    """

    id: str
    label: str
    description: str|None = None

    equipment: int|Sequence[int]
    "A filter for the equipment unit(s) this rule applies to"
    equipment_selectable: bool = False
    "If set to true and equipment is a list, then the user may select the applicable equipment"
    allowed: bool = False
    """By default, the restriction excludes certain equipment (value = false). 
        If this is set to true, then only the specified equipment is allowed."""
    condition: Condition


class TemporaryRestrictionsProvider:

    def __init__(self, url: str, site: Site):
        self._url = url
        self._site = site

    def equipment_restrictions(self, equipment: int|Sequence[int]|None=None, active_only: bool=False) -> Sequence[tuple[EquipmentRestriction, Sequence[RuleSettings]]]:
        """
        Parameters:
            equipment:

        Returns:
             sequence of rules together with their active status
        """
        raise NotImplementedError

    def get_restriction(self, rule_id: str) -> tuple[EquipmentRestriction|None, Sequence[RuleSettings]]:
        """
        Parameters:
            rule_id:

        Returns:
             Restriction plus active status
        """
        return next(((rule, settings) for rule, settings in self.equipment_restrictions() if rule.id == rule_id), (None, tuple()))

    def activate(self, rule: str, settings: RuleSettings, rule_index: int|None=None) -> bool:
        """
        Activate or deactivate a rule, identified by its id

        Parameters:
            rule:
            settings:
            rule_index: if not None, the respective configuration will be updated
        """
        raise NotImplementedError

    def deactivate(self, rule: str, rule_index: int = 0) -> bool:
        raise NotImplementedError

    def is_active(self, rule_id: str) -> bool:
        raise NotImplementedError


class RuleSettings(BaseModel, use_attribute_docstrings=True):
    active: bool
    active_equipment: Sequence[int]|None=None
    "If none, all equipments are considered selected"
    parameters: Sequence[ConditionValue]|None=None
    "TODO: nested parameters"


class RestrictionUtils:

    @staticmethod
    def deserialize(content: dict[str, Any]) -> EquipmentRestriction:
        if not content or "condition" not in content:
            raise ValueError(f"Not a valid condition: {content}")
        condition = ConditionUtils.deserialize(content["condition"])
        content2 = content|{"condition": condition}
        return EquipmentRestriction.model_validate(content2)

    @staticmethod
    def equipment_allowed(rule: EquipmentRestriction, settings: Sequence[RuleSettings], equipment: int, order: Order) -> bool:
        equipment_match = equipment in rule.equipment if isinstance(rule.equipment, Sequence) else equipment == rule.equipment
        if equipment_match == rule.allowed:
            return True
        for setting in settings:
            params = list(setting.parameters) if setting.parameters else None
            condition = ConditionUtils.apply_parameters(rule.condition, params)
            applies = ConditionUtils.applies(condition, order)
            allowed = (not rule.allowed and not applies) or (rule.allowed and applies)
            if not allowed:
                return allowed
        return True
