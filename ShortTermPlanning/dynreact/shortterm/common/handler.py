"""Common short-term planning utilities for OSS_Platform/ShortTermPlanning/dynreact/shortterm/common/handler.

The module is documented in English to make the short-term planning
workflow easier to maintain across OSS and RAS-specific integrations.
"""

from typing import Any
import json
import os
import shlex
import re
import time
import docker
from datetime import datetime, timezone

from dynreact.shortterm.common import KeySearch
from dynreact.shortterm.common.remote_pool import RemoteDockerPool, worker_endpoints


LABEL_TOPIC = "dynreact.topic"
"Label with the auction topic a container belongs to"
LABEL_CREATED = "dynreact.created"
"Label with the epoch seconds at which a container was launched"

REAPER_EXITED_GRACE = 300.0
"Seconds an exited replica is kept, for diagnostics, before it is removed"
REAPER_MAX_AGE = 10800.0
"Seconds after which a still running replica is considered stuck and is removed"
REAPER_TOPIC_GRACE = 1800.0
"Minimum age in seconds of a running replica before its auction topic is required to exist"


def _env_float(name: str, default: float) -> float:
    """Read a positive float from the environment, falling back to the default when unset or invalid."""
    try:
        value = float(os.environ.get(name, ""))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _parse_docker_time(value: Any) -> float | None:
    """Convert a Docker timestamp into epoch seconds. Returns None for unset or unparsable values."""
    if not value or str(value).startswith("0001-01-01"):
        return None
    text = str(value)
    # Docker gives nanosecond precision, datetime only accepts microseconds
    if "." in text:
        head, _, tail = text.partition(".")
        digits = "".join(ch for ch in tail if ch.isdigit())[:6]
        text = f"{head}.{digits}+00:00"
    else:
        text = text.rstrip("Z") + "+00:00"
    try:
        return datetime.fromisoformat(text).astimezone(timezone.utc).timestamp()
    except ValueError:
        return None


def _namespaced_tag(tag: str | None) -> str | None:
    """Scope Docker owner labels to the active Jenkins/runtime context when available."""
    if not tag:
        return tag
    context_prefix = (os.environ.get("CONTAINER_NAME_PREFIX") or "").strip()
    if not context_prefix:
        return tag
    return f"{context_prefix}:{tag}"


def _container_state_details(container: Any) -> dict[str, Any]:
    """Extract the most relevant Docker state details for diagnostics."""
    state = getattr(container, "attrs", {}).get("State", {}) or {}
    exit_code = state.get("ExitCode")
    return {
        "exit_code": exit_code if exit_code not in (None, "") else None,
        "oom_killed": bool(state.get("OOMKilled", False)),
        "error": state.get("Error") or None,
        "started_at": state.get("StartedAt") or None,
        "finished_at": state.get("FinishedAt") or None,
    }


def _container_status_reason(container_info: dict[str, Any]) -> str:
    """Render a short human-readable explanation for one tracked container."""
    reason_bits = []
    if container_info.get("oom_killed"):
        reason_bits.append("oom-killed")
    exit_code = container_info.get("exit_code")
    if exit_code is not None:
        reason_bits.append(f"exit_code={exit_code}")
    error = container_info.get("error")
    if error:
        reason_bits.append(f"error={error}")
    finished_at = container_info.get("finished_at")
    if finished_at and finished_at != "0001-01-01T00:00:00Z":
        reason_bits.append(f"finished_at={finished_at}")
    if not reason_bits:
        return container_info.get("status", "unknown")
    return f"{container_info.get('status', 'unknown')}: " + ", ".join(reason_bits)


