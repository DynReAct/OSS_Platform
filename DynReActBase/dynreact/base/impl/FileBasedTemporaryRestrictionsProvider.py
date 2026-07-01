import glob
import json
import logging
import os.path
from typing import Sequence

from pydantic import TypeAdapter

from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.TemporaryRestrictionsProvider import TemporaryRestrictionsProvider, EquipmentRestriction, \
    RestrictionUtils
from dynreact.base.model import Site


class FileBasedTemporaryRestrictionsProvider(TemporaryRestrictionsProvider):
    """
    Expects rules to be stored in json files in a single folder, and likewise stores the active status in a
    special file "__active__.json" in this folder.
    """

    _ACTIVE_FILE: str = "__active__.json"

    def __init__(self, url: str, site: Site):
        super().__init__(url, site)
        if not url or not url.startswith("file:"):
            raise NotApplicableException(f"Service {url} not applicable to FileBasedTemporaryRestrictionsService")
        folder = url[len("file:"):]
        if not os.path.isdir(folder):
            raise NotApplicableException(f"Folder not found {folder}")
        folder = folder.replace("\\", "/")
        json_files = [f for f in glob.glob(os.path.join(folder, "*.json")) if not f.endswith(FileBasedTemporaryRestrictionsProvider._ACTIVE_FILE)]
        if len(json_files) == 0:
            raise NotApplicableException(f"No config files in folder {folder}")
        self._folder = folder
        self._files = json_files
        self._rules: dict[str, EquipmentRestriction]|None = None  # initialized lazily
        self._active_file = os.path.join(self._folder, FileBasedTemporaryRestrictionsProvider._ACTIVE_FILE)
        self._active_rules: tuple[str] = self._parse_active()

    def _active_status_for_rules(self, rules: Sequence[EquipmentRestriction]) -> Sequence[tuple[EquipmentRestriction, bool]]:
        return [(r, r.id in self._active_rules) for r in rules]

    def _check_parse(self):
        if not self._rules:
            self._rules = FileBasedTemporaryRestrictionsProvider._parse(self._files)

    def _parse_active(self):
        file = self._active_file
        if not os.path.isfile(file):
            return tuple()
        with open(file, "r") as fl:
            content = fl.read()
        active_rules = TypeAdapter(tuple[str]).validate_json(content)
        return active_rules

    @staticmethod
    def _parse(files: Sequence[str]) -> dict[str, EquipmentRestriction]:
        rules = {}
        for file in files:
            with open(file, mode="r") as fl:
                content = fl.read()
                json_content = json.loads(content)  # FIXME better use a custom Python validator than deserialize
            rule: EquipmentRestriction = RestrictionUtils.deserialize(json_content)
            rule_id = rule.id
            if rule_id in rules:
                cnt = 0
                while rule_id in rules:
                    rule_id = rule.id + f"_{cnt}"
                    cnt += 1
                logging.getLogger(__name__).warning(f"Duplicate rule id {rule.id}; replacing it by {rule_id}")
                rule = rule.model_copy(update={"id": rule_id})
            rules[rule_id] = rule
        return rules

    def equipment_restrictions(self, equipment: int | Sequence[int] | None = None) -> Sequence[tuple[EquipmentRestriction, bool]]:
        """
        Parameters:
            equipment:

        Returns:
             sequence of rules together with their active status
        """
        self._check_parse()
        rules = self._rules.values()
        if equipment is not None:
            equipment = equipment if isinstance(equipment, Sequence) else (equipment, )
            rules = [r for r in rules if r.equipment in equipment or (isinstance(r.equipment, Sequence) and any(e in equipment for e in r.equipment))]
        return self._active_status_for_rules(rules)

    def set_active_status(self, rule: str|Sequence[str], active: bool):
        """
        Activate or deactivate a rule, identified by its id

        Parameters:
            rule:
            active:
        """
        if not isinstance(rule, Sequence):
            rule = [rule]
        current_rules = self._active_rules
        if not active:
            rules = [r for r in current_rules if r not in rule]
        else:
            rules = list(current_rules) + [r for r in rule if r not in current_rules]
        self._rules = tuple(rules)
        self._store_rules()

    def _store_rules(self):
        # TODO failsafe writing
        rules = self._rules
        file = self._active_file
        if not rules:
            if os.path.isfile(file):
                os.remove(file)
            return
        content = "[" + ", ".join(rules) + "]"
        with open(file, mode="w") as fl:
            fl.write(content)









