"""SSH worker fleet used by the OSS and RAS base agents.

Placement uses live active-container counts, not available RAM. A per-profile
worker limit is advisory across independent parents (no distributed reservation).
All endpoints must be reachable before placement: an unknown worker may already
hold a previous attempt, so silently moving a launch would risk duplicate agents.
"""
import os
import re
import time
import threading
from concurrent.futures import ThreadPoolExecutor
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
        self.parallelism = int(os.getenv('DYNREACT_LAUNCHES_PER_WORKER', '2'))
        if self.parallelism < 1:
            raise ValueError('DYNREACT_LAUNCHES_PER_WORKER must be positive')
        self._condition = threading.Condition()
        self._inflight = [0] * len(self.clients)
        self._loads = None
        self._loads_at = 0.0
        self._names = {}

    def list(self, **kwargs):
        def inspect(worker):
            endpoint, client = worker
            try:
                # Sparse avoids an extra inspect request for every matching container.
                return client.containers.list(**kwargs)
            except Exception as exc:
                raise RuntimeError(f'Cannot inspect worker {endpoint}; placement/cleanup incomplete') from exc
        with ThreadPoolExecutor(max_workers=len(self.clients)) as executor:
            return [row for rows in executor.map(inspect, self.clients) for row in rows]

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
        # A repeated CREATE cannot race its own reconciliation within this parent.
        with self._condition:
            lock, users = self._names.get(kwargs['name'], (threading.Lock(), 0))
            self._names[kwargs['name']] = (lock, users + 1)
        started = time.monotonic()
        try:
            with lock:
                return self._run(**kwargs)
        finally:
            with self._condition:
                _, users = self._names[kwargs['name']]
                if users == 1:
                    del self._names[kwargs['name']]
                else:
                    self._names[kwargs['name']] = (lock, users - 1)
            print(f'Launch {kwargs["name"]}: total={time.monotonic()-started:.3f}s')

    def _run(self, **kwargs):
        # Reconcile on every worker before creating anything, including after a timeout.
        existing = self.list(all=True, sparse=True, filters={'name': '^/?'+re.escape(kwargs['name'])+'$'})
        if existing:
            if len(existing) != 1 or existing[0].labels.get('owner') != kwargs['labels'].get('owner'):
                raise RuntimeError('Fleet container name collision')
            existing[0].reload()
            if existing[0].status == 'running':
                return existing[0]
            raise RuntimeError('Existing non-running replica requires inspection before relaunch')
        with self._condition:
            while True:
                # Refresh between batches, never discard outstanding reservations.
                if self._loads is None or (not any(self._inflight) and time.monotonic() - self._loads_at > 2):
                    def count(worker):
                        _, client = worker
                        active = client.api.containers(all=True, filters={'label': f'dynreact.profile={self.profile}'})
                        return sum(c.get('State') in ('created', 'running', 'restarting', 'paused') for c in active)
                    with ThreadPoolExecutor(max_workers=len(self.clients)) as executor:
                        self._loads = list(executor.map(count, self.clients))
                    self._loads_at = time.monotonic()
                eligible = [i for i, load in enumerate(self._loads) if not self.limit or load < self.limit]
                if not eligible:
                    raise RuntimeError('All workers reached the advisory replica limit; no container was launched')
                available = [i for i in eligible if self._inflight[i] < self.parallelism]
                if available:
                    index = min(available, key=lambda i: (self._loads[i], (i-self.cursor) % len(self.clients)))
                    self._loads[index] += 1
                    self._inflight[index] += 1
                    self.cursor = (index+1) % len(self.clients)
                    break
                self._condition.wait()
        endpoint, client = self.clients[index]
        try:
            return self._launch_on_worker(index, endpoint, client, kwargs)
        finally:
            with self._condition:
                self._inflight[index] -= 1
                self._condition.notify_all()

    def _launch_on_worker(self, index, endpoint, client, kwargs):
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
        started = time.monotonic()
        try:
            return client.containers.run(**kwargs)
        finally:
            # Retain the reservation even after an ambiguous timeout; a later live
            # refresh reconciles it. No automatic retry on a different worker.
            print(f'Docker start {kwargs["name"]} on {endpoint}: {time.monotonic()-started:.3f}s')
