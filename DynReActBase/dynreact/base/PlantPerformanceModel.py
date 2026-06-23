from typing import TypeAlias, Sequence

from pydantic import BaseModel, Field

from dynreact.base.model import Order


class PerformanceEstimation(BaseModel, use_attribute_docstrings=True):
    """
    An order-dependent performance estimation of the equipment
    """

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
    details: dict|None=None


# TODO upon dropping Python 3.11 support we can replace ...: TypeAlias = by type ... =
PlantPerformanceResults: TypeAlias = PlantPerformanceResultsSuccess | PlantPerformanceResultsFailed


class PlantPerformanceInput(BaseModel, use_attribute_docstrings=True):

    equipment: int
    orders: Sequence[Order]


class PerformanceModelMetadata(BaseModel, use_attribute_docstrings=True):

    id: str
    label: str
    description: str|None = None
    processes: Sequence[str]|None = None
    equipment: Sequence[int]|None = None


class EquipmentStatusEstimation(BaseModel, use_attribute_docstrings=True):
    """
    A global, i.e. order-independent, performance estimation of the equipment.
    """

    equipment: int
    active: bool
    "True if equipment is operating at all, false if not"
    capacity: float|None = None
    """
        A value in the range 0-1, indicative of the performance status of the equipment. 1 = operating at full capacity, 0 = not operating. 
        The meaning of a value between 0 and 1 is model-specific, but it might indicate for instance that the equipment is currently capable 
        of processing certain types of orders only.
    """
    status_description: str|None = None
    "E.g. a reason for non-availability"


EquipmentStatusResults: TypeAlias = PlantPerformanceResultsFailed|dict[int, EquipmentStatusEstimation]


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

    def applicable_processes_and_plants(self) -> tuple[Sequence[str]|None, Sequence[int]|None]:
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

    def bulk_performance(self, plant: int, orders: Sequence[Order]) -> PlantPerformanceResults:
        """Performance of the model for specific orders."""
        raise Exception("not implemented")

    def equipment_status(self, plant: int) -> EquipmentStatusEstimation:
        """Overall equipment status"""
        return self.bulk_equipment_status((plant, ))[plant]

    def bulk_equipment_status(self, plant: Sequence[int]) -> dict[int, EquipmentStatusEstimation]:
        """Overall equipment status"""
        raise Exception("not implemented")
