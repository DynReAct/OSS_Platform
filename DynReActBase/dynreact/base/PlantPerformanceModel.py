from datetime import datetime
from typing import TypeAlias

from pydantic import BaseModel, Field

from dynreact.base.model import Order, Material, Site


class PerformanceEstimation(BaseModel, use_attribute_docstrings=True):

    performance: float
    "A value between 0 and 1. Zero indicates inavailability of the plant to process the requested order or coil, One indicates no restriction."

    equipment: int
    order: str
    #material: str | None = None
    reason: str|None = None
    #estimated_duration: datetime|None = None


class PlantPerformanceResultsSuccess(BaseModel, use_attribute_docstrings=True):
    results: list[PerformanceEstimation]


class PlantPerformanceResultsFailed(BaseModel, use_attribute_docstrings=True):

    reason: int
    "http status code, or 1 for service not available"
    message: str|None=None


# TODO upon dropping Python 3.11 support we can replace ...: TypeAlias = by type ... =
PlantPerformanceResults: TypeAlias = PlantPerformanceResultsSuccess | PlantPerformanceResultsFailed


class PlantPerformanceInput(BaseModel, use_attribute_docstrings=True):

    equipment: int
    orders: list[Order]


class PerformanceModelMetadata(BaseModel, use_attribute_docstrings=True):

    id: str
    label: str
    description: str|None = None
    processes: list[str]|None = None
    equipment: list[int]|None = None


class PlantPerformanceModel:

    def id(self) -> str:
        raise Exception("not implemented")

    def label(self, lang: str="en") -> str:
        return self.id()

    def description(self, lang: str="en") -> str|None:
        return None

    def status(self) -> int:
        """
        :return: 0: service running, 1: service not available, > 10: custom error codes
        """
        return 0

    def applicable_processes_and_plants(self) -> tuple[list[str]|None, list[int]|None]:
        """
        :return: a list of process ids and equipment ids. One or both of the results may be None, which should be understood
        as unrestricted.
        """
        return None, None

    #def performance(self, equipment: int, order: Order, coil: Material | None = None) -> PerformanceEstimation:
    #    """
    #    Note: the performance is always evaluated at the query time
    #    :param equipment:
    #    :param order:
    #    :param coil:
    #    :return:
    #    """
    #    return PerformanceEstimation(performance=1, equipment=equipment.id, order=order.id)

    def bulk_performance(self, plant: int, orders: list[Order]) -> PlantPerformanceResults:
        raise Exception("not implemented")

