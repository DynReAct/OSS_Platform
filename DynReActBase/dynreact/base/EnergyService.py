from bisect import bisect_right
from datetime import datetime, timedelta
from typing import Literal, Sequence, Mapping, TypeAlias, Any

from pydantic import BaseModel, model_validator
from typing_extensions import Self

from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.model import Order, Site, Material, EnergyType


class EnergyServiceMetadata(BaseModel, use_attribute_docstrings=True, frozen=True):
    """Provides metadata about the energy estimation service.

    Attributes:
        id (str): The unique identifier of the service.
        label (str): A human-readable label for the service.
        description (str): A brief description of the service.
        processes (List(str)): supported process steps.
        equipment (List[str]): A list of equipment IDs for which models are available.
        available_models (List[str]): A list of all model keys available for prediction.
    """
    id: str
    label: str
    energy_type: EnergyType
    material_based: bool = False
    description: str|None=None
    attribution: str | None = None
    license_info: str | None = None
    license_details: str | None = None
    processes: Sequence[str]|None=None
    equipment: Sequence[int]|None=None
    "Equipment ids supported. If None, all equipments can be assumed to be supported"
    available_models: Sequence[str]|Mapping[int, Sequence[str]]|None = None
    "List of all available model keys. Either a flat list, or a mapping from equipment ids to lists of model keys."
    relevant_fields: Mapping[str, str]|Mapping[int, Mapping[str, str]]|None=None
    "Important for the HTTP energy service; keys=service attributes, values=DynReAct order attribute names, such as \"material_properties.custom_attribute\"."


class EnergyPrediction(BaseModel, use_attribute_docstrings=True, extra="allow"):
    """Result structure for energy estimation.

    Attributes:
        model_name (str): The name of the model used for the prediction.
        predicted_energy (float): The predicted energy consumption in kWh.
    """
    model: str|None = None   # model_name conflicts with pydantic conventions
    predicted_energy: float
    "The predicted energy consumption (kWh)."
    """
    cost_unit: str = "€"
    predicted_costs: float|None=None
    ""
    predicted_emissions: Mapping[str, float] = {}
    """
    "Emissions, such as \"co2_tons\""
    # TODO uncertainties etc


class EnergyPredictionResultsSuccess(BaseModel, use_attribute_docstrings=True):
    results: Sequence[EnergyPrediction]


class ServiceResultsFailed(BaseModel, use_attribute_docstrings=True):

    reason: int
    "http status code, or 1 for service not available"
    message: str|None=None
    details: dict|str|None=None


# TODO upon dropping Python 3.11 support we can replace ...: TypeAlias = by type ... =
EnergyPredictionResults: TypeAlias = EnergyPredictionResultsSuccess | ServiceResultsFailed


class EnergyService:

    def __init__(self, url: str, site: Site, snapshot_provider: SnapshotProvider):
        self._url = url
        self._site = site
        self._snapshot_provider = snapshot_provider

    def service(self) -> EnergyServiceMetadata:
        raise NotImplementedError

    def status(self) -> int:
        """
        :return: 0: service running, 1: service not available, > 10: custom error codes
        """
        raise NotImplementedError

    def energy_type(self) -> EnergyType:
        return self.service().energy_type

    def energy_consumption(self,
                           order: Order,
                           equipment: int,
                           snapshot: datetime,
                           #start_time: datetime,
                           *args,
                           material: Material | None = None,
                           process_id: int|None=None,
                           model: str|None=None,
                           missing_value_ensemble: Sequence[Order]|None=None,
                           **kwargs) -> EnergyPrediction | ServiceResultsFailed:
        """
        An estimation of the energy required for processing an order at some equipment.
        TODO more input data needed? Start/end time, predecessor, etc?
        Parameters:
            order:
            equipment:
            material: optional material unit
            start_time:
            process_id: the energy may vary depending on the process performed
            model: optional identifier of the estimation model to be performed. Service-specific.

        Returns
            Estimated energy for processing the specified order at the specified equipment
        """
        raise NotImplementedError

    def bulk_energy_consumption(self,
                           orders: Sequence[Order],
                           equipment: int,
                           snapshot: datetime,
                           #start_times: Sequence[datetime],
                           *args,
                           material: Mapping[str, Sequence[Material]]|None = None,
                           process_id: int|None=None,
                           model: str|None=None,
                           missing_value_ensemble: Sequence[Order] | None = None,
                           **kwargs) -> EnergyPredictionResults:

        if material is not None:
            empty = tuple()
            entries = [(o, mat) for o in orders for mat in material.get(o.id, empty)]
        else:
            entries = [(o, None) for o in orders]
        return EnergyPredictionResultsSuccess(results=[self.energy_consumption(order, equipment, snapshot, *args, material=mat, process_id=process_id,
                                        model=model, missing_value_ensemble=missing_value_ensemble, **kwargs) for order, mat in entries])


class EnergyCostServiceMetadata(BaseModel, use_attribute_docstrings=True):
    """Provides metadata about the energy estimation service.

    Attributes:
        id (str): The unique identifier of the service.
        label (str): A human-readable label for the service.
        description (str): A brief description of the service.
    """
    id: str
    label: str
    description: str|None=None


class EnergyCharacteristics(BaseModel, use_attribute_docstrings=True):

    validity: tuple[datetime, datetime]
    costs_per_mwh: float
    co2_per_mwh: float|None=None


class EnergyPriceCurve(BaseModel, use_attribute_docstrings=True):

    entries: Sequence[EnergyCharacteristics]
    "Ordered list of entries for consecutive time interval."
    cost_unit: str = "€"
    # internally used fields below; set in model validator
    start_end: tuple[datetime, datetime]|None
    start_times: tuple[datetime, ...]

    @model_validator(mode="before")
    def validate(self) -> Self:
        if not self.start_end and len(self.entries) > 0:
            self.start_end = (self.entries[0].validity[0], self.entries[-1].validity[1])
        if not self.start_times:
            self.start_times = tuple([e.validity[0] for e in self.entries])
        return self

    def average_price(self, start: datetime, end: datetime, default_price: float|None=None):
        """
        Parameters:
            start:
            end:
            default_price:
        Returns:
             price in
        """
        if not self.start_end or end <= self.start_end[0] or start >= self.start_end[1] or end < start:
            return default_price
        if end <= self.entries[0].validity[1]:
            return self.entries[0].costs_per_mwh
        if start >= self.entries[-1].validity[0]:
            return self.entries[-1].costs_per_mwh
        start_idx = bisect_right(self.start_times, start) - 1
        total_duration: timedelta = timedelta()
        total_value: timedelta = timedelta()
        for entry in self.entries[start_idx:]:
            validity = entry.validity
            if start > validity[0]:
                if end <= validity[1]:
                    return entry.costs_per_mwh
                delta = validity[1] - start
            elif end <= validity[0]:
                break
            else:
                delta = validity[1] - validity[0]
            total_duration += delta
            total_value += entry.costs_per_mwh * delta
        return total_value / total_duration


class EnergyCostService:

    def __init__(self, url: str):
        self._url = url

    def service(self) -> EnergyServiceMetadata:
        raise NotImplementedError

    def energy_type(self) -> EnergyType:
        return self.service().energy_type

    def status(self) -> int:
        """
        :return: 0: service running, 1: service not available, > 10: custom error codes
        """
        raise NotImplementedError

    def energy_costs(self, start: datetime, end: datetime) -> EnergyPriceCurve|ServiceResultsFailed:
        raise NotImplementedError
