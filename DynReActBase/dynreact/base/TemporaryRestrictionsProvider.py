from __future__ import annotations

from typing import Sequence, Any

from pydantic import BaseModel

from dynreact.base.conditions import Condition, ConditionUtils
from dynreact.base.model import Site, Order


class EquipmentRestriction(BaseModel, use_attribute_docstrings=True):
    """
    A restriction for a subset of orders that excludes certain equipment from processing them.
    """

    id: str
    label: str
    description: str|None = None

    equipment: int|Sequence[int]
    "A filter for the equipment unit(s) this rule applies to"
    allowed: bool = False
    """By default, the restriction excludes certain equipment (value = false). 
        If this is set to true, then only the specified equipment is allowed."""
    condition: Condition


class TemporaryRestrictionsProvider:

    def __init__(self, url: str, site: Site):
        self._url = url
        self._site = site

    def equipment_restrictions(self, equipment: int|Sequence[int]|None=None, active_only: bool=False) -> Sequence[tuple[EquipmentRestriction, bool]]:
        """
        Parameters:
            equipment:

        Returns:
             sequence of rules together with their active status
        """
        raise NotImplementedError

    def get_restriction(self, rule_id: str) -> tuple[EquipmentRestriction|None, bool]:
        """
        Parameters:
            rule_id:

        Returns:
             Restriction plus active status
        """
        return next(((rule, active) for rule, active in self.equipment_restrictions() if rule.id == rule_id), (None, False))


    def set_active_status(self, rule: str|Sequence[str], active: bool):
        """
        Activate or deactivate a rule, identified by its id

        Parameters:
            rule:
            active:
        """
        raise NotImplementedError


class RestrictionUtils:

    @staticmethod
    def deserialize(content: dict[str, Any]) -> EquipmentRestriction:
        if not content or "condition" not in content:
            raise ValueError(f"Not a valid condition: {content}")
        condition = ConditionUtils.deserialize(content["condition"])
        content2 = content|{"condition": condition}
        return EquipmentRestriction.model_validate(content2)

    @staticmethod
    def equipment_allowed(rule: EquipmentRestriction|Sequence[EquipmentRestriction], equipment: int, order: Order) -> bool:
        if isinstance(rule, Sequence):
            return all(RestrictionUtils.equipment_allowed(r, equipment, order) for r in rule)
        equipment_match = equipment in rule.equipment if isinstance(rule.equipment, Sequence) else equipment == rule.equipment
        if equipment_match == rule.allowed:
            return True
        applies = ConditionUtils.applies(rule.condition, order)
        return (not rule.allowed and not applies) or (rule.allowed and applies)
