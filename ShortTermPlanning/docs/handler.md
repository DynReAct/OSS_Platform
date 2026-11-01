# Handler module

Docker lifecycle of the agents. The parent agents (LOG, EQUIPMENT and MATERIAL) use a
`DockerManager` to launch one container per child agent of an auction, and to remove the
containers that are no longer useful.

---

## Container lifecycle

Auction children of all three roles (MATERIAL, EQUIPMENT, LOG) now use
`auto_remove=True`: Docker removes their container as soon as the process exits,
including a failed exit. Persistent parents keep `auto_remove=False` and are
started with `restart unless-stopped` by the deployment script. A direct manager
launch defaults to auto-removal for replicas and retention for bases; callers can
explicitly retain a diagnostic replica, but cannot auto-remove a persistent base.

Container exit metadata and `docker logs` are unavailable after auto-removal.
Application logs explicitly written to the bind-mounted log directory survive;
stdout-only output needs an external collector if it must be retained. The reaper
still handles stuck/orphan running children and retained legacy/diagnostic exited
containers. Lifecycle cleanup tolerates concurrent Docker auto-removal. A child
that vanishes before its first inspection is reported with unknown exit status;
this does not certify successful auction completion or restore failed work.

Rebuild/publish OSS and RAS images and recreate parents to activate the change.
Existing containers keep the HostConfig with which they were created.

Every container is labelled when it is launched:

| Label | Content |
| --- | --- |
| `owner` | Tag of the `DockerManager` that launched it (namespaced with `CONTAINER_NAME_PREFIX`). |
| `dynreact.topic` | Kafka topic of the auction the container belongs to. |
| `dynreact.created` | Launch time, in epoch seconds. |

Each parent agent sweeps its own containers (`owner` label) at most every
`DYNREACT_REAPER_INTERVAL` seconds, from its message loop. The sweep applies three rules:

1. **Exited** containers are removed `DYNREACT_REAPER_EXITED_GRACE` seconds after they finish.
2. **Stuck** containers, running for longer than `DYNREACT_REAPER_MAX_AGE` seconds, are removed.
3. **Orphan** containers, older than `DYNREACT_REAPER_TOPIC_GRACE` seconds whose auction topic no
   longer exists in Kafka, are removed. The rule is skipped when Kafka cannot be queried.

The sweep never raises, so a Docker or Kafka failure cannot stop a parent agent.

| Variable | Default | Description |
| --- | --- | --- |
| `DYNREACT_REAPER_INTERVAL` | `60` | Seconds between sweeps. Zero or negative disables the reaper. |
| `DYNREACT_REAPER_EXITED_GRACE` | `300` | Seconds an exited container is kept to read its diagnostics. |
| `DYNREACT_REAPER_MAX_AGE` | `10800` | Seconds after which a running container is considered stuck. |
| `DYNREACT_REAPER_TOPIC_GRACE` | `1800` | Minimum age of a container before its topic is required to exist. |

---

## DockerManager class
::: dynreact.shortterm.common.handler.DockerManager
    options:
        docstring_style: google
        show_signature: true
        show_source: false

---

## Traceability

Every sweep that removes containers writes one line to the LOG of the parent agent (general topic),
with the number of containers removed per rule and their names, for example
`Reaper of MATERIAL:dynGen removed 2 containers {'exited': 1, 'stuck': 0, 'orphan': 1}: JENKINS_MATERIAL_x (exited), ...`.
The same line is printed to the standard output of the parent container.
