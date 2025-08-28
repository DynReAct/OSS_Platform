from datetime import datetime
from typing import Any

from dynreact.base.model import ProductionTargets, Snapshot, ProductionPlanning, ObjectiveFunction, Lot, Model


class MidTermScenario(Model):

    id: str
    "Unique scenario id"
    config: str
    "Id of the config provider"
    costs: str
    "Id of the cost provider"
    #snapshot_provider: str
    "Id of the snapshot provider"
    snapshot: Snapshot
    targets: ProductionTargets
    backlog: list[str]
    "Order ids"
    solution: ProductionPlanning|None = None
    "Optional reference solution"
    objective: ObjectiveFunction|None = None
    "Optional reference objective function value"
    parameters: dict[str, Any]|None=None
    "Solution parameters"
    iterations: int|None = None
    "Number of iterations used for generating the reference solution"


class MidTermBenchmark(Model):
    """KPIs and result for a mid-term planning optimization"""

    scenario: str
    "Reference to scenario id"
    iterations: int
    child_processes: int
    "< 0 means unknown"
    cpu_time: float
    "In seconds"
    wall_time: float
    "In seconds"
    objective: ObjectiveFunction
    lots: dict[int, list[Lot]]
    "Keys: equipment ids"
    timestamp: datetime

    optimizer_id: str
    "Default: 'tabu_search'"
    optimization_parameters: dict[str, Any]|None = None
    "json dump of MidTermPlanning/dynreact/lotcreation/TabuParams, or the respective parameters of the optimizer used"
