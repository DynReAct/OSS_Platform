import json
import os
import shlex
import docker
from datetime import datetime

from dynreact.shortterm.common import KeySearch


class DockerManager:
    def __init__(self, tag="default_tag", max_allowed = -1):
        """
        Initialize Docker client and set a tag to track owned containers.

        :param tag: Unique tag to identify containers launched by this instance.
        """
        self.client = docker.from_env()
        self.tag = tag
        self.max_allowed = max_allowed
        self.tracked_containers = []

    def launch_container(self, name:str, agent:str, mode:str, params:dict, envs: dict = None, auto_remove=False):
        """
        Launch a new Docker container and tag it with the instance's unique identifier.

        :param name: Optional name for the container.
        :param agent: Name of the agent (log, equipment, material9.
        :param mode: Is the agent running a replica or the manager.
        :param params: Dictionary of python params.
        :param envs: Dictionary of environment variables.
        :param auto_remove: Remove container after execution
        :return: The container object.
        """
        if params is None:
            params = dict()

        try:

            # Get updated list of containers before launching
            all_containers = self.list_tracked_containers()

            # command_str = f"python -m shortterm {agent} {mode} {dict_to_cli_params(params)}".strip()  # Replaced by JOM 20/02/2026
            command_str = f"python -m dynreact.shortterm.agents {agent} {mode} {dict_to_cli_params(params)}".strip()

            print(f"Launching with {command_str}")

            container_prefix = os.environ.get('CONTAINER_NAME_PREFIX', False)

            if self.max_allowed == -1 or (len(self.tracked_containers) + 1) <= self.max_allowed:

                environment_variables = {
                  "IS_DOCKER": "true",
                  "TOPIC_GEN": KeySearch.search_for_value("TOPIC_GEN"),
                  "TOPIC_CALLBACK": KeySearch.search_for_value("TOPIC_CALLBACK")
                }

                if envs:
                    environment_variables.update(envs)

                name = f"{container_prefix + '_' if container_prefix else ''}{agent.upper()}_{name}"

                if any((d['name'] == name and d['status'] == "exited") for d in all_containers):
                    print("Container with the same name found, auto removing")
                    self.clean_container(name)

                container = self.client.containers.run(
                    image=f"{os.environ.get("LOCAL_REGISTRY", "")}dynreact-shortterm:{os.environ.get("IMAGE_TAG", "latest")}",
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
                    labels={"owner": self.tag} if self.tag else []  # Use a label to track ownership
                )
                self.tracked_containers.append({
                    "id": container.id,
                    "status": container.status,
                })
                print(f"Container '{container.name if name else container.short_id}' launched successfully!")
                return container
            else:
                print("Unable to provision container, container limit reached!")
        except Exception as e:
            dt = datetime.now().strftime("%Y-%m-%d %H:%M:%S %Z%z")
            raise Exception(f"{dt} | ERROR: Error launching container: {e}")

    def stop_tracked_containers(self):
        """
        Stop and remove all containers launched by this instance (using the tag).
        """
        try:
            containers = self.client.containers.list(filters={"label": f"owner={self.tag}"} if self.tag else {})
            if not containers:
                print("No tracked containers found.")
                return

            for container in containers:
                container.stop()
                container.remove()
                print(f"Container '{container.name}' stopped and removed.")

            # Clear the internal tracking list
            self.tracked_containers = []
        except Exception as e:
            print(f"Error stopping tracked containers: {e}")

    def clean_containers(self):
        """
        Stop and remove all containers launched by this instance (using the tag).
        """
        try:
            result  = self.client.containers.prune(filters={"label": f"owner={self.tag}"} if self.tag else {})
            deleted_containers = result.get("ContainersDeleted", [])

            if not deleted_containers:
                print("No tracked containers found.")
                return

            for container_id in deleted_containers:
                print(f"Container '{container_id}' removed.")

        except Exception as e:
            print(f"Error cleaning containers: {e}")

    def clean_container(self, container_name: str):
        """
        Stop and remove all containers launched by this instance (using the tag).

        :param container_name: Container name
        :return: The container object.
        """
        try:
            result  = self.client.containers.prune(filters={"name": container_name})
            deleted_containers = result.get("ContainersDeleted", [])

            if not deleted_containers:
                print("No tracked containers found.")
                return

            for container_name in deleted_containers:
                print(f"Container '{container_name}' removed.")

        except Exception as e:
            print(f"Error cleaning containers: {e}")

    def stop_tracked_container(self, container_id: str):
        """
        Stop and remove one container by container ID.
        """
        try:
            container = self.client.containers.get(container_id)
            if not container:
                print(f"No tracked container with id {container_id} found.")
                return

            container.stop()
            container.remove()
            print(f"Container '{container.name}' stopped and removed.")

            # Clear the internal tracking list
            self.tracked_containers = [item for item in self.tracked_containers if item.get('id') != container_id]
        except Exception as e:
            print(f"Error stopping tracked container: {e}")

    def list_tracked_containers(self):
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
                container.reload()
                self.tracked_containers.append({
                    "id": container.id,
                    "status": container.status,
                    "name": container.name
                })
                print(f"ID: {container.short_id} | Name: {container.name} | Status: {container.status}")

        return self.tracked_containers

def dict_to_cli_params(params):
    cli_params = []
    for key, value in params.items():
        if value is None:
            continue #TODO: reevaluate need for this optional.

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
