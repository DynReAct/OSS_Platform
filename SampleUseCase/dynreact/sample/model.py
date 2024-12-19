from typing import Literal

from pydantic import BaseModel


class SampleMaterial(BaseModel, use_attribute_docstrings=True):
    """
    A simple material class
    """

    width: float
    "The coil width in mm"
    thickness_initial: float
    "The coil thickness in mm before cold rolling"
    thickness_final: float
    "The coil thickness in mm after cold rolling"
    finishing_type: Literal["ftype1", "ftype2"]
    """
    Some material property with two possible values; in our example the value of this property will determine
    which finishing lines can process the coil.
    """
