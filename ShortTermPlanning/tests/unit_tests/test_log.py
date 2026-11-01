"""Unit tests for the LOG agent of the short-term planning auction.

The tests cover :class:`dynreact.shortterm.agents.log.Log`: the log file, the collection of results,
the start of the auction, and its shutdown. Kafka and Docker are replaced by mocks and the log file
lives in a temporary directory.

The auction protocol these tests protect:

* The LOG pings the agents, counts the ones present and starts the auction exactly once, when all are there.
* It records every ``CONFIRM`` exchanged in the topic as an assignment of a material to an equipment.
* When every expected equipment has finished and the results have been served, it ends the auction once.
"""
import logging
import os
import re
import time
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from dynreact.shortterm.agents import log as log_module
from dynreact.shortterm.agents.log import Log, LogWithExtensionHandler, purge_old_logs

TOPIC = "dynTESTLOG"


@pytest.fixture
def log(tmp_path: Any) -> Any:
    """A parent LOG writing to a temporary file, with Kafka, Docker and the Kafka admin mocked."""
    with patch("dynreact.shortterm.agents.agent.Producer"), patch("dynreact.shortterm.agents.agent.Consumer"), \
            patch.object(log_module, "AdminClient"), patch.object(log_module.DockerManager, "__init__", return_value=None):
        agent = Log(topic=TOPIC, agent=f"LOG:{TOPIC}", log_file=str(tmp_path / f"{TOPIC}.log"))
    yield agent
    logger = logging.getLogger(TOPIC)
    for handler in list(logger.handlers):
        handler.close()
        logger.removeHandler(handler)


@pytest.fixture
def sent() -> Any:
    """Captures every message the LOG sends."""
    with patch.object(log_module, "sendmsgtopic") as mock:
        yield mock


def _written(log: Log) -> str:
    for handler in log.logger.handlers:
        handler.flush()
    with open(log.log_file, encoding="utf-8") as file:
        return file.read()


def _confirm(equipment: str = f"EQUIPMENT:{TOPIC}:14:0", material: str = f"MATERIAL:{TOPIC}:1003", costs: Any = 2.5) -> dict:
    return {"source": material, "dest": equipment, "action": "CONFIRM",
            "payload": {"material_params": {"order": {"id": "o1", "material": "x"}}, "costs": costs}}


# ---------------------------------------------------------------- log file

def test_write_stores_the_message_in_the_log_file(log: Log) -> None:
    log.handle_write_action({"source": "A", "dest": "B", "action": "WRITE",
                             "payload": {"msg": "hello", "identifier": "12345678-aaaa"}})
    assert "|MSG|A|B|WRITE|12345678|hello" in _written(log)


def test_write_accepts_a_json_string_payload(log: Log) -> None:
    log.handle_write_action({"source": "A", "dest": "B", "action": "WRITE",
                             "payload": '{"msg": "from json", "identifier": "abcdefgh-1"}'})
    assert "from json" in _written(log)


def test_write_without_a_payload_leaves_a_trace_instead_of_failing(log: Log) -> None:
    assert log.handle_write_action({"source": "A"}) == "CONTINUE"
    assert "HANDLE_WRITE_ERROR" in _written(log)


def test_rotated_files_keep_the_log_extension(tmp_path: Any) -> None:
    handler = LogWithExtensionHandler(str(tmp_path / "x.log"))
    try:
        assert handler.suffix.endswith(".log")
        assert handler.rotation_filename("ignored").endswith(".log")
    finally:
        handler.close()


def test_messages_without_an_identifier_are_written_with_a_placeholder(log: Log) -> None:
    log.handle_write_action({"source": "A", "dest": "B", "action": "BID", "payload": {"msg": "no identifier"}})
    assert "|MSG|A|B|BID|-|no identifier" in _written(log)


def test_messages_without_text_are_written_as_their_payload(log: Log) -> None:
    log.handle_write_action({"source": "A", "dest": "B", "action": "BID", "payload": {"price": 3}})
    assert '|MSG|A|B|BID|-|{"price": 3}' in _written(log)


def test_plain_string_payloads_are_written_as_text(log: Log) -> None:
    log.handle_write_action({"source": "A", "dest": "B", "action": "WRITE", "payload": "plain text"})
    assert "|MSG|A|B|WRITE|-|plain text" in _written(log)


def test_incomplete_messages_never_fail(log: Log) -> None:
    assert log.handle_write_action({"payload": {}}) == "CONTINUE"
    assert "|MSG|-|-|-|-|{}" in _written(log)


