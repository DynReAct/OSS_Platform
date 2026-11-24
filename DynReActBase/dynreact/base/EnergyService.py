from bisect import bisect_right
from datetime import datetime, timedelta
from typing import Literal, Sequence, Mapping, TypeAlias, Any

import numpy as np
from pydantic import BaseModel, model_validator
from typing_extensions import Self

from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.model import Order, Site, Material, EnergyType, EquipmentStatus, ObjectiveFunction, \
    ProductionPlanning, Snapshot


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
        is_dict = isinstance(self, dict)
        start_end = self.get("start_end") if is_dict else self.start_end
        entries = self.get("entries") if is_dict else self.entries
        start_times = self.get("start_times") if is_dict else self.start_times
        if not start_end and len(entries) > 0:
            start_end = (entries[0].validity[0], entries[-1].validity[1])
        if not start_times:
            start_times = tuple([e.validity[0] for e in entries])
        if is_dict:
            self["start_end"] = start_end
            self["start_times"] = start_times
        else:
            self.start_end = start_end
            self.start_times = start_times
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


class EnergyUtils:

    @staticmethod
    def evaluate_process_energy_costs(planning: ProductionPlanning, objective: ObjectiveFunction, snapshot: Snapshot,
                                        energy_predictions: Mapping[EnergyType, Mapping[int, Mapping[str, EnergyPrediction]]] | None,
                                        energy_prices: Mapping[EnergyType, EnergyPriceCurve] | None,
                                        default_energy_price: Mapping[EnergyType, float],
                                        energy_costs_factor: float | None
                                        ) -> tuple[ProductionPlanning, ObjectiveFunction]:
        """
        Assumptions:
            * planning.lots is set, and lot times are provided where possible
        TODO need exact order times instead of lot times only
        Parameters:
            planning:
            objective:
            snapshot:
            energy_predictions:
            energy_prices:
            energy_costs_factor:
            default_energy_price: in €/MWh (or other currency unit/MWh)
        Returns:
             the modified planning and objective objects
        """
        if not planning.lots:
            raise ValueError("Lots not set in planning object")
        if not energy_predictions:
            return planning, objective
        _empty = tuple()
        unassigned_orders: list[str] = []
        for eq, status in planning.equipment_status.items():
            # energy costs have been evaluated already for this equipment => common case in mtp solver, when the equipment is not affected by a swap
            if status.energy_costs is not None:
                if objective.energy_costs is None:
                    objective.energy_costs = {}
                for e_type, costs in status.energy_costs:
                    objective.energy_costs[e_type] = objective.energy_costs.get(e_type, 0.) + costs
                continue
            eq_lots = planning.lots.get(eq, _empty)
            for lot in eq_lots:
                if lot.start_time is None or lot.end_time is None or lot.weight is None:
                    unassigned_orders.extend(lot.orders)
                    continue
                start = lot.start_time
                duration = lot.end_time - start
                order_times = []  # TODO use exact order times instead, if known
                for order in lot.orders:
                    end = start + snapshot.get_order(order, do_raise=True).actual_weight/lot.weight * duration
                    order_times.append((start, end))
                    start = end
                eq_energy_predictions = {et: pred[eq] for et, pred in energy_predictions.items() if eq in pred and len(pred[eq]) > 0}
                if len(eq_energy_predictions) == 0:
                    eq_energy_predictions = None
                EnergyUtils.evaluate_equipment_energy_costs(status, objective, lot.orders, order_times,
                                                    eq_energy_predictions, energy_prices, energy_costs_factor, default_energy_price)
        unassigned_orders.extend([ass.order for ass in planning.order_assignments.values() if ass.equipment < 0])
        if len(unassigned_orders) > 0:
            for e_type, predictions in energy_predictions.items():
                unassigned_energy = 0.
                for order in unassigned_orders:
                    energies = [dct[order].predicted_energy for dct in predictions.values() if order in dct]
                    if len(energies) == 0:
                        continue
                    mean_energy = np.mean(energies)
                    unassigned_energy += mean_energy
                if unassigned_energy > 0:
                    # TODO store unassigned energy in planning object! Cannot allocate to equipment status
                    if e_type in default_energy_price:
                        default_price = default_energy_price[e_type]
                        costs = default_price * unassigned_energy / 1e3
                        # TODO store unassigned energy costs in planning object too
                        obj = costs * energy_costs_factor
                        objective.energy_costs[e_type] = objective.energy_costs.get(e_type, 0.) + obj
        return planning, objective

    @staticmethod
    def evaluate_equipment_energy_costs(status: EquipmentStatus, objective: ObjectiveFunction|None,
                              orders: Sequence[str], order_times: Sequence[tuple[datetime, datetime]|None],
                              energy_predictions: Mapping[EnergyType, Mapping[str, EnergyPrediction]] | None,
                              energy_prices: Mapping[EnergyType, EnergyPriceCurve] | None,
                              default_energy_price: Mapping[EnergyType, float], energy_costs_factor: float | None,
                              ) -> tuple[EquipmentStatus, ObjectiveFunction|None]:
        """
        Modifies the status and objective objects and returns them
        """
        if not energy_predictions:
            return status, objective
        energy_usage = {}
        energy_costs = {}
        energy_costs_obj = {} if objective is not None else None
        for order, o_times in zip(orders, order_times):
            for e_type, predictions in energy_predictions.items():
                pred: EnergyPrediction | None = predictions.get(order)
                if pred is not None:
                    energy_usage[e_type] = energy_usage.get(e_type, 0.) + pred.predicted_energy
                    if energy_prices and e_type in energy_prices:
                        # determine cost factor for the considered time interval!
                        avg_price = energy_prices[e_type].average_price(o_times[0], o_times[1]) if o_times is not None else None
                        if avg_price is None:
                            avg_price = default_energy_price.get(e_type)
                        if avg_price is not None:
                            energy_costs[e_type] = energy_costs.get(e_type, 0.) + pred.predicted_energy * avg_price
                            if energy_costs_factor and energy_costs_obj is not None:
                                energy_costs_obj[e_type] = energy_costs_obj.get(e_type, 0) + pred.predicted_energy * energy_costs_factor
        if len(energy_usage) > 0:
            status.energy_usage = energy_usage
        if len(energy_costs) > 0:
            status.energy_costs = energy_costs
        if energy_costs_obj is not None and len(energy_costs_obj) > 0:
            objective.energy_costs = energy_costs_obj
            sum_obj = sum(energy_costs_obj.values())
            objective.total_value += sum_obj
            objective.additive_costs += sum_obj
        return status, objective

    # TODO energy costs for non-scheduled orders
    @staticmethod
    def update_energy_costs(status: EquipmentStatus, objective: ObjectiveFunction,
                            new_status: EquipmentStatus, new_objective: ObjectiveFunction,
                            start: datetime, end: datetime,
                            energy_predictions: Mapping[EnergyType, Mapping[str, EnergyPrediction]] | None,
                            energy_prices: Mapping[EnergyType, EnergyPriceCurve] | None,
                            default_energy_price: Mapping[EnergyType, float],
                            energy_costs_factor: float|None) -> tuple[EquipmentStatus, ObjectiveFunction]:
        """
        Modifies the passed new_status and new_objective objects in place and returns them
        Parameters:
            status:
            objective:
            energy_predictions: prediction by order id

        Return:

        """
        if energy_predictions is None or len(energy_predictions) == 0 or status.energy_usage is None:
            return new_status, new_objective
        new_status.energy_usage = dict(status.energy_usage)
        new_status.energy_costs = dict(status.energy_costs) if status.energy_costs is not None else None
        # old_obj = status[1]
        energy_usage = new_status.energy_usage
        energy_costs = new_status.energy_costs
        energy_usage_obj = dict(objective.energy_usage) if objective.energy_usage is not None else None
        energy_costs_obj = dict(objective.energy_costs) if objective.energy_costs is not None else None
        new_objective.energy_usage = energy_usage_obj
        new_objective.energy_costs = energy_costs_obj
        for e_type, predictions in energy_predictions.items():
            pred: EnergyPrediction | None = predictions.get(new_status.current_order)
            if pred is not None:  # TODO what if it is? Option to use a default?
                energy_usage[e_type] = energy_usage.get(e_type, 0.) + pred.predicted_energy
                # if energy_usage_obj:  # ?
                #    energy_usage_obj[e_type] = energy_usage_obj.get(e_type, 0.) + pred.predicted_energy * [TODO factor]
                if energy_prices and e_type in energy_prices and energy_costs:
                    # determine cost factor for the considered time interval
                    # TODO handle None case, respectively provide a reasonable default
                    avg_price = energy_prices[e_type].average_price(start, end)
                    if avg_price is not None:
                        e_costs = avg_price * pred.predicted_energy / 1e3
                        energy_costs[e_type] = energy_costs.get(e_type, 0.) + e_costs
                        if energy_costs_obj:
                            obj = e_costs * energy_costs_factor
                            energy_costs_obj[e_type] = energy_costs_obj.get(e_type, 0.) + obj
                            new_objective.total_value += obj
                            new_objective.additive_costs += obj
        return new_status, new_objective