import glob
import json
import logging
import os.path
import shutil
import threading
import time
from typing import Sequence, Mapping

from pydantic import TypeAdapter, BaseModel, ValidationError
from datetime import datetime

from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.TemporaryRestrictionsProvider import TemporaryRestrictionsProvider, EquipmentRestriction, \
    RestrictionUtils, RuleSettings
from dynreact.base.conditions import Condition, ConditionUtils
from dynreact.base.model import Site


class ActiveSettings(BaseModel, use_attribute_docstrings=True):
    rules: dict[str, list[RuleSettings]|None]
    "Note: only a single instance of a rule may be instantiated for non-configurable rules, i.e., those without ParameterValues."


_INACTIVE = RuleSettings(active=False)


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
            return tuple()
        settings = active[rule_id]
        return settings if settings is not None else (RuleSettings(active=True), )

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

    def get_restriction(self, rule_id: str) -> tuple[EquipmentRestriction|None, Sequence[RuleSettings]]:
        self._check_parse()
        rule = self._rules.get(rule_id)
        if rule is None:
            return None, tuple()
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

    def is_active(self, rule_id: str, setting_id: int = 0) -> bool:
        self._check_parse()
        rules = self._active_rules.get(rule_id, (_INACTIVE, ))
        if rules is None:  # non-configurable rules have a None value stored
            return True
        rule = next((r for r in rules if r.setting_id == setting_id), _INACTIVE)
        return rule.active

    def add(self, rule: str) -> RuleSettings:
        self._check_parse()
        if rule not in self._rules:
            raise ValueError(f"Rule {rule} unknown")
        rule_obj = self._rules[rule]
        has_parameters = ConditionUtils.condition_has_parameters(rule_obj.condition)
        has_equipment_selection = rule_obj.equipment_selectable
        if not has_parameters and not has_equipment_selection:
            raise ValueError(f"Cannot add settings for non-configurable rule {rule}")
        with self._active_rules_lock:
            new_rules = dict(self._active_rules)
            if rule not in new_rules:
                new_rules[rule] = []
            current_rules = self._active_rules[rule]
            setting_id = round(datetime.now().timestamp()*1000)
            while any(r.setting_id == setting_id for r in current_rules):
                time.sleep(0.01)
                setting_id = round(datetime.now().timestamp()*1000)
            new_rule = RuleSettings(setting_id=setting_id, active=False)
            current_rules.append(new_rule)
            logging.getLogger(__name__).info(f"Adding temporary equipment restriction(s) {rule}")
            self._active_rules = new_rules
            try:
                self._store_rules()
            except:
                self._active_rules = current_rules  # rollback
                raise
            return new_rule

    def store(self, rule: str, settings: RuleSettings):
        """
        Activate or deactivate a rule, identified by its id

        Parameters:
            rule:
            settings:
        """
        self._check_parse()
        if rule not in self._rules:
            raise ValueError(f"Rule {rule} unknown")
        rule_obj = self._rules[rule]
        has_parameters = ConditionUtils.condition_has_parameters(rule_obj.condition)
        has_equipment_selection = rule_obj.equipment_selectable
        #if not has_equipment_selection and settings.active_equipment is not None:
        #    raise ValueError(f"Must not specifiy equipment when it is not applicable. Rule: {rule_obj}")
        if has_equipment_selection:
            if settings.active_equipment is None:
                if settings.active:
                    raise ValueError(f"Must specify equipment for rule {rule_obj}")
                else:
                    existing = next((r for r in self._active_rules.get(rule, tuple()) if r.setting_id == settings.setting_id), None)
                    if existing is None or not existing.active:  # inactive anyway
                        return
                    settings = settings.model_copy(update={"active_equipment": existing.active_equipment})
            not_applicable = [e for e in settings.active_equipment if e not in rule_obj.equipment]
            if len(not_applicable) > 0:
                raise ValueError(f"Selected equipment {not_applicable} not applicable to rule {rule_obj}")
        elif not has_equipment_selection and settings.active_equipment is not None:
            applicable_equipment = rule_obj.equipment if isinstance(rule_obj.equipment, Sequence) else (rule_obj.equipment, )
            if len(applicable_equipment) != len(settings.active_equipment) or any(e not in applicable_equipment for e in settings.active_equipment):
                raise ValueError(f"Cannot specify equipment for rule {rule}")
            settings = settings.model_copy(update={"active_equipment": None})
        if not has_parameters and settings.parameters is not None:
            if len(settings.parameters) != 0:
                raise ValueError(f"Must not specifiy parameters when they are not applicable. Rule: {rule_obj}")
            settings = settings.model_copy(update={"parameters": None})
        if has_parameters and (settings.parameters is None or len(settings.parameters) == 0):
            if settings.active:
                raise ValueError(f"Parameters not specified for rule {rule_obj}")
            else:
                existing = next((r for r in self._active_rules.get(rule, tuple()) if r.setting_id == settings.setting_id), None)
                if existing is None or not existing.active:  # inactive anyway
                    return
                settings = settings.model_copy(update={"parameters": existing.parameters})
        with self._active_rules_lock:
            current_rules = self._active_rules
            new_rules = dict(current_rules)
            if not has_parameters and not has_equipment_selection:
                if settings.active:
                    new_rules[rule] = None
                else:
                    new_rules.pop(rule, None)
            else:
                settings = settings.model_copy()
                if rule not in new_rules:
                    new_rules[rule] = []
                existing_rules = new_rules[rule]
                existing = next((r_idx for r_idx, r in enumerate(existing_rules) if r.setting_id == settings.setting_id), -1)
                if existing < 0:
                    existing_rules.append(settings)
                else:
                    existing_rules[existing] = settings
            prefix = "Dea" if not settings.active else "A"
            logging.getLogger(__name__).info(f"{prefix}ctivating temporary equipment restriction(s) {rule}")
            self._active_rules = new_rules
            try:
                self._store_rules()
            except:
                self._active_rules = current_rules  # rollback
                raise
            return True

    def delete(self, rule: str, setting_id: int) -> bool:
        return self._delete_or_deactivate(rule, rule_id=setting_id, delete=True)

    def _delete_or_deactivate(self, rule: str, rule_id: int, delete: bool=False) -> bool:
        self._check_parse()
        if rule not in self._rules:
            raise ValueError(f"Rule {rule} unknown")
        current_rules = self._active_rules
        if rule not in current_rules:
            return False
        rule_obj = self._rules[rule]
        has_parameters = ConditionUtils.condition_has_parameters(rule_obj.condition)
        has_equipment_selection = rule_obj.equipment_selectable
        with self._active_rules_lock:
            new_rules = dict(current_rules)
            if not has_parameters and not has_equipment_selection:
                new_rules.pop(rule, None)
            else:
                existing_settings = new_rules[rule]
                setting_idx = next((idx for idx, setting in enumerate(existing_settings) if setting.setting_id == rule_id), None)
                if setting_idx is None:
                    return False
                if delete:
                    existing_settings.pop(setting_idx)
                else:
                    existing_setting = existing_settings[setting_idx]
                    if not existing_setting.active:
                        return False
                    existing_settings[setting_idx] = existing_setting.model_copy(update={"active": False})
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
