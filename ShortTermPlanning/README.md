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
