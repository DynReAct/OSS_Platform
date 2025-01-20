from datetime import datetime

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


class PlantPerformanceInput(BaseModel, use_attribute_docstrings=True):

    equipment: int
    orders: list[Order]


class PlantPerformanceModel:

    def __init__(self, url: str, site: Site):
        self._url = url
        self._site = site

    def id(self) -> str:
        raise Exception("not implemented")

    def label(self, lang: str="en") -> str:
        return self.id()

    def description(self, lang: str="en") -> str|None:
        return None

    def applicable_processes_and_plants(self) -> tuple[list[str], list[int]|None]:
        """
        :return: a list of process ids, and optionally of plant ids. If the returned plant ids are None, then
        all plants belonging to the returned processes are covered.
        """
        return [p.name_short for p in self._site.processes], None

    def performance(self, equipment: int, order: Order, coil: Material | None = None) -> PerformanceEstimation:
        """
        Note: the performance is always evaluated at the query time
        :param equipment:
        :param order:
        :param coil:
        :return:
        """
        return PerformanceEstimation(performance=1, equipment=equipment.id, order=order.id)

    def bulk_performance(self, plant: int, orders: list[Order] #, coils: list[Material] | None = None
                        ) -> list[PerformanceEstimation]:
        results = None
        #if coils is not None:
        #    order_for_coil = [next(o for o in orders if o.id == coil.order) for idx, coil in enumerate(coils)]
        #    results = (self.performance(plant, order_for_coil[idx], coil=coil) for idx, coil in enumerate(coils))
        #else:
        results = (self.performance(plant, order) for order in orders)
        return [r for r in results if r.performance != 1]

