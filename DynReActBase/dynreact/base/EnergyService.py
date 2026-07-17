from datetime import datetime
from typing import Literal, Sequence, Mapping, TypeAlias

from pydantic import BaseModel

from dynreact.base.model import Order, Site


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
    description: str|None=None
    processes: Sequence[str]|None=None
    equipment: Sequence[int]|None=None
    "Equipment ids supported. If None, all equipments can be assumed to be supported"
    available_models: Sequence[str]|Mapping[int, Sequence[str]]|None = None
    "List of all available model keys. Either a flat list, or a mapping from equipment ids to lists of model keys."
    relevant_fields: Mapping[str, str]|None=None
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
    # TODO uncertainties etc


class EnergyPredictionResultsSuccess(BaseModel, use_attribute_docstrings=True):
    results: Sequence[EnergyPrediction]


class EnergyPredictionResultsFailed(BaseModel, use_attribute_docstrings=True):

    reason: int
    "http status code, or 1 for service not available"
    message: str|None=None
    details: dict|None=None


# TODO upon dropping Python 3.11 support we can replace ...: TypeAlias = by type ... =
EnergyPredictionResults: TypeAlias = EnergyPredictionResultsSuccess | EnergyPredictionResultsFailed


class EnergyService:

    def __init__(self, url: str, site: Site):
        self._url = url
        self._site = site

    def service(self) -> EnergyServiceMetadata:
        raise NotImplementedError

    def status(self) -> int:
        """
        :return: 0: service running, 1: service not available, > 10: custom error codes
        """
        raise NotImplementedError

    def energy_type(self) -> Literal["electric", "heat"]:
        raise NotImplementedError

    def energy_consumption(self,
                           order: Order,
                           equipment: int,
                           start_time: datetime,
                           *args,
                           process_id: int|None=None,
                           model: str|None=None,
                           **kwargs) -> EnergyPrediction|EnergyPredictionResultsFailed:
        """
        An estimation of the energy required for processing an order at some equipment.
        TODO more input data needed? Start/end time, predecessor, etc?
        Parameters:
            order:
            equipment:
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
                           start_times: Sequence[datetime],
                           *args,
                           process_id: int|None=None,
                           model: str|None=None,
                           **kwargs) -> EnergyPredictionResults:
        return EnergyPredictionResultsSuccess(results=[self.energy_consumption(order, equipment, start_times[idx], *args,
                                                        process_id=process_id, model=model, **kwargs) for idx, order in enumerate(orders)])


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
    cost_unit: str = "€"
    costs_per_kwh: float
    co2_per_kwh: float|None=None


class EnergyPriceCurve(BaseModel, use_attribute_docstrings=True):

    entries: Sequence[EnergyCharacteristics]
    "Ordered list of entries for consecutive time interval."


class EnergyCostService:

    def __init__(self, url: str):
        self._url = url

    def service(self) -> EnergyServiceMetadata:
        raise NotImplementedError

    def energy_type(self) -> Literal["electric", "heat"]:
        raise NotImplementedError

    def energy_costs(self, start: datetime, end: datetime) -> EnergyPriceCurve:
        raise NotImplementedError
