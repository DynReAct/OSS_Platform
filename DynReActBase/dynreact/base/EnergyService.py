from datetime import datetime
from typing import Literal, Sequence, Mapping

from pydantic import BaseModel

from dynreact.base.model import Order, Site


class EnergyServiceMetadata(BaseModel, use_attribute_docstrings=True):
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


class EnergyPrediction(BaseModel, use_attribute_docstrings=True):
    """Result structure for energy estimation.

    Attributes:
        model_name (str): The name of the model used for the prediction.
        predicted_energy (float): The predicted energy consumption in kWh.
    """
    model: str|None = None   # model_name conflicts with pydantic conventions
    predicted_energy: float
    "The predicted energy consumption (kWh)."


class EnergyService:

    def __init__(self, url: str, site: Site):
        self._url = url
        self._site = site

    def service(self) -> EnergyServiceMetadata:
        raise NotImplementedError

    def energy_type(self) -> Literal["electric", "heat"]:
        raise NotImplementedError

    def energy_consumption(self,
                           order: Order,
                           equipment: int,
                           *args,
                           process_id: int|None=None,
                           model: str|None=None,
                           **kwargs) -> EnergyPrediction:
        """
        An estimation of the energy required for processing an order at some equipment.
        TODO more input data needed? Start/end time, predecessor, etc?
        Parameters:
            order:
            equipment:
            process_id: the energy may vary depending on the process performed
            model: optional identifier of the estimation model to be performed. Service-specific.

        Returns
            Estimated energy for processing the specified order at the specified equipment
        """
        raise NotImplementedError


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
