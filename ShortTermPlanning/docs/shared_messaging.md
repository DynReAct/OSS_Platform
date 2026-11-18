# Concurrent auctions and shared Kafka channels

## Ownership and the failure being prevented

`TOPIC_GEN` is the control channel consumed independently by the parent LOG,
EQUIPMENT and MATERIAL agents. `TOPIC_CALLBACK` carries replies to application
clients. Both channels belong to the runtime context, not to an individual
auction. The `topic` field in a CREATE envelope identifies the auction whose
replicas the parent should launch; it does not change the ownership of the
Kafka channel on which that envelope is stored.

Previously the OSS GUI purged both shared channels before Create. Both GUIs
also purged them after a failed Start, and the parent LOG purged them when its
loop ended. `purge_topics()` used `delete_records` with `OFFSET_END`, removing
records for every auction sharing those partitions. Creating B could therefore
erase A's queued CREATEs or replies. Shutting down the LOG did not prove that
all clients and other parents had finished using those records.

Message age is not a safe substitute for ownership. An old CREATE can still be
needed by a busy parent, and a recently written reply can already be obsolete.
Kafka DeleteRecords removes a prefix of each partition, rather than selected
messages belonging to an auction. A lag observation is specific to a consumer
group and can change immediately after it is measured.

## Runtime invariants

1. Create, Start failure, Refresh, auction termination and parent shutdown never
   purge shared channels. Replacing TEST parents also preserves their history.
2. An auction topic is reserved with Kafka's atomic CreateTopics operation
   before any CREATE is published. A failed reservation publishes no CREATE.
   The advisory existence check alone is insufficient under concurrent users.
3. Every callback reader has its own group identifier and explicit partition
   assignment. It cannot take another reader's share of callbacks.
4. Every status/results request has a fresh `request_id`. LOG echoes it in the
   callback envelope. A client accepts only its exact source, destination,
   action and request ID.
5. Parent offsets remain independent for each agent kind. A shutdown persists
   its processed EXIT offset synchronously and never deletes sibling history.

The auction's Kafka topic remains its execution identity. Use a new auction
name for a new execution; do not recycle a deleted name while old commands or
replicas may remain. One driver should control the lifecycle of a given
auction; multiple independent auctions may share the parent channels.

## Callback protocol and readers

`create_callback_consumer(kafka_ip, callback_topic)` creates the callback topic
if necessary without altering an existing topic's configuration. It reads the
high watermark of each callback partition and explicitly assigns those numeric
offsets before returning. Callers construct the reader **before** sending a
request. This avoids replaying historical replies and avoids the subscribe /
latest race in which initial assignment happens after the requested reply has
already arrived. All OSS GUI, RAS GUI, CLI and Recommender callback readers use
this helper. Do not call `subscribe()` afterward: that replaces its assignment.

For example, a request addressed to `LOG:auction-A` includes:

```json
{"topic":"auction-A","source":"UX","dest":"LOG:auction-A","action":"ASKRESULTS","request_id":"unique-request-id"}
```

The callback still uses the configured callback channel in its `topic` field,
and retains the existing results/status payload shape. Its source is
`LOG:auction-A`, destination is exactly `UX`, and its `request_id` equals the
request's ID. Repeated status polls generate different IDs, so delayed replies
from a previous poll cannot satisfy the current one. Existing legacy callers
that omit an ID still receive replies without an ID; updated callers require
an ID and deliberately reject uncorrelated legacy replies.

`wait_for_callback()` enforces a wall-clock budget of
`max_iters * max(1, sleep_timeout)` seconds. Traffic for other auctions, malformed
records, broker errors and repeated irrelevant records cannot reset that
budget. The callback reader commits no offsets and never acknowledges parent
work. Readers are closed on completion/failure; factory failures close a
partially constructed consumer too. A fixed deadline can still expire under
sustained overload: failure is bounded rather than silently returning another
auction's reply.

## Parent restart and abandoned commands

Parents disable automatic offset commits and automatic offset storage.
Accepted dispatches and intentionally ignored records are acknowledged
synchronously. In particular, a processed EXIT is persisted before closing the
consumer. Each parent keeps its existing stable agent-specific group name, so
ordinary restarts resume its own progress rather than replaying all history.

At first assignment of each general-topic partition, the parent records its
high watermark without advancing its consumer position. An EXIT below that
boundary addresses a previous parent incarnation and is ignored. Pending
CREATEs are still read. The initial boundary survives rebalances and uses Kafka
offsets, not wall-clock age or cross-machine clock synchronization. A current
shutdown request must be sent after the new parent has obtained its initial
assignment; shutdown commands queued while it was offline do not shut down the
new incarnation.

