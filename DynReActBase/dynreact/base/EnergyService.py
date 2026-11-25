from bisect import bisect_right
from datetime import datetime, timedelta
from typing import Literal, Sequence, Mapping, TypeAlias, Any

import numpy as np
from pydantic import BaseModel, model_validator
from typing_extensions import Self

from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.model import Order, Site, Material, EnergyType, EquipmentStatus, ObjectiveFunction, \
    ProductionPlanning, Snapshot
from dynreact.base.model_timeseries import MemoryTimeseries, Timeseries


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


class EnergyCostService:

    def __init__(self, url: str):
        self._url = url

    def service(self) -> EnergyServiceMetadata:
        raise NotImplementedError

    def energy_type(self) -> EnergyType:
        return self.service().energy_type

    def unit(self) -> str:
        return "€/MWh"

    def status(self) -> int:
        """
        :return: 0: service running, 1: service not available, > 10: custom error codes
        """
        raise NotImplementedError

    def energy_costs(self, start: datetime, end: datetime) -> Timeseries|ServiceResultsFailed:
        raise NotImplementedError


class EnergyUtils:

    @staticmethod
    def evaluate_process_energy_costs(planning: ProductionPlanning, objective: ObjectiveFunction, snapshot: Snapshot,
                                        energy_predictions: Mapping[EnergyType, Mapping[int, Mapping[str, EnergyPrediction]]] | None,
                                        energy_prices: Mapping[EnergyType, Timeseries] | None,
                                        default_energy_price: Mapping[EnergyType, float],
                                        energy_costs_factor: float | None,
                                        order_times: Mapping[str, tuple[datetime, datetime]]|None = None
                                        ) -> tuple[ProductionPlanning, ObjectiveFunction]:
        """
        Assumptions:
            * planning.lots is set, and lot times are provided where possible
        Parameters:
            planning:
            objective:
            snapshot:
            energy_predictions:
            energy_prices:
            energy_costs_factor:
            default_energy_price: in €/MWh (or other currency unit/MWh)
            order_times: optional, but recommended. If not set, times will be deduced from ?
        Returns:
             the modified planning and objective objects
        """
        if planning.lots is None:
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
                for e_type, costs in status.energy_costs.items():
                    objective.energy_costs[e_type] = objective.energy_costs.get(e_type, 0.) + costs * energy_costs_factor
                continue
            eq_lots = planning.lots.get(eq, _empty)
            for lot in eq_lots:
                lot_order_times = order_times
                if not lot_order_times:
                    if lot.start_time is None or lot.end_time is None or lot.weight is None:
                        unassigned_orders.extend(lot.orders)
                        continue
                    start = lot.start_time
                    duration = lot.end_time - start
                    lot_order_times = {}
                    for order in lot.orders:
                        end = start + snapshot.get_order(order, do_raise=True).actual_weight/lot.weight * duration
                        lot_order_times[order] = ((start, end))
                        start = end
                else:
                    unassigned_orders.extend([o for o in lot.orders if o not in order_times])
                eq_energy_predictions = {et: pred[eq] for et, pred in energy_predictions.items() if eq in pred and len(pred[eq]) > 0}
                if len(eq_energy_predictions) == 0:
                    eq_energy_predictions = None
                EnergyUtils.evaluate_equipment_energy_costs(status, objective, lot.orders, lot_order_times,
                                                    eq_energy_predictions, energy_prices, default_energy_price, energy_costs_factor)
        unassigned_orders.extend([ass.order for ass in planning.order_assignments.values() if ass.equipment < 0])
        planning.energy_usage = {}
        planning.energy_usage_unassigned = {}
        if energy_prices is not None:
            planning.energy_costs = {}
            planning.energy_costs_unassigned = {}
        for status in planning.equipment_status.values():
            if status.energy_usage is not None:
                for e_type, usage in status.energy_usage.items():
                    planning.energy_usage[e_type] = planning.energy_usage.get(e_type, 0.) + usage
            if status.energy_costs is not None:
                for e_type, costs in status.energy_costs.items():
                    planning.energy_costs[e_type] = planning.energy_costs.get(e_type, 0.) + costs
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
                    planning.energy_usage[e_type] = planning.energy_usage.get(e_type, 0.) + unassigned_energy
                    planning.energy_usage_unassigned[e_type] = planning.energy_usage_unassigned.get(e_type, 0.) + unassigned_energy
                    if e_type in default_energy_price:
                        default_price = default_energy_price[e_type]
                        costs = default_price * unassigned_energy / 1e3
                        if planning.energy_costs is not None:
                            planning.energy_costs[e_type] = planning.energy_costs.get(e_type, 0.) + costs
                            planning.energy_costs_unassigned[e_type] = planning.energy_costs_unassigned.get(e_type, 0.) + costs
                        obj = costs * energy_costs_factor
                        if objective.energy_costs is None:
                            objective.energy_costs = {}
                        objective.energy_costs[e_type] = objective.energy_costs.get(e_type, 0.) + obj
                        objective.total_value += obj
        return planning, objective

    @staticmethod
    def evaluate_equipment_energy_costs(status: EquipmentStatus, objective: ObjectiveFunction|None,
                              orders: Sequence[str], order_times: Mapping[str, tuple[datetime, datetime]],
                              energy_predictions: Mapping[EnergyType, Mapping[str, EnergyPrediction]] | None,
                              energy_prices: Mapping[EnergyType, Timeseries] | None,
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
        for order in orders:
            o_times = order_times.get(order)
            for e_type, predictions in energy_predictions.items():
                pred: EnergyPrediction | None = predictions.get(order)
                if pred is not None:
                    energy_usage[e_type] = energy_usage.get(e_type, 0.) + pred.predicted_energy
                    if energy_prices and e_type in energy_prices:
                        # determine cost factor for the considered time interval!
                        avg_price = energy_prices[e_type].avg(start=o_times[0], end=o_times[1])[0] if o_times is not None else None
                        if avg_price is None:
                            avg_price = default_energy_price.get(e_type)
                        if avg_price is not None:
                            costs = pred.predicted_energy * avg_price
                            energy_costs[e_type] = energy_costs.get(e_type, 0.) + costs
                            if energy_costs_factor and energy_costs_obj is not None:
                                energy_costs_obj[e_type] = energy_costs_obj.get(e_type, 0) + costs * energy_costs_factor
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

    @staticmethod
    def update_energy_costs(status: EquipmentStatus, objective: ObjectiveFunction,
                            new_status: EquipmentStatus, new_objective: ObjectiveFunction,
                            start: datetime, end: datetime,
                            energy_predictions: Mapping[EnergyType, Mapping[str, EnergyPrediction]] | None,
                            energy_prices: Mapping[EnergyType, Timeseries] | None,
                            default_energy_price: Mapping[EnergyType, float],
                            energy_costs_factor: float|None) -> tuple[EquipmentStatus, ObjectiveFunction]:
        """
        Modifies the passed new_status and new_objective objects in place and returns them.
        Note: this does not apply a penalty for unassigned orders, and this behaviour is assumed by the call from
        another method above
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
        if energy_usage_obj is not None:
            sum_use_obj = sum(energy_usage_obj.values())
            new_objective.total_value += sum_use_obj
            new_objective.additive_costs += sum_use_obj
        if energy_costs_obj is not None:
            sum_cost_obj = sum(energy_costs_obj.values())
            new_objective.total_value += sum_cost_obj
            new_objective.additive_costs += sum_cost_obj  # TODO only if energy costs are always positive?
        for e_type, predictions in energy_predictions.items():
            pred: EnergyPrediction | None = predictions.get(new_status.current_order)
            if pred is not None:  # TODO what if it is? Option to use a default?
                energy_usage[e_type] = energy_usage.get(e_type, 0.) + pred.predicted_energy
                if energy_prices and e_type in energy_prices and energy_costs:
                    # determine cost factor for the considered time interval
                    avg_price = energy_prices[e_type].avg(start=start, end=end)[0]
                    if avg_price is None:
                        avg_price = default_energy_price.get(e_type)
                    if avg_price is not None:
                        e_costs = avg_price * pred.predicted_energy / 1e3
                        energy_costs[e_type] = energy_costs.get(e_type, 0.) + e_costs
                        if energy_costs_obj:
                            obj = e_costs * energy_costs_factor
                            energy_costs_obj[e_type] = energy_costs_obj.get(e_type, 0.) + obj
                            new_objective.total_value += obj
                            new_objective.additive_costs += obj
        return new_status, new_objective