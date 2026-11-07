# ShortTerm scenario from the DynReAct project

## Introduction

The repository comes with a Short Term sample scenario, defined in **dynreact** subfolder.
It does include several agent prototypes, such as

* **log.py**: Log Agent, in charge for recording all the messages

* **equipment.py**: Resource Agent (plants), in charge of handling the auction's bids 
                   considering the different setup status parameters.

* **material.py**: Material Agent (coils), in charge of representing the status
                   of the material and its willingness to offer for a slot in the
                   next auction. Confirmed assignments are interpreted at order
                   level for accumulated tonnage and processing duration.

* **ShortTermPlanning.py**: Main script in charge of simulating several contexts for
                   the auction. 
		   The scenario requires to have a Kafka broker avaliable to all the
                   agent instances.
                   To make possible to reset the broker queues a tool has been created
                   and named **clean_kafka.py**.


## Prerequisites

Python versions >= 3.10 and <= 3.12 should be supported. 

### Install dependencies

#### Pip environment

First, create a virtual environment for the project. Navigate to the folder, and execute

```commandline
python -m venv --upgrade-deps venv
```

You can run the setup by installing dependencies:

```commandline
pip install -r requirements.txt  [--break-system-packages]
```

Then, you can build the packages

```commandline
pip wheel . --no-cache-dir --disable-pip-version-check --no-deps --wheel-dir dist
```

#### Poetry approach

First, if not there, create a virtual environment for the project. Navigate to the folder, and execute

```commandline
pipx install poetry
poetry install --no-root
eval $(poetry env activate)

```

Then you can build packages

```commandline
poetry build

```



## Run

Different use cases can be simulated by testing the following commands:

```commandline
python3 ShortTermPlanning.py -v 3  -b . -rw 10 -cw 30 -aw 50 -bw 15 -ew 10 -r 6 -n 1
python3 ShortTermPlanning.py -v 3  -b . -rw 10 -cw 30 -aw 50 -bw 15 -ew 10 -r 6 -n 2
python3 ShortTermPlanning.py -v 3 -b . -rw 10 -cw 30 -aw 200 -bw 15 -ew 10 -r 6 7 -n 1
python3 ShortTermPlanning.py -v 3 -b . -rw 10 -cw 30 -aw 200 -bw 15 -ew 10 -r 6 7 -n 4
python3 ShortTermPlanning.py -v 3 -b . -rw 100 -cw 300 -aw 1200 -bw 45 -ew 100 -r 6 7
```

Be sure that the live kafka broker  and the live cost service have been properly configured in the file *config.cnf*.

## Container lifecycle and reaper

Each auction clones the parent agents (LOG, EQUIPMENT, MATERIAL) into one Docker container per child agent.
Under continuous use, such as the Recommender, these containers would pile up, so the parent agents run a
*reaper* from their message loop. It removes, among the containers launched by that parent only:

- exited containers, after a grace period that leaves time to read their diagnostics;
- running containers older than a maximum age (stuck);
- running containers whose auction topic no longer exists in Kafka (orphans, nobody will send them `EXIT`).

Every removal is recorded in the LOG of the parent agent, with the container names and the rule applied.

The Recommender also deletes the Kafka topic and consumer groups of each auction once it ends
(`cleanup_auction`). The reaper can be tuned with environment variables:

| Variable | Default | Description |
| --- | --- | --- |
| `DYNREACT_REAPER_INTERVAL` | `60` | Seconds between sweeps. Zero or negative disables the reaper. |
| `DYNREACT_REAPER_EXITED_GRACE` | `300` | Seconds an exited container is kept. |
| `DYNREACT_REAPER_MAX_AGE` | `10800` | Seconds after which a running container is considered stuck. |
| `DYNREACT_REAPER_TOPIC_GRACE` | `1800` | Minimum age of a container before its topic is required to exist. |

Launching a container no longer inspects every existing container, so the launch cost is constant.
See the *Handler* page of the documentation for details.

## Log files

The LOG agent of each auction stores every message of the topic in `<LOG_FILE_PATH>/<topic>.log`. The files rotate
weekly, keep the newest rotated ones, and the parent LOG removes the log files that have not been written for
30 days. See the *Log* page of the documentation for the `DYNREACT_LOG_*` variables.

## Tests

The unit tests run without Kafka or Docker:

```commandline
python -m pytest tests/unit_tests -q
```

See [tests/README.md](tests/README.md) for what each file protects and how to write new tests.

## Multi-VM deployment and registry scripts

Use `extras/deployment/deploy_parents.sh ras|oss IMAGE_TAG` to preload the selected
image on profile workers and start the three parents locally with verbose 1.
`list_registry_images.sh PROFILE` lists tags and dates;
`prune_registry_images.sh PROFILE DAYS` previews age-based manifest cleanup
(`DYNREACT_APPLY=1` applies it). See [deployment and registry operations](docs/deployment.md)
for env-file templates, SSH permissions, load-aware placement and protection limits.

## OSS analytical costs and auction startup

The OSS service uses `SampleCostProvider` from the `SampleUseCase` package.
Install that package in the service virtual environment and configure the service
(using `.env_OSS` as the template):

```ini
DYNREACT_PROFILE=oss
COST_PROVIDER=class:dynreact.cost.CostCalculatorImpl.SampleCostProvider,sampleuc:costs
TOPIC_GEN=Dynreact-OSS-Gen
TOPIC_CALLBACK=Dynreact-OSS-Callback
```

The service's `dynreact.cost` package extends its package path so local providers
and installed providers remain discoverable together. Do not copy the analytical
formula into a local `oss.py`. A `SimpleCostProvider` without a transition table
is not equivalent to the analytical provider. For FIN02, transitions between
different orders cost `1 + 0.1 * abs(width1 - width2)`, plus 10 when finishing
types differ; a missing previous order or the same order costs zero.

After deployment, restart the service and validate from its working directory:
import `dynreact.cost.CostCalculatorImpl.SampleCostProvider`, then query
`/costs/status/{equipment}/{snapshot}?unit=material` and POST known snapshot
orders/materials to `/costs/transitions` and `/costs/transitions-stateful`.
Check HTTP success and the expected cost, not only systemd running status.
These cost endpoints evaluate requests without launching auctions. Agents can
fall back to zero costs on HTTP failures, so auction activity alone does not
prove that analytical costs are enabled.

The UI uses `Materials`; `Coils` remains a supported legacy alias in `Auction`.
Startup counts `smats`, the material IDs actually sent for replica creation,
for both material and order scheduling. One equipment, four materials and one
LOG must therefore yield six expected agents. An incorrect expected count of
two is a UI/model issue, not a reason to restart parent agents. Deploy the
updated ShortTermPlanning package in the service environment as well.

Topic names are case-sensitive and must match those of the running parents.
Use a new auction reference after a failed startup because failure cleanup may
have deleted the previous auction topic.

Run the focused regression checks from the repository root:

```sh
PYTHONPATH=OSS_Platform/DynReActService:OSS_Platform/DynReActBase:OSS_Platform/SampleUseCase:OSS_Platform/ShortTermPlanning python OSS_Platform/ShortTermPlanning/tests/regression/test_oss_startup.py
```

### Empty-line stateful costs

An empty line has `current_order: null`. The agent must call
`POST /costs/transitions-stateful` even for its first candidate; a zero setup cost
must not bypass simulation. The stateful request accepts a null previous order.
The service validates the next material and invokes the cost provider with
`current=None` and `new_lot=True` to initialize the simulated assignment.
Providers used by this endpoint must support this empty-line update.

`SampleCostProvider` returns a deep copy with the new order/material, one lot,
its material weight (or order weight in order mode), updated order count,
remaining target weight and objective. The first transition adds zero setup
cost; the overall objective may still include production and logistics terms.
The response `costs` remains an objective object, not a scalar zero. The STP
agent reads the cumulative `status.planning.transition_costs` as before.
Further materials of the same order update material IDs and tonnage without
adding another order or setup cost.

Candidate evaluation does not mutate the input state. The equipment adopts the
returned state on confirmed assignment (`move_to_next_round`); later rounds use
that state. For FIN02, assigning order7 (995 mm) to an empty line costs zero;
then order3 (980 mm, same finishing type) adds 2.5. With material weights 11 t
and 15 t and a 100 t target, remaining weight must change 100 -> 89 -> 74 t.

Run the agent/HTTP/provider regression (no Kafka or Docker required):

```sh
PYTHONPATH=OSS_Platform/DynReActService:OSS_Platform/DynReActBase:OSS_Platform/SampleUseCase:OSS_Platform/ShortTermPlanning:OSS_Platform/MidTermPlanning python OSS_Platform/ShortTermPlanning/tests/regression/test_empty_line_costs.py
```

Deployment requires updating DynReActService, SampleUseCase and ShortTermPlanning
in the service environment. Rebuild the ShortTermPlanning agent image and deploy
the parents with that image when no auctions are active; a service restart alone
does not update code inside Docker agents. Existing children keep their old code.
Validate a new auction and confirm the stateful requests and advancing order IDs.
The existing HTTP-error fallback in the agent still returns zero with unchanged
state; HTTP errors must therefore be checked separately from valid zero-cost
first assignments.

### Zero-valued fields in stateful responses

`/costs/transitions-stateful` serializes default-valued state fields, including
`status.planning.transition_costs: 0.0`. A legitimate zero setup cost must not be
confused with a malformed response. The agent also accepts older responses that
omit this field: a missing transition cost within a valid `planning` object is
interpreted as zero, while the returned simulated state is retained. Missing
`status` or `planning` objects are still handled as invalid responses.
The empty-line regression suite covers both explicit-zero HTTP responses and
legacy responses without the zero field. Deploy the service change and rebuild
and redeploy agent images to install the compatibility change in the agents.

### OSS STP callback registration at startup

Dash sends the callback dependency graph to the browser before the user visits
STP. Registering the default OSS callbacks only from the STP page layout leaves
the first browser session without the equipment-to-orders/materials callback,
even though subsequent direct requests to that callback return data.

`DynReActService/dynreact/gui/dash_app.py` preloads `state.get_stp_page()` at the
end of initialization, only when `STP_FRONTEND=default`. At that point the Dash
application and shared callbacks already exist, so `agentsPage` can import the
application without the circular initialization encountered during page discovery.
Custom frontends, including RAS, retain their preload in `pages/stp_page.py`.
The loader's existing error-page handling is retained for unavailable frontends.

The equipment selector populates available orders/materials but leaves the
selection empty until the user chooses entries. For the supplied OSS snapshot,
Orders + FIN01 offers `order3` and `order6` with `value=[]`. This is intentional;
an empty selection does not imply empty options.

The cold-start regression runs in a new process and checks the very first
`/_dash-dependencies` response, the FIN01 callback, and HTTP access to STP, LTP
and MTP routes. Existing profile-loader tests cover custom-frontend preloading.
From the repository root, with the service dependencies installed:

```sh
PYTHONPATH=OSS_Platform/DynReActService:OSS_Platform/DynReActBase:OSS_Platform/SampleUseCase:OSS_Platform/ShortTermPlanning:OSS_Platform/MidTermPlanning python -m unittest discover -s OSS_Platform/DynReActService/tests/integrationtests -p test_stp_initial_dependencies.py -v
```

Deploy the updated DynReActService and restart the OSS GUI service. Reload any
browser tabs that fetched dependencies before the fix. This callback-registration
change does not require rebuilding agent images or modifying LTP/MTP algorithms.