Before dispatching a CREATE, a parent checks that the auction topic still
exists and is not a shared channel. Missing auction topics mean the request
has been abandoned; other live auctions are unaffected. If topic metadata
cannot be obtained, the parent seeks back to the same record and retries
without acknowledging it. A CREATE that carries different `TOPIC_GEN`,
`TOPIC_CALLBACK` or `KAFKA_IP` variables is ignored rather than changing the
shared parent's routing to a different context. The metadata check requires a
broker round trip per CREATE; it does not infer abandonment from message age.

These checks do not make Docker launches transactional with Kafka offsets.
CREATE dispatch queues Docker work asynchronously. Normal shutdown drains
accepted launch jobs instead of cancelling them. A parent crash after
acknowledging queue acceptance can still lose an in-memory launch, and a crash
between a side effect and its offset commit can cause redelivery. Durable
launch receipts/idempotency are a separate concern. Likewise, deleting an
auction after its existence check can race a queued launch; the existing
parent reaper removes replicas whose auction topic has disappeared. Preserve
topics until the auction is finished, and use startup diagnostics to detect
missing agents.

## Cleanup and retention

`purge_topics()` and `delete_topics()` reject an entire request containing a
configured shared channel before making any broker call. `silent=True` does
not bypass this guard. `cleanup_auction()` and `end_auction()` also reject shared
channels. Cleanup of a failed GUI Start is restricted to that auction's topic;
a cleanup failure is logged without replacing the startup failure message.

The compatibility hooks `should_purge_exit_history()` and
`purge_exit_history_if_needed()` remain available but respectively return False
and do nothing. `delete_all_topics()` requires an explicit `offline=True` and
still preserves the configured shared channels. It is not an auction lifecycle
operation and must not run against concurrent auctions.

An explicit `allow_shared=True` exists for direct purge/delete utilities only
for offline maintenance in a context owned exclusively by the operator. No GUI,
CLI, Recommender, parent shutdown, replace-base command or verification fixture
uses it. Stop all producers and consumers before deliberately removing shared
history; a timestamp or zero observed lag does not establish that condition.

LOG-created topics now use the broker's retention defaults instead of forcing
`retention.ms=30000`. This does **not** modify existing topics. During deployment,
inspect existing general, callback and auction topic configurations and remove
or increase any old 30-second override in the appropriate maintenance window.
Choose retention for the maximum supported auction duration, parent outage and
backlog, with capacity headroom. Broker retention can still delete unconsumed
records after its configured limit; this change does not promise infinite
message retention. Pre-provision topics with the desired replication factor
and retention in deployments that require different broker defaults.

## Deployment and Jenkins compatibility

Deploy the updated common helpers, planner, parent agents, LOG replicas and
clients together. Restart existing parents with the updated image; existing
LOG replicas do not gain request-ID echoing until recreated. An updated client
will time out against an old replica rather than accept an unrelated reply.
The RAS Dockerfile explicitly copies `short_term_planning.py` and
`replace_base.py` from the same OSS checkout as common/agents, preventing a new
caller protocol from being combined with an old base-image implementation.
The local RAS GUI build-context preparation includes both files too.

Both Jenkinsfiles run `Shared Messaging Regression` against the newly built
local image before pushing it. The stage runs mocked concurrency/shutdown
regressions and two real-broker checks. The real checks require the job's normal
Kafka connectivity and permissions to create, describe and delete **their own
UUID-named TEST topics**; no Docker socket, registry or REST service is needed.
They never purge the pipeline's parent channels. `MESSAGING_TEST_KAFKA=1`
explicitly enables them; ordinary offline test runs skip them.

Each pipeline now derives the auction prefix, general channel and callback
channel from a sanitized build context, rather than sharing fixed TEST channels
across builds. Replica containers inherit these values through the existing
DockerManager configuration. Scenario 0-8 entry points, selected snapshots,
immutable runtime image tags and expected result assertions are preserved.
The integration fixture only purges its private `DYN_TEST` scratch topic, while
replace-base retains shared records and historical EXITs are handled by parent
assignment boundaries. Completed build contexts may be removed later by an
operator after confirming their jobs/parents have stopped; no broad broker
cleanup is introduced into Jenkins.

The runtime requires Kafka permissions to reserve auction topics. A metadata
or provisioning error fails the operation; it never falls back to purging
shared history. This is also why mixing an updated bind-mounted planner with
an older common/LOG package is unsupported.

## Verification

