"""SSH worker fleet used by the OSS and RAS base agents.

Placement uses live active-container counts, not available RAM. A per-profile
worker limit is advisory across independent parents (no distributed reservation).
All endpoints must be reachable before placement: an unknown worker may already
hold a previous attempt, so silently moving a launch would risk duplicate agents.
"""
import os
import re
from urllib.parse import urlsplit
import docker


def worker_endpoints(profile):
    values = os.getenv(f'{profile.upper()}_DOCKER_WORKERS', '')
    endpoints = list(dict.fromkeys(v.strip() for v in values.split(',') if v.strip()))
    for endpoint in endpoints:
        url = urlsplit(endpoint)
        if (url.scheme != 'ssh' or not url.hostname or url.username != profile
                or url.password or url.path not in ('', '/') or url.query or url.fragment):
            raise ValueError(f'{profile.upper()}_DOCKER_WORKERS requires ssh://{profile}@host[:port] endpoints')
    return endpoints


class RemoteDockerPool:
    """Docker containers facade; objects returned by Docker retain their own client."""
    def __init__(self, profile, endpoints):
        self.profile = profile
        self.containers = self
        self.clients = [(endpoint, docker.DockerClient(base_url=endpoint, use_ssh_client=True,
            version=docker.constants.DEFAULT_DOCKER_API_VERSION, timeout=30)) for endpoint in endpoints]
        self.limit = int(os.getenv('DYNREACT_WORKER_LIMIT', '0'))
        if self.limit < 0:
            raise ValueError('DYNREACT_WORKER_LIMIT cannot be negative')
        self.cursor = 0

    def list(self, **kwargs):
        rows = []
        for endpoint, client in self.clients:
            try:
                rows.extend(client.containers.list(**kwargs))
            except Exception as exc:
                raise RuntimeError(f'Cannot inspect worker {endpoint}; placement/cleanup incomplete') from exc
        return rows

    def get(self, container_id):
        found = []
        for endpoint, client in self.clients:
            try:
                found.append(client.containers.get(container_id))
            except docker.errors.NotFound:
                continue
        if not found:
            raise docker.errors.NotFound(f'No fleet container {container_id}')
        if len(found) != 1:
            raise RuntimeError(f'Expected exactly one fleet container for {container_id}, found {len(found)}')
        return found[0]

    def run(self, **kwargs):
        # Reconcile on every worker before creating anything, including after a timeout.
        existing = self.list(all=True, filters={'name': '^/?'+re.escape(kwargs['name'])+'$'})
        if existing:
            if len(existing) != 1 or existing[0].labels.get('owner') != kwargs['labels'].get('owner'):
                raise RuntimeError('Fleet container name collision')
            existing[0].reload()
            if existing[0].status == 'running':
                return existing[0]
            raise RuntimeError('Existing non-running replica requires inspection before relaunch')
        loads = []
        for index, (endpoint, client) in enumerate(self.clients):
            active = client.api.containers(all=True, filters={'label':f'dynreact.profile={self.profile}'})
            count = sum(c.get('State') in ('created','running','restarting','paused') for c in active)
            if not self.limit or count < self.limit:
                loads.append((count, (index-self.cursor) % len(self.clients), index))
        if not loads:
            raise RuntimeError('All workers reached the advisory replica limit; no container was launched')
        _, _, index = min(loads)
        endpoint, client = self.clients[index]
        kwargs['labels'].update({'dynreact.profile':self.profile, 'dynreact.worker':endpoint})
        memory = os.getenv('DYNREACT_REPLICA_MEMORY')
        cpus = os.getenv('DYNREACT_REPLICA_CPUS')
        if memory: kwargs['mem_limit'] = memory
        if cpus:
            cpu_value = float(cpus)
            if not 0 < cpu_value < 1024:
                raise ValueError('DYNREACT_REPLICA_CPUS must be positive and finite')
            kwargs['nano_cpus'] = int(cpu_value*1_000_000_000)
        print(f'Placing {kwargs["name"]} on {endpoint}')
        result = client.containers.run(**kwargs)
        self.cursor = (index+1) % len(self.clients)
        return result
