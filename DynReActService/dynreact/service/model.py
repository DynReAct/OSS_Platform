from datetime import datetime

from dynreact.base.model import EquipmentStatus
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