`tests/unit_tests/test_shared_messaging.py` covers whole-batch cleanup guards,
independent readers and partition positions, existing-topic provisioning,
factory failure cleanup, interleaved/delayed replies, bounded waits under other
auction traffic, LOG correlation, abandoned/active CREATEs, unavailable
metadata, foreign routing, historical/current EXITs, rebalance boundaries and
reservation failure before publishing commands.

`tests/integration_test/test_exit_cleanup.py` checks all three parent kinds
close without invoking topic administration. The opt-in
`tests/integration_test/test_shared_messaging_kafka.py` verifies two actual Kafka
readers receive only their own correlated replies, queued general-channel work
survives, and an atomic reservation failure cannot publish another CREATE.

To run the broker checks against a dedicated local broker:

```bash
MESSAGING_TEST_KAFKA=1 KAFKA_IP=127.0.0.1:9092 \
python -m pytest -q tests/integration_test/test_shared_messaging_kafka.py
```

The fixtures generate their own topic names and remove those exact topics in
teardown. Full Jenkins auction scenarios additionally exercise Docker launches,
REST snapshot access and remote worker infrastructure; passing the messaging
regressions alone does not establish the availability of those external
services.

### Jenkins startup scenarios and snapshot failures

Scenarios 00 and 01 replace the auction creator with a test double and have no
participating equipment. Scenario 02 creates a LOG replica without equipment
or materials. These lifecycle checks must not depend on the snapshot REST
service or transport-time data. An empty equipment order scope returns
immediately; LOG-only creation does not construct `DataSetup` or fetch
transport times. The CLI computes result filtering only for an actual auction
with more than one agent, inside its lifecycle `try/finally`.

This distinction fixes a failure observed after the shared-messaging stage had
passed: Scenario 00 made an unnecessary
`GET /snapshots/2025-01-18T08:00:00Z` while calculating an empty order scope, and
a snapshot HTTP 500 failed the parent-startup test before its cleanup block.
Snapshot errors for genuine equipment/material auctions remain errors and
propagate to the caller. If result-scope preparation fails after creation, the
CLI closes its callback reader and executes auction/parent termination.

`tests/unit_tests/test_cli_lifecycle.py` reproduces the parent-only scenarios
with an unavailable snapshot service, tests LOG-only creation without snapshot
or transport access, verifies real material creation still loads its data, and
checks cleanup and error propagation for a real auction's HTTP 500. Both
Jenkins shared-messaging stages run this suite before publishing the image.
Skipping REST in an empty lifecycle check does not repair an unavailable or
invalid snapshot used by subsequent equipment scenarios; those need a working
service and the configured snapshot.


### Pinned OSS regression dataset and readiness gate

The OSS job pins `SNAPSHOT_VERSION=2024-12-31T11:00:00Z` and
`SCENARIO_8_ORDER_ID=order7`. The previous January 2025 timestamp is absent from
the confirmed OSS endpoint (port 5016); the other profile's endpoint (port 5026)
is not an interchangeable source. The OSS dataset contains `FIN01`/`FIN02`
(equipment 6/7), while RAS uses different equipment names. Do not select an
arbitrary latest snapshot to make the job pass: scenario data must be checked
with the same selection rule used by the auction tests.

`OSS Snapshot Readiness` runs in the newly built image before publication or
parent startup. Its read-only `extras/snapshot_preflight.py` verifies the OSS
equipment identity, loads the exact pinned timestamp, validates material/order
references, runs the real scenario 4-8 material selector, checks that the
scenario-8 expected order is selected, and loads initial material-based cost
statuses for the participating equipment. It has bounded HTTP timeouts and
never prints the credential-backed endpoint, response bodies or exception
messages. The job forwards the configured equipment/order variables to each
scenario container, including the scenario-8 positive result assertion.

Live verification on the OSS service found 8 orders and 15 materials at the
pinned timestamp. Scenario 6 can select two distinct FIN02 orders (`order7` and
`order8`); scenario 8 selects one FIN01 order and two FIN02 orders. The selector
intentionally permits fewer than the requested count in a multi-equipment
auction when remaining orders are shared; the result assertions calculate the
expected count using that same rule. Both equipment initial-cost requests
returned HTTP 200. This establishes data readiness, not a complete distributed
auction execution.

The snapshot GET endpoint now returns HTTP 404 when the provider returns no
snapshot, instead of dereferencing None and returning HTTP 500. That API change
requires deployment of the updated DynReActService; changing the Jenkins date
works with the currently deployed service and does not require that deployment.
`test_snapshot_preflight.py` covers wrong dates, substituted timestamps, wrong
profiles, incompatible selections, missing order references, unavailable
services and credential-safe diagnostics.