def test_exit_ends_the_loop(log: Log) -> None:
    assert log.handle_exit_action({"source": "UX", "dest": log.agent}) == "END"
    assert f"|MSG|UX|{log.agent}|EXIT|-|Requested Exit" in _written(log)       # the exit is traced in the file


# ---------------------------------------------------------------- results

def test_messages_for_other_agents_are_written_to_the_log_file(log: Log) -> None:
    log.callback_on_not_match({"source": "MATERIAL:x", "dest": "EQUIPMENT:y", "action": "BID", "payload": {}})
    assert "|MSG|MATERIAL:x|EQUIPMENT:y|BID|-|[Topic] dynTESTLOG|" in _written(log)
    assert log.results == {}                                  # only CONFIRM counts as a result


def test_confirm_is_recorded_as_an_assignment_to_the_equipment(log: Log) -> None:
    log.callback_on_not_match(_confirm())
    assert list(log.results) == ["14"]
    entry = log.results["14"][0]
    assert entry["equipment"] == "14" and entry["round"] == "0" and entry["costs"] == 2.5
    assert "material" not in entry                            # the bulky material data is not kept


def test_assignments_of_the_same_equipment_accumulate_in_order(log: Log) -> None:
    log.callback_on_not_match(_confirm(equipment=f"EQUIPMENT:{TOPIC}:14:0"))
    log.callback_on_not_match(_confirm(equipment=f"EQUIPMENT:{TOPIC}:14:1"))
    log.callback_on_not_match(_confirm(equipment=f"EQUIPMENT:{TOPIC}:15:0"))
    assert [e["round"] for e in log.results["14"]] == ["0", "1"] and len(log.results["15"]) == 1


# ---------------------------------------------------------------- start of the auction

def test_check_sets_the_expected_agents_and_pings_all_of_them(log: Log, sent: MagicMock) -> None:
    assert log.handle_check_action({"topic": TOPIC, "payload": {"num_agents": 5}}) == "CONTINUE"
    assert log.total_num_agents == 5
    kwargs = sent.call_args.kwargs
    assert kwargs["action"] == "PING"
    for name in (f"MATERIAL:{TOPIC}:7", f"EQUIPMENT:{TOPIC}:3:0", f"LOG:{TOPIC}"):
        assert re.match(kwargs["dest"], name)
    assert not re.match(kwargs["dest"], "MATERIAL:dynOTHER:7")


def test_each_agent_is_counted_once_and_equipments_are_expected(log: Log) -> None:
    for name in (f"EQUIPMENT:{TOPIC}:3:0", f"EQUIPMENT:{TOPIC}:3:0", f"MATERIAL:{TOPIC}:7", f"LOG:{TOPIC}"):
        log.handle_pinganswer_action({"source": name})
    assert len(log.present_agents) == 3
    assert log.expected_equipments == {"3"}
    assert (log.count_agents("EQUIPMENT"), log.count_agents("MATERIAL"), log.count_agents("LOG")) == (1, 1, 1)


def test_the_auction_starts_once_when_every_agent_is_present(log: Log, sent: MagicMock) -> None:
    log.total_num_agents = 2
    log.handle_pinganswer_action({"source": f"MATERIAL:{TOPIC}:7"})
    assert log.callback_before_message() == "CONTINUE"
    assert not log.auction_start and sent.call_count == 0     # one agent is still missing
    log.handle_pinganswer_action({"source": f"EQUIPMENT:{TOPIC}:3:0"})
    log.callback_before_message()
    assert log.auction_start
    assert sent.call_args.kwargs["action"] == "START" and sent.call_args.kwargs["dest"] == f"EQUIPMENT:{TOPIC}:.*"
    sent.reset_mock()
    log.callback_before_message()
    sent.assert_not_called()                                   # it never starts twice


def test_auction_status_is_reported_on_the_callback_topic(log: Log, sent: MagicMock) -> None:
    log.total_num_agents = 2
    log.handle_pinganswer_action({"source": f"MATERIAL:{TOPIC}:7"})
    log.handle_is_auction_started_action({"topic": TOPIC, "source": "UX"})
    kwargs = sent.call_args.kwargs
    assert kwargs["action"] == "AUCTIONSTARTED" and kwargs["tsend"] == log.topic_callback and kwargs["dest"] == "UX"
    assert kwargs["payload"]["is_auction_started"] is False
    assert kwargs["payload"]["present_agents"] == {"log": 0, "material": 1, "equipment": 0, "total": 1}
    log.handle_pinganswer_action({"source": f"EQUIPMENT:{TOPIC}:3:0"})
    log.auction_start = True
    log.handle_is_auction_started_action({"topic": TOPIC, "source": "UX"})
    assert sent.call_args.kwargs["payload"]["is_auction_started"] is True


# ---------------------------------------------------------------- end of the auction

def _started_with_two_equipments(log: Log) -> None:
    log.total_num_agents = 2
    for number in (3, 4):
        log.handle_pinganswer_action({"source": f"EQUIPMENT:{TOPIC}:{number}:0"})
    log.auction_start = True


def test_the_auction_is_complete_only_when_every_equipment_finished(log: Log) -> None:
    _started_with_two_equipments(log)
    log.handle_equipmentfinished_action({"payload": {"equipment": "3"}})
    assert not log.auction_completed
    log.handle_equipmentfinished_action({"payload": {"equipment": "4"}})
    assert log.auction_completed


def test_finished_equipment_before_the_start_does_not_complete_the_auction(log: Log) -> None:
    _started_with_two_equipments(log)
    log.auction_start = False
    for number in ("3", "4"):
        log.handle_equipmentfinished_action({"payload": {"equipment": number}})
    assert not log.auction_completed


def test_finished_equipment_is_identified_by_its_name_when_the_payload_lacks_it(log: Log) -> None:
    _started_with_two_equipments(log)
    log.handle_equipmentfinished_action({"source": f"EQUIPMENT:{TOPIC}:3:2", "payload": {}})
    assert log.finished_equipments == {"3"}
    log.handle_equipmentfinished_action({"source": "MATERIAL:x:1", "payload": {}})   # no id at all
    assert log.finished_equipments == {"3"}


def test_results_are_served_to_the_asker_and_the_auction_ends_once(log: Log, sent: MagicMock) -> None:
    log.results = {"3": [{"id": "o1"}]}
    log.auction_completed = True
    with patch.object(log_module, "end_auction") as end:
        assert log.handle_askresults_action({"topic": TOPIC, "source": "UX"}) == "CONTINUE"
        log.handle_askresults_action({"topic": TOPIC, "source": "UX"})
    kwargs = sent.call_args.kwargs
    assert kwargs["action"] == "RESULTS" and kwargs["dest"] == "UX" and kwargs["payload"] == log.results
    assert kwargs["tsend"] == log.topic_callback
    end.assert_called_once()
    assert end.call_args.kwargs["topic"] == TOPIC


def test_results_requested_before_completion_do_not_end_the_auction(log: Log, sent: MagicMock) -> None:
    with patch.object(log_module, "end_auction") as end:
        log.handle_askresults_action({"topic": TOPIC, "source": "UX"})
    end.assert_not_called()


def test_a_fatal_error_of_an_agent_discards_the_results_and_ends_the_auction(log: Log) -> None:
    log.results = {"3": [{"id": "o1"}]}
    with patch.object(log_module, "end_auction") as end:
        assert log.handle_receive_error_action({"source": "MATERIAL:x:1", "payload": {}}) == "CONTINUE"
    assert log.results == {}
    end.assert_called_once()


# ---------------------------------------------------------------- CREATE

def test_create_launches_the_replica_log_of_the_auction(log: Log) -> None:
    log.handler = MagicMock()
    message = {"topic": "dynAUCTION", "payload": {"variables": {}}}
    with patch.object(log_module.KeySearch, "assign_values"), patch.object(log_module.KeySearch, "dump_model", return_value={}):
        assert log.handle_create_action(message) == "CONTINUE"
    kwargs = log.handler.launch_container.call_args.kwargs
    assert kwargs["auto_remove"] is True
    assert kwargs["name"] == "dynAUCTION" and kwargs["agent"] == "log" and kwargs["mode"] == "replica"
    assert kwargs["params"]["agent-name"] == "LOG:dynAUCTION"
    assert kwargs["params"]["log-file"].endswith("dynAUCTION.log")


def test_replicas_cannot_create_replicas(log: Log) -> None:
    log.handler = None
    with pytest.raises(Exception, match="Replicas can't create new instances"):
        log.handle_create_action({"topic": "dynAUCTION", "payload": {"variables": {}}})


# ---------------------------------------------------------------- rotation and retention

def _touch(path: Any, age_days: float = 0.0) -> str:
    path.write_text("x")
    when = time.time() - age_days * 86400
    os.utime(path, (when, when))
    return str(path)