class DockerManager:
    """Docker manager.
    
    This class belongs to the short-term planning integration layer. It
    encapsulates state, configuration, or UI behavior used by the planning
    workflow without changing the runtime semantics of the original module.
    """
    def __init__(self, tag: Any="default_tag", max_allowed: Any = -1) -> None:
        """
        Initialize Docker client and set a tag to track owned containers.

        :param tag: Unique tag to identify containers launched by this instance.
        """
        self.profile = os.getenv('DYNREACT_PROFILE', 'oss').lower()
        if self.profile not in ('oss','ras'):
            raise ValueError('DYNREACT_PROFILE must be oss or ras')
        self.remote_workers = worker_endpoints(self.profile)
        self.client = (RemoteDockerPool(self.profile, self.remote_workers)
                       if self.remote_workers else docker.from_env())
        if self.remote_workers:
            os.environ.setdefault('CONTAINER_NAME_PREFIX', f'dynreact-{self.profile}')
        self.tag = _namespaced_tag(tag)
        self.max_allowed = max_allowed
        self.tracked_containers = []
        self.last_reaped: list[str] = []

    @staticmethod
    def _normalize_container_name(name: str) -> str:
        return name[1:] if name.startswith("/") else name

    def _build_labels(self, params: dict) -> dict[str, str]:
        """Labels used to track ownership, the auction of the container and its launch time."""
        labels = {LABEL_CREATED: str(int(time.time()))}
        if self.tag:
            labels["owner"] = self.tag
        topic = params.get("topic") if isinstance(params, dict) else None
        if topic:
            labels[LABEL_TOPIC] = str(topic)
        return labels

    def _count_owned_containers(self) -> int:
        """Count the containers of this manager with one cheap listing (no per-container inspection)."""
        return len(self.client.containers.list(filters={"label": f"owner={self.tag}"} if self.tag else {}, all=True))

    def launch_container(self, name:str, agent:str, mode:str, params:dict, envs: dict[str, str] | None = None, auto_remove: bool | None=None) -> Any:
        """Launches a new Docker container and labels it for ownership, auction and launch time.

        The container count and the name-collision check use one filtered listing each,
        without inspecting the existing containers, so the cost of a launch does not grow
        with the number of containers already running.

        Args:
            name: Name for the container.
            agent: Name of the agent (log, equipment, material).
            mode: Whether the agent runs as a replica or as the manager (base).
            params: Dictionary of python params. Its ``topic`` entry labels the container with its auction.
            envs: Dictionary of environment variables.
            auto_remove: Remove after execution; defaults to True for replicas and False for bases.

        Returns:
            The container object, or None when the container limit was reached.
        """
        if params is None:
            params = dict()
        if auto_remove is None:
            auto_remove = mode == 'replica'
        if mode == 'base' and auto_remove:
            raise ValueError('Persistent base agents cannot use auto_remove=True')

        try:

            # command_str = f"python -m shortterm {agent} {mode} {dict_to_cli_params(params)}".strip()  # Replaced by JOM 20/02/2026
            command_str = f"python -m dynreact.shortterm.agents {agent} {mode} {dict_to_cli_params(params)}".strip()

            print(f"Launching with {command_str}")

            container_prefix = os.environ.get('CONTAINER_NAME_PREFIX')

            if self.max_allowed == -1 or (self._count_owned_containers() + 1) <= self.max_allowed:

                environment_variables = {
                  "IS_DOCKER": "true",
                  "KAFKA_TOPIC_PREFIX": KeySearch.search_for_value("KAFKA_TOPIC_PREFIX"),
                  "TOPIC_GEN": KeySearch.search_for_value("TOPIC_GEN"),
                  "TOPIC_CALLBACK": KeySearch.search_for_value("TOPIC_CALLBACK")
                }

                inherited_env_keys = (
                    "DYNREACT_PROFILE",
                    "CONTAINER_NAME_PREFIX",
                    "DOCKER_NETWORK",
                    "IMAGE_NAME",
                    "IMAGE_TAG",
                    "KAFKA_IP",
                    "KAFKA_TOPIC_PREFIX",
                    "LOCAL_REGISTRY",
                    "LOG_FILE_PATH",
                    "PERF_URL",
                    "REST_URL",
                    "SHORT_TERM_PLANNING_PARAMS",
                    "SNAPSHOT_VERSION",
                    "TRANSPORT_TIMES_URL",
                )

                for key in inherited_env_keys:
                    value = os.environ.get(key)
                    if value:
                        environment_variables[key] = value

                replica_variables = params.get("variables") if isinstance(params, dict) else None
                if isinstance(replica_variables, dict):
                    for key in inherited_env_keys:
                        value = replica_variables.get(key)
                        if value not in (None, ""):
                            environment_variables[key] = str(value)

                if envs:
                    environment_variables.update(envs)

                name = f"{container_prefix + '_' if container_prefix else ''}{agent.upper()}_{name}"
                docker_network = os.environ.get("DOCKER_NETWORK")

                matches = self.client.containers.list(all=True, filters={"name": f"^/?{re.escape(name)}$"})
                if self.remote_workers and matches:
                    if len(matches) != 1 or matches[0].labels.get('owner') != self.tag:
                        raise RuntimeError('Remote name collision outside this parent ownership')
                    matches[0].reload()
                    if matches[0].status == 'running':
                        return matches[0]
                    raise RuntimeError('Existing stopped remote replica requires explicit cleanup')
                if matches:
                    print("Container with the same name found, replacing it")
                    self.clean_container(name)

                run_kwargs = dict(
                    image=os.environ.get('DYNREACT_SHORTTERM_IMAGE') or f"{os.environ.get('LOCAL_REGISTRY', '')}{os.environ.get('IMAGE_NAME', 'dynreact-oss-shortterm')}:{os.environ.get('IMAGE_TAG', 'latest')}",
                    name=name,
                    detach=True,
                    auto_remove=auto_remove,
                    command=command_str,
                    environment=environment_variables,
                    volumes={
                        "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "rw"},
                        "/var/log/dynreact-logs": {
                            "bind": "/var/log/dynreact-logs",
                            "mode": "rw",
                        }
                    },
                    labels=self._build_labels(params)
                )

                if self.remote_workers:
                    if mode != 'replica':
                        raise RuntimeError('Worker pools launch replicas only; start parents using deploy_parents.sh')
                    run_kwargs['entrypoint'] = '/usr/local/bin/entrypoint.sh'
                    # Remote source paths belong to the worker, not to this parent.
                    run_kwargs['volumes'] = {
                        os.getenv('DYNREACT_WORKER_LOG_DIR',f'/home/{self.profile}/dynreact-logs'):
                            {'bind':'/var/log/dynreact-logs','mode':'rw'}}
                    run_kwargs['labels']['dynreact.profile'] = self.profile
                if docker_network:
                    run_kwargs["network"] = docker_network

                container = self.client.containers.run(**run_kwargs)
                try:
                    container.reload()
                except docker.errors.NotFound:
                    if not auto_remove:
                        raise
                    print(f"Container '{name}' already auto-removed before inspection; exit status unavailable.")
                    return container
                container_info = {
                    "id": container.id,
                    "status": container.status,
                    "name": container.name,
                }
                container_info.update(_container_state_details(container))
                self.tracked_containers.append(container_info)
                print(f"Container '{container.name if name else container.short_id}' launched successfully!")
                return container
            else:
                print("Unable to provision container, container limit reached!")
        except Exception as e:
            dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
            raise Exception(f"{dt} | ERROR: Error launching container: {e}")

    @staticmethod
    def _reload_if_present(container: Any) -> bool:
        try:
            container.reload()
            return True
        except docker.errors.NotFound:
            return False

    @staticmethod
    def _remove_if_present(container: Any, stop: bool = True, force: bool = False) -> None:
        try:
            if stop:
                container.stop()
            container.remove(force=force)
        except docker.errors.NotFound:
            pass  # Docker can remove an auto-remove child immediately after stop.

    def stop_tracked_containers(self) -> None:
        """
        Stop and remove all containers launched by this instance (using the tag).
        """
        try:
            containers = self.client.containers.list(filters={"label": f"owner={self.tag}"} if self.tag else {})
            if not containers:
                print("No tracked containers found.")
                return

            for container in containers:
                self._remove_if_present(container)
                print(f"Container '{container.name}' stopped and removed.")

            # Clear the internal tracking list
            self.tracked_containers = []
        except Exception as e:
            print(f"Error stopping tracked containers: {e}")

    def clean_containers(self) -> None:
        """
        Stop and remove all containers launched by this instance (using the tag).
        """
        try:
            containers = self.client.containers.list(
                filters={"label": f"owner={self.tag}"} if self.tag else {},
                all=True
            )

            if not containers:
                print("No tracked containers found.")
                return

            for container in containers:
                if not self._reload_if_present(container):
                    continue
                container_info = {
                    "id": container.id,
                    "status": container.status,
                    "name": container.name,
                }
                container_info.update(_container_state_details(container))
                self._remove_if_present(container, stop=container.status == "running", force=True)
                print(f"Container '{container.name}' removed ({_container_status_reason(container_info)}).")

        except Exception as e:
            print(f"Error cleaning containers: {e}")

    def clean_container(self, container_name: str) -> None:
        """
        Stop and remove all containers launched by this instance (using the tag).

        :param container_name: Container name
        :return: The container object.
        """
        try:
            normalized_name = self._normalize_container_name(container_name)
            matched_containers = [
                container for container in self.client.containers.list(all=True)
                if container.name is not None and self._normalize_container_name(container.name) == normalized_name
            ]

            if not matched_containers:
                print("No tracked containers found.")
                return

            for container in matched_containers:
                if not self._reload_if_present(container):
                    continue
                container_info = {
                    "id": container.id,
                    "status": container.status,
                    "name": container.name,
                }
                container_info.update(_container_state_details(container))
                self._remove_if_present(container, stop=container.status == "running", force=True)
                print(f"Container '{container.name}' removed ({_container_status_reason(container_info)}).")

        except Exception as e:
            print(f"Error cleaning containers: {e}")

    def stop_tracked_container(self, container_id: str) -> None:
        """
        Stop and remove one container by container ID.
        """
        try:
            container = self.client.containers.get(container_id)
            if not container:
                print(f"No tracked container with id {container_id} found.")
                return

            self._remove_if_present(container)
            print(f"Container '{container.name}' stopped and removed.")

            # Clear the internal tracking list
            self.tracked_containers = [item for item in self.tracked_containers if item.get('id') != container_id]
        except docker.errors.NotFound:
            self.tracked_containers = [item for item in self.tracked_containers if item.get('id') != container_id]
        except Exception as e:
            print(f"Error stopping tracked container: {e}")

    def list_tracked_containers(self) -> Any:
        """
        List all running containers that belong to this instance.

        :return: The container list id.
        """

        # Reset the count
        self.tracked_containers = []

        containers = self.client.containers.list(filters={"label": f"owner={self.tag}"} if self.tag else {}, all=True)
        if not containers:
            print("No tracked containers found.")
        else:
            print(f"\nTracked Containers for tag '{self.tag}':")
            for container in containers:
                if not self._reload_if_present(container):
                    continue
                container_info = {
                    "id": container.id,
                    "status": container.status,
                    "name": container.name
                }
                container_info.update(_container_state_details(container))
                self.tracked_containers.append(container_info)
                print(
                    f"ID: {container.short_id} | Name: {container.name} | "
                    f"Status: {_container_status_reason(container_info)}"
                )

        return self.tracked_containers

    def reap(self, exited_grace: float | None = None, max_age: float | None = None,
             topic_grace: float | None = None, existing_topics: set[str] | None = None) -> dict[str, int]:
        """Removes the containers of this manager that are no longer useful.

        The rules apply only to containers carrying this manager's ``owner`` label:

        * Exited or dead containers are removed once ``exited_grace`` seconds have
          passed since they finished, which leaves time to read their diagnostics.
        * Running containers older than ``max_age`` seconds are stuck and are removed.
        * Running containers older than ``topic_grace`` seconds whose auction topic is
          not in ``existing_topics`` are removed: their auction was cleaned up and
          nobody will ever send them ``EXIT``. This rule is skipped when
          ``existing_topics`` is None (Kafka not reachable), so an error never kills
          a live auction.

        The method never raises. Every failure is reported and the sweep continues
        with the next container.

        Args:
            exited_grace: Seconds an exited container is kept. Defaults to ``DYNREACT_REAPER_EXITED_GRACE`` or ``REAPER_EXITED_GRACE``.
            max_age: Seconds after which a running container is stuck. Defaults to ``DYNREACT_REAPER_MAX_AGE`` or ``REAPER_MAX_AGE``.
            topic_grace: Minimum age of a running container to require its topic. Defaults to ``DYNREACT_REAPER_TOPIC_GRACE`` or ``REAPER_TOPIC_GRACE``.
            existing_topics: Topics currently present in Kafka, or None when unknown.

        Returns:
            Number of containers removed per rule, with keys ``exited``, ``stuck`` and ``orphan``.
            The names of the removed containers, with the rule applied, stay in ``last_reaped``.
        """
        exited_grace = _env_float("DYNREACT_REAPER_EXITED_GRACE", REAPER_EXITED_GRACE) if exited_grace is None else exited_grace
        max_age = _env_float("DYNREACT_REAPER_MAX_AGE", REAPER_MAX_AGE) if max_age is None else max_age
        topic_grace = _env_float("DYNREACT_REAPER_TOPIC_GRACE", REAPER_TOPIC_GRACE) if topic_grace is None else topic_grace
        removed = {"exited": 0, "stuck": 0, "orphan": 0}
        self.last_reaped = []
        if not self.tag:
            # Without an owner label we cannot tell our containers from anybody else's
            return removed
        now = time.time()
        try:
            containers = self.client.containers.list(all=True, filters={"label": f"owner={self.tag}"})
        except Exception as e:
            print(f"Reaper could not list containers: {e}")
            return removed
        for container in containers:
            try:
                labels = (container.attrs.get("Config", {}) or {}).get("Labels") or container.labels or {}
                created = _parse_docker_time(container.attrs.get("Created")) if isinstance(container.attrs.get("Created"), str) \
                    else container.attrs.get("Created")
                try:
                    created = float(labels.get(LABEL_CREATED, created))
                except (TypeError, ValueError):
                    pass
                age = now - created if created else 0.0
                status = container.status
                if status in ("exited", "dead"):
                    container.reload()
                    finished = _parse_docker_time(_container_state_details(container)["finished_at"])
                    if finished is None or now - finished >= exited_grace:
                        container.remove(force=True)
                        removed["exited"] += 1
                        self.last_reaped.append(f"{container.name} (exited)")
                elif status == "running":
                    topic = labels.get(LABEL_TOPIC)
                    if age > max_age:
                        container.remove(force=True)
                        removed["stuck"] += 1
                        self.last_reaped.append(f"{container.name} (stuck)")
                    elif topic and existing_topics is not None and topic not in existing_topics and age > topic_grace:
                        container.remove(force=True)
                        removed["orphan"] += 1
                        self.last_reaped.append(f"{container.name} (orphan)")
            except Exception as e:
                # The container may have vanished by itself between listing and removing it
                print(f"Reaper skipped container {getattr(container, 'name', '?')}: {e}")
        if any(removed.values()):
            print(f"Reaper removed containers for tag '{self.tag}': {removed}")
        return removed


def dict_to_cli_params(params: Any) -> Any:
    """Dict to cli params.
    
    This function is part of the short-term planning workflow and keeps
    the existing runtime behavior while documenting the public contract.
    
    Args:
        params: Input value for the `params` parameter.
    
    Returns:
        The value produced by the underlying planning, UI, or test helper logic.
    """
    cli_params = []
    for key, value in params.items():
        if isinstance(value, bool):
            if value:  # Include flag only if True
                cli_params.append(f"--{key}")
        elif isinstance(value, list):  # Handle list values
            cli_params.append(f"--{key} {' '.join(map(str, value))}")
        elif isinstance(value, dict):  # Handle dict values
            json_string = json.dumps(value)
            cli_params.append(f"--{key} {shlex.quote(json_string)}")
        else:
            cli_params.append(f"--{key} {value}")
    return " ".join(cli_params)
