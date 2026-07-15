import datetime
import glob
import json
import logging
import os.path
import shutil
import threading
import time
from typing import Sequence, Mapping

from pydantic import TypeAdapter, BaseModel, ValidationError

from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.TemporaryRestrictionsProvider import TemporaryRestrictionsProvider, EquipmentRestriction, \
    RestrictionUtils, RuleSettings
from dynreact.base.conditions import Condition, ConditionUtils
from dynreact.base.model import Site


class ActiveSettings(BaseModel, use_attribute_docstrings=True):
    rules: dict[str, list[RuleSettings]|None]
    "Note: only a single instance of a rule may be instantiated for non-configurable rules, i.e., those without ParameterValues."


class FileBasedTemporaryRestrictionsProvider(TemporaryRestrictionsProvider):
    """
    Expects rules to be stored in json files in a single folder, and likewise stores the active status in a
    special file "__active__.json" in this folder.
    """

    _ACTIVE_FILE: str = "__active__.json"
    _ACTIVE_FILE_BACKUP: str = "__active__.bak.json"

    def __init__(self, url: str, site: Site):
        super().__init__(url, site)
        if not url or not url.startswith("file:"):
            raise NotApplicableException(f"Service {url} not applicable to FileBasedTemporaryRestrictionsService")
        folder = url[len("file:"):]
        if not os.path.isdir(folder):
            raise NotApplicableException(f"Folder not found {folder}")
        folder = folder.replace("\\", "/")
        json_files = [f for f in glob.glob(os.path.join(folder, "*.json")) if not f.endswith(FileBasedTemporaryRestrictionsProvider._ACTIVE_FILE)
                                                                            and not f.endswith(FileBasedTemporaryRestrictionsProvider._ACTIVE_FILE_BACKUP)]
        if len(json_files) == 0:
            raise NotApplicableException(f"No config files in folder {folder}")
        self._folder = folder
        self._files = json_files
        self._rules: dict[str, EquipmentRestriction]|None = None  # initialized lazily
        self._active_file = os.path.join(self._folder, FileBasedTemporaryRestrictionsProvider._ACTIVE_FILE)
        self._active_file_backup = os.path.join(self._folder, FileBasedTemporaryRestrictionsProvider._ACTIVE_FILE_BACKUP)
        self._active_rules_lock = threading.Lock()
        self._active_rules: dict[str, list[RuleSettings]|None] = self._parse_active()

    def _settings_for_rule(self, rule_id: str) -> Sequence[RuleSettings]:
        active = self._active_rules
        if rule_id not in active:
            return []
        settings = active[rule_id]
        return settings if settings is not None else [RuleSettings(active=True)]

    def _active_status_for_rules(self, rules: Sequence[EquipmentRestriction], active_only: bool) -> Sequence[tuple[EquipmentRestriction, Sequence[RuleSettings]]]:
        return [(rule, tuple(self._settings_for_rule(rule.id))) for rule in rules if not active_only or rule.id in self._active_rules]

    def _check_parse(self):
        if not self._rules:
            with self._active_rules_lock:   # double-checked locking
                if not self._rules:
                    self._rules = FileBasedTemporaryRestrictionsProvider._parse(self._files)

    def _parse_active(self):
        with self._active_rules_lock:
            try:
                return FileBasedTemporaryRestrictionsProvider._parse_active_file(self._active_file)
            except (ValidationError, OSError):
                backup_rules = FileBasedTemporaryRestrictionsProvider._parse_active_file(self._active_file_backup)
                try:
                    self._backup_file_to_active()
                except:
                    pass
                return backup_rules

    @staticmethod
    def _parse_active_file(file: str):
        if not os.path.isfile(file):
            return dict()
        with open(file, mode="rt", encoding="utf-8") as fl:
            content = fl.read()
        active_rules = ActiveSettings.model_validate_json(content)
        return active_rules.rules

    @staticmethod
    def _parse(files: Sequence[str]) -> dict[str, EquipmentRestriction]:
        rules = {}
        for file in files:
            with open(file, mode="rt", encoding="utf-8") as fl:
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

    def get_restriction(self, rule_id: str) -> tuple[EquipmentRestriction, Sequence[RuleSettings]] | None:
        self._check_parse()
        rule = self._rules.get(rule_id)
        if rule is None:
            return None
        return rule, self._settings_for_rule(rule_id)

    def equipment_restrictions(self, equipment: int | Sequence[int] | None = None, active_only: bool=False) ->Sequence[tuple[EquipmentRestriction, Sequence[RuleSettings]]]:
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
        return self._active_status_for_rules(rules, active_only)

    def is_active(self, rule_id: str) -> bool:
        self._check_parse()
        return rule_id in self._active_rules

    def activate(self, rule: str, settings: RuleSettings, rule_index: int | None = None):
        """
        Activate a rule, identified by its id

        Parameters:
            rule:
            active:
        """
        if not settings.active:
            return self.deactivate(rule, rule_index=rule_index)
        self._check_parse()
        if rule not in self._rules:
            raise ValueError(f"Rule {rule} unknown")
        rule_obj = self._rules[rule]
        has_parameters = ConditionUtils.condition_has_parameters(rule_obj.condition)
        has_equipment_selection = rule_obj.equipment_selectable
        if not has_equipment_selection and settings.active_equipment is not None:
            raise ValueError(f"Must not specifiy equipment when it is not applicable. Rule: {rule_obj}")
        if has_equipment_selection:
            if settings.active_equipment is None:
                raise ValueError(f"Must specify equipment for rule {rule_obj}")
            if len(settings.active_equipment) == 0:
                return self.deactivate(rule, rule_index=rule_index)
            not_applicable = [e for e in settings.active_equipment if e not in rule_obj.equipment]
            if len(not_applicable):
                raise ValueError(f"Selected equipment {not_applicable} not applicable to rule {rule_obj}")
        if not has_parameters and settings.parameters is not None:
            raise ValueError(f"Must not specifiy parameters when they are not applicable. Rule: {rule_obj}")
        if has_parameters and settings.parameters is None:
            raise ValueError(f"Parameters not specified for rule {rule_obj}")
        with self._active_rules_lock:
            current_rules = self._active_rules
            new_rules = dict(current_rules)
            if not has_parameters and not has_equipment_selection:
                new_rules[rule] = None
            else:
                if rule not in new_rules:
                    new_rules[rule] = []
                existing_rules = new_rules[rule]
                if rule_index is not None and rule_index != len(existing_rules):
                    if rule_index > len(existing_rules):
                        raise ValueError(f"Rule {rule} has {len(existing_rules)} active settings, but index set to {rule_index}")
                    existing_rules[rule_index] = settings
                else:
                    existing_rules.append(settings)
            logging.getLogger(__name__).info(f"Activating temporary equipment restriction(s) {rule}")
            self._active_rules = new_rules
            try:
                self._store_rules()
            except:
                self._active_rules = current_rules  # rollback
                raise
            return True

    def deactivate(self, rule: str, rule_index: int = 0) -> bool:
        self._check_parse()
        if rule not in self._rules:
            raise ValueError(f"Rule {rule} unknown")
        current_rules = self._active_rules
        if rule not in current_rules:
            return False
        rule_obj = self._rules[rule]
        with self._active_rules_lock:
            new_rules = dict(current_rules)
            has_parameters = ConditionUtils.condition_has_parameters(rule_obj.condition)
            if not has_parameters or (rule_index == 0 and len(new_rules[rule]) == 1):
                new_rules.pop(rule, None)
            else:
                existing_settings = new_rules[rule]
                if rule_index >= len(existing_settings):
                    return False
                existing_settings.pop(rule_index)
            self._active_rules = new_rules
            try:
                self._store_rules()
            except:
                self._active_rules = current_rules  # rollback
                raise
            return True

    def _store_rules(self):
        rules = self._rules
        if not rules or len(self._active_rules) == 0:
            if not FileBasedTemporaryRestrictionsProvider._delete_with_retry(self._active_file_backup) or not \
                            FileBasedTemporaryRestrictionsProvider._delete_with_retry(self._active_file):
                raise Exception("Failed to delete persistent rules settings")
            return
        if not self._store_rules_file_with_retry(self._active_file_backup):
            raise Exception("Failed to store persistent rules settings")
        self._backup_file_to_active()

    def _backup_file_to_active(self):
        if not os.path.isfile(self._active_file_backup):
            FileBasedTemporaryRestrictionsProvider._delete_with_retry(self._active_file)
            return
        try:
            shutil.copy2(self._active_file_backup, self._active_file)
        except OSError:
            time.sleep(0.5)
            try:
                shutil.copy2(self._active_file_backup, self._active_file)
            except OSError:
                logging.getLogger(__name__).exception("Failed to copy backup active file to active file")
                raise

    def _store_rules_file_with_retry(self, file: str) -> bool:
        active_rules = self._active_rules
        active = ActiveSettings(rules=active_rules)
        as_json = active.model_dump_json(exclude_unset=True, exclude_none=True)
        try:
            FileBasedTemporaryRestrictionsProvider._write_single_and_validate(file, as_json)
            return True
        except:
            time.sleep(0.5)
            try:
                FileBasedTemporaryRestrictionsProvider._write_single_and_validate(file, as_json)
                return True
            except:
                return False

    @staticmethod
    def _write_single_and_validate(file: str, content: str):
        with open(file, mode="wt", encoding="utf-8") as fl:
            fl.write(content)
        FileBasedTemporaryRestrictionsProvider._parse_active_file(file)

    @staticmethod
    def _delete_with_retry(file: str) -> bool:
        try:
            if os.path.isfile(file):
                os.remove(file)
            return True
        except:
            time.sleep(0.5)
            try:
                if os.path.isfile(file):
                    os.remove(file)
                return True
            except:
                return False
