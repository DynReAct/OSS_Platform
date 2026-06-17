from datetime import datetime
from typing import Sequence

from dynreact.base.model import Model


# Below: general service health and statistics
# =========================================== #


class ServiceHealth(Model):

    status: int
    "0: ok"
    running_since: datetime|None=None


class Metric(Model):
    id: str
    labels: dict[str, str]|None=None


class PrimitiveMetric(Metric):
    value: float|int


class Histogram(Metric):
    data: list[float]
    buckets: list[float]
    include_infinity: bool=True


class ServiceMetrics(Model):
    service_id: str
    metrics: Sequence[Metric]


# Below: batch lot creation monitoring
# =============================================== #

class LotCreationProcessStatistics(Model):
    order_backlog_count: int
    order_backlog_tons: float
    lots_created: int
    orders_assigned: int
    tons_assigned: float
    tons_target: float
    objective_value: float
    "Average objective value in case of aggregated data"
    objective_range: tuple[float, float]|None=None
    "Only relevant for aggregated statistics"
    equipment: Sequence[int]
    missing_material: int
    "A boolean that indicates whether the lot creation was canceled due to an empty order backlog."
    material_insufficient_for_target: int
    "A boolean that indicates whether the order backlog contains enough material to cover the targeted production"
    lots_exceed_planning_horizon: int
    "A boolean that indicates whether existing lots already cover the planning period"
    errors: int
    "A boolean indicating whether an error occurred, or in the case of aggregated statistics, the sum of errors."


class LotsBatchJobStatistics(Model):
    start_time: datetime
    total_invocations: int
    is_active: bool = False
    previous_invocation: datetime | None = None
    previous_snapshot: datetime|None = None
    next_invocation: datetime | None = None
    # TODO option to keep more than one result set
    previous_process_results: dict[str, LotCreationProcessStatistics] | None = None
    overall_process_results: dict[str, LotCreationProcessStatistics]


