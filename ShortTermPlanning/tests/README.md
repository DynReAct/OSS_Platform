# Tests of ShortTermPlanning

## Unit tests

Run them from `OSS_Platform/ShortTermPlanning`:

```commandline
python -m pytest tests/unit_tests -q
```

They need neither a Kafka broker nor a Docker daemon: both are replaced by mocks, and the autouse fixture `stp_config` in
`conftest.py` gives every test the same known STP configuration and restores the previous one afterwards, so they can
run in any order.

| File | Protects |
| --- | --- |
| `test_agent.py` | Message loop shared by every agent: routing by destination regex, ignoring other topics, dispatch of actions, survival of a failing handler (`RECIEVEERROR`), end of the loop with `EXIT`, and the reaper interval setting. |
| `test_material.py` | MATERIAL auction protocol: bidding price, `BID` to `COUNTERBID`, single commitment on `ASKCONFIRM` (the rest receive `ASSIGNED`), transport times and origin fallback, and cloning of replicas only by the parent. |
| `test_equipment.py` | EQUIPMENT auction protocol: `START` invites the materials to bid, `COUNTERBID` becomes a bid (profit = price minus cost, tardiness), ordering of the bids, one confirmation request at a time after `COUNTERBID_WAIT`, end with `EQUIPMENTFINISHED` when no bids are left or the target tonnage is reached, `CONFIRM` from the wrong material, `ASSIGNED` elsewhere, and cloning of replicas only by the parent. |
| `test_log.py` | LOG agent: writing to the log file (every message is stored, with `-` when it has no identifier), recording `CONFIRM` messages as results, pinging and counting agents, starting the auction exactly once, completion when every expected equipment finished, serving the results and ending the auction once, weekly rotation with a limited number of backups, purge of old log files by the parent, and cloning of replicas only by the parent. |
| `test_reaper.py` | Container lifecycle: the three reaper rules, no kill when Kafka is unknown, resilience to Docker errors, constant-cost launches, `max_allowed`, and the Kafka cleanup of an auction (`cleanup_auction`). |
| `test_common.py` | Dump of the configuration without stale environment overrides, and container diagnostics. |
| `test_auction_model.py`, `test_equipment_order_semantics.py`, `test_replace_base.py` | Auction model, order semantics of the equipment and replacement of the base agents. |

## Writing new tests

* Build agents with `Producer`, `Consumer` and `DockerManager` patched, as `_make()` in `test_material.py` does.
* Patch `sendmsgtopic` in the module under test and assert on its keyword arguments (`action`, `dest`, `payload`):
  they are the contract with the other agents.
* Every test documents the behaviour it protects in its name. Add a docstring when the reason is not obvious.
* Integration tests (`tests/integration_test`) need a live Kafka broker and a Docker daemon.


The shared-channel concurrency regressions live in `unit_tests/test_shared_messaging.py`
and `integration_test/test_exit_cleanup.py`. They run offline with Kafka mocked.
`integration_test/test_shared_messaging_kafka.py` is opt-in (`MESSAGING_TEST_KAFKA=1`,
`KAFKA_IP` set) and creates/deletes only its own UUID-named TEST topics. Both
Jenkins images run these checks before publication. See
[Shared messaging](../docs/shared_messaging.md) for guarantees and operations.
