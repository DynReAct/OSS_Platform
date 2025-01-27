from datetime import datetime

from dynreact.base.model import EquipmentStatus, ProductionPlanning, ProductionTargets, ObjectiveFunction
from pydantic import BaseModel, Field, ConfigDict


class EquipmentTransition(BaseModel):

    model_config = ConfigDict(use_attribute_docstrings=True)

    equipment: int
    snapshot_id: datetime
    current_order: str
    "Current order id"
    next_order: str
    "Next order id"
    current_material: str | None = None
    "Current coil id"
    next_material: str | None = None
    "Next coil id"


class EquipmentTransitionStateful(EquipmentTransition):

    equipment_status: EquipmentStatus
    "Optimization status, typically retrieved either from a previous optimization run, or from the ...init function"


class TransitionInfo(BaseModel, use_attribute_docstrings=True):

    status: EquipmentStatus
    costs: ObjectiveFunction


class LotsOptimizationInput(BaseModel):
    model_config = ConfigDict(use_attribute_docstrings=True)

    snapshot: datetime
    "Snapshot id"
    targets: ProductionTargets
    "Production targets"
    orders: list[str]
    "Orders to include in the optimization."
    initial_solution: ProductionPlanning|None = None
    "Starting point for the optimization"
    min_due_date: datetime|None = None,
    "Minimum due date"
    trace_results: bool = False
    "Set to true in order to store all intermediate results"


class LotsOptimizationResults(BaseModel):

    model_config = ConfigDict(use_attribute_docstrings=True)

    snapshot: datetime
    "Snapshot id"
    targets: ProductionTargets
    "Production targets"
    orders: list[str]
    "Orders included in the optimization."

    results: list[ProductionPlanning]
    "Note: if trace_results in the input data was False, this list will contain a single entry. Otherwise all intermediate results"
    objective_function: list[ObjectiveFunction]
    "Values of the objective function for all intermediate results, irrespectively of whether trace_results is set or not"
    done: bool
    "Optimization completed?"

