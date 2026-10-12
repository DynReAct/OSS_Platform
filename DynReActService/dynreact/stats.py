from __future__ import annotations

import logging
import threading
from typing import Mapping

import pandas as pd

from dynreact.base.monitoring import MetricsPersistence, ServiceMetrics, ServiceHealth, PrimitiveMetric, Histogram
from dynreact.state import DynReActSrvState


class MetricsPersistenceJob:

    def __init__(self, interval: str, persistence: MetricsPersistence, state: DynReActSrvState):
        self._state = state
        self._persistence = persistence
        self._interval = pd.Timedelta(interval).to_pytimedelta()
        self._stopped = threading.Event()
        self._thread = threading.Thread(name="dynreact.stats.persistence", target=self.run)
        self._previous_metrics: dict[str, ServiceMetrics] = {}
        self._previous_health: dict[str, ServiceHealth] = {}
        self._thread.daemon = True
        self._thread.start()

    def run(self):
        logging.getLogger(__name__).info(f"Metrics persistence started with interval {self._interval}")
        while not self._stopped.is_set():
            try:
                self._process()
            except:
                logging.getLogger(__name__).exception("Failed to store stats")
            self._stopped.wait(self._interval.total_seconds())
        logging.getLogger(__name__).info(f"Metrics persistence stopped")

    def _changed(self, metrics: Mapping[str, ServiceMetrics], health: Mapping[str, ServiceHealth]) -> bool:
        p_metrics = self._previous_metrics
        p_health = self._previous_health
        if len(metrics) != len(p_metrics) or len(health) != len(p_health):
            return True
        if any(k not in p_metrics for k in metrics.keys()) or any(k not in p_health for k in health.keys()):
            return True
        for m, v in metrics.items():
            new_m = v.metrics
            old_m = p_metrics[m].metrics
            if len(new_m) != len(old_m):
                return True
            for new_metric, old_metric in zip(new_m, old_m):
                if new_metric.type != old_metric.type or new_metric.id != old_metric.id:
                    return True
                is_primitive = isinstance(new_metric, PrimitiveMetric)
                if is_primitive:
                    if new_metric.value != old_metric.value:
                        return True
                elif isinstance(new_metric, Histogram):
                    old_values = old_metric.data
                    new_values = new_metric.data
                    if len(old_values) != len(new_values) or any(v != w for v, w in zip(old_values, new_values)) or any(b1 != b2 for b1, b2 in zip(old_metric.buckets, new_metric.buckets)):
                        return True
        for m, new_health in health.items():
            old_health = p_health[m]
            if old_health.status != new_health.status or old_health.running_since != new_health.running_since or old_health.reason != new_health.reason:
                return True
        return False


    def _process(self):
        metrics = self._state.metrics()
        health = self._state.services_health()
        if self._changed(metrics, health):
            self._persistence.store(metrics, health)
            self._previous_metrics = metrics
            self._previous_health = health
        logging.getLogger(__name__).debug(f"Metrics persisted")
