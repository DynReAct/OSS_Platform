from datetime import datetime

import numpy as np
from pydantic import BaseModel, Field, BeforeValidator, PlainSerializer
from typing import Annotated
import ast

from dynreact.base.model import Site, LongTermTargets, EquipmentAvailability


# cf https://www.flowphysics.com/2024/02/12/numpy-arrays-in-pydantic.html
def nd_array_before_validator(x):
    # custom before validation logic
    if isinstance(x, str):
        x_list = ast.literal_eval(x)
        x = np.array(x_list)
    if isinstance(x, list):
        x = np.array(x)
    return x


def nd_array_serializer(x):
    # custom serialization logic
    return x.tolist()
    # return np.array2string(x,separator=',', threshold=sys.maxsize)


NumPyArray = Annotated[np.ndarray,
    BeforeValidator(nd_array_before_validator),
    PlainSerializer(nd_array_serializer, return_type=list),
]


class SerializableResult(BaseModel, frozen=True, use_attribute_docstrings=True, arbitrary_types_allowed=True):
    site: Site
    structure: LongTermTargets
    shifts: list[tuple[datetime, datetime]]
    availabilities:  dict[int, EquipmentAvailability]
    storage_levels: dict[str, NumPyArray]
    storages_to_equipment: dict[str, dict[int, NumPyArray]]
    equipment_to_storages: dict[int, dict[str, NumPyArray]]
    frozen_horizons: dict[int, datetime] | None = None


