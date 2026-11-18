# Log module

First Prototype of Kubernetes oriented solution for the LOG service

---

## Log files, rotation and retention

Every auction has its own LOG agent, which stores all the messages of the topic in `<LOG_FILE_PATH>/<topic>.log`.
Every message is stored: those without `payload.identifier` get `-` as identifier, and those without
`payload.msg` are stored as their JSON payload.

Two mechanisms keep the folder from growing without limit:

* **Rotation.** Each log file rotates weekly (Monday, UTC) into `<topic>.<YYYY-MM-DD>.log`, and only the
  newest rotated files are kept.
* **Retention.** The parent LOG removes, at startup and then every hour, the `*.log` files of the folder
  that have not been written for a number of days, which cleans the files of finished auctions. Its own
  file is never removed. Every removal is recorded in its log.

| Variable | Default | Description |
| --- | --- | --- |
| `DYNREACT_LOG_ROTATE_WHEN` | `W0` | Rotation of the files: `W0`-`W6` (weekly, `W0` is Monday), `midnight` (daily)... |
| `DYNREACT_LOG_BACKUP_COUNT` | `8` | Rotated files kept for each log file. Zero keeps all of them. |
| `DYNREACT_LOG_RETENTION_DAYS` | `30` | Days without writing after which a log file is removed. Zero or negative disables the purge. |

---

## Log class

::: dynreact.shortterm.agents.log.Log
    options:
        docstring_style: google
        show_signature: true
        show_source: false

## LogWithExtensionHandler class

::: dynreact.shortterm.agents.log.LogWithExtensionHandler
    options:
        docstring_style: google
        show_signature: true
        show_source: false

## purge_old_logs function

::: dynreact.shortterm.agents.log.purge_old_logs
    options:
        docstring_style: google
        show_signature: true
        show_source: false