def test_log_files_rotate_weekly_by_default(tmp_path: Any) -> None:
    handler = LogWithExtensionHandler(str(tmp_path / "x.log"), utc=True)
    try:
        assert handler.when == "W0" and handler.interval == 7 * 86400
        assert handler.backupCount == 8
    finally:
        handler.close()


def test_rotation_can_be_changed(tmp_path: Any) -> None:
    handler = LogWithExtensionHandler(str(tmp_path / "x.log"), when="midnight", backupCount=3, utc=True)
    try:
        assert handler.interval == 86400 and handler.backupCount == 3
    finally:
        handler.close()


def test_a_rotation_keeps_the_extension_and_only_the_newest_backups(tmp_path: Any) -> None:
    handler = LogWithExtensionHandler(str(tmp_path / "x.log"), backupCount=2, utc=True)
    try:
        for day in ("2025-01-06", "2025-01-13", "2025-01-20", "2025-01-27"):
            _touch(tmp_path / f"x.{day}.log")
        _touch(tmp_path / "y.2025-01-06.log")           # another log of the folder: untouched
        handler.emit(logging.LogRecord("t", logging.INFO, "f", 1, "line", None, None))
        handler.doRollover()
        rotated = sorted(name for name in os.listdir(tmp_path) if name.startswith("x.2"))
        assert len(rotated) == 2 and all(name.endswith(".log") for name in rotated)
        assert "x.2025-01-06.log" not in rotated and "x.2025-01-13.log" not in rotated
        assert "y.2025-01-06.log" in os.listdir(tmp_path)
        assert (tmp_path / "x.log").exists()             # a fresh current file continues
    finally:
        handler.close()


def test_zero_backup_count_keeps_every_rotated_file(tmp_path: Any) -> None:
    handler = LogWithExtensionHandler(str(tmp_path / "x.log"), backupCount=0, utc=True)
    try:
        for day in ("2025-01-06", "2025-01-13", "2025-01-20"):
            _touch(tmp_path / f"x.{day}.log")
        assert handler.getFilesToDelete() == []
    finally:
        handler.close()


def test_purge_removes_only_old_log_files(tmp_path: Any) -> None:
    old = _touch(tmp_path / "dynOLD.log", age_days=40)
    old_rotated = _touch(tmp_path / "dynGEN.2025-01-06.log", age_days=300)
    recent = _touch(tmp_path / "dynNEW.log", age_days=1)
    current = _touch(tmp_path / "dynCURRENT.log", age_days=90)
    other = _touch(tmp_path / "notes.txt", age_days=400)
    (tmp_path / "sub").mkdir()
    removed = purge_old_logs(str(tmp_path), 30, keep=(current,))
    assert sorted(removed) == sorted([old, old_rotated])
    for path in (recent, current, other):
        assert os.path.exists(path)


def test_purge_is_disabled_with_a_non_positive_age_and_survives_a_missing_folder(tmp_path: Any) -> None:
    old = _touch(tmp_path / "dynOLD.log", age_days=400)
    assert purge_old_logs(str(tmp_path), 0) == [] and os.path.exists(old)
    assert purge_old_logs(str(tmp_path / "missing"), 30) == []


def test_the_parent_purges_the_log_folder_and_traces_it(log: Log, tmp_path: Any) -> None:
    old = _touch(tmp_path / "dynOLD.log", age_days=400)
    log.handler = MagicMock()
    log.purge_logs_if_due()
    assert not os.path.exists(old) and os.path.exists(log.log_file)      # its own file is never removed
    assert "dynOLD.log" in _written(log)
    # Rate limited: a file that becomes old right after is kept until the next interval
    again = _touch(tmp_path / "dynAGAIN.log", age_days=400)
    log.purge_logs_if_due()
    assert os.path.exists(again)


def test_replicas_never_purge(log: Log, tmp_path: Any) -> None:
    old = _touch(tmp_path / "dynOLD.log", age_days=400)
    log.handler = None
    log.purge_logs_if_due()
    assert os.path.exists(old)


def test_the_retention_is_configurable_from_the_environment(log: Log, tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    kept = _touch(tmp_path / "dynTENDAYS.log", age_days=10)
    log.handler = MagicMock()
    monkeypatch.setenv("DYNREACT_LOG_RETENTION_DAYS", "5")
    log.purge_logs_if_due()
    assert not os.path.exists(kept)
