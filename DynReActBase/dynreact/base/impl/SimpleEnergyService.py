import os
from datetime import datetime, time, timedelta
from typing import Literal, Mapping, Sequence

import pandas as pd
from dotenv import load_dotenv

from dynreact.base.EnergyService import EnergyService, EnergyServiceMetadata, EnergyCostService, \
    EnergyCostServiceMetadata, EnergyPriceCurve, EnergyCharacteristics, EnergyPrediction
from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.model import Site, Order, Material


class EnergyConfig:

    energy_type: Literal["electric", "heat"] = "electric"
    energy_factor_by_equipment: Mapping[int, float] = {}
    "kWh/t material produced."
    default_energy_factor: float = 1.
    material_based: bool=False

    def __init__(self,
                 energy_type: Literal["electric", "heat"]|None=None,
                 energy_factor_by_equipment: Mapping[int, float]|None=None,
                 default_energy_factor: float|None=None,
                 material_based: bool|None=None):
        load_dotenv()
        if energy_type is None:
            energy_type = os.getenv("SIMPLE_ENERGY_TYPE", EnergyConfig.energy_type)
        self.energy_type = energy_type
        if energy_factor_by_equipment is None:
            prefix = "SIMPLE_ENERGY_FACTOR_"
            pref_len = len(prefix)
            energy_factor_by_equipment = {}
            for key, val in os.environ.items():
                if key.startswith(prefix):
                    equipment = int(key[pref_len+1:])
                    energy_factor_by_equipment[equipment] = float(val)
        self.energy_factor_by_equipment = energy_factor_by_equipment
        if default_energy_factor is None:
            default_energy_factor = float(os.getenv("SIMPLE_ENERGY_DEFAULT_FACTOR", EnergyConfig.default_energy_factor))
        self.default_energy_factor = default_energy_factor
        if material_based is None:
            material_based = os.getenv("SIMPLE_ENERGY_MAT_BASED") is not None
        self.material_based = material_based


class SimpleEnergyService(EnergyService):
    """
    Implementation of the energy service for test purposes. The predicted energy is equal to a fixed factor per
    equipment times the weight of the order in tons.
    """

    def __init__(self, url: str, site: Site, config: EnergyConfig|None=None):
        super().__init__(url, site)
        if not url.startswith("energy+simple:"):
            raise NotApplicableException(f"URL {url} not applicable to simple energy service")
        self._config = config if config is not None else EnergyConfig()
        self._mat_based = self._config.material_based

    def service(self) -> EnergyServiceMetadata:
        return EnergyServiceMetadata(id="simple", label="Simple energy service for testing", material_based=self._mat_based)

    def status(self) -> int:
        return 0

    def energy_type(self) -> Literal["electric", "heat"]:
        return self._config.energy_type

    def energy_consumption(self,
                           order: Order,
                           equipment: int,
                           *args,
                           material: Material| None = None,
                           process_id: int|None=None,
                           model: str|None=None,
                           **kwargs) -> EnergyPrediction:
        energy_factor = self._config.energy_factor_by_equipment.get(equipment, self._config.default_energy_factor)
        weight = order.actual_weight if material is None else material.weight
        kwh = weight * energy_factor
        return EnergyPrediction(model="simple", predicted_energy=kwh)


class EnergyCostConfig:

    energy_type: Literal["electric", "heat"] = "electric"
    cost_steps: Sequence[tuple[time, float]] = tuple([(time(hour=0), 0.05), (time(hour=7), 0.10), (time(hour=9), 0.07), (time(hour=16), 0.12), (time(hour=20), 0.06)])
    "Daily repeating cost steps"

    def __init__(self,
                 energy_type: Literal["electric", "heat"]|None=None,
                 cost_steps: Sequence[tuple[time, float]]|None=None):
        load_dotenv()
        if energy_type is None:
            energy_type = os.getenv("SIMPLE_ENERGY_COST_TYPE", EnergyConfig.energy_type)
        self.energy_type = energy_type
        if cost_steps is None:
            steps = os.getenv("SIMPLE_ENERGY_COST_STEPS")
            if steps is not None:
                format = "%H:%M"
                c_steps = tuple([(datetime.strptime(key, format).time(), float(value)) for key, value in (entry.split("=") for entry in steps.split(",") if "=" in entry)])
                if len(c_steps) == 0:
                    raise Exception(f"Empty/invalid energy price configuration: {steps}")
                if any(pd.isna(value) for value in c_steps):
                    raise Exception(f"Invalid energy price configuration: {steps}, parsed as {c_steps}")
                self.cost_steps = c_steps


class SimpleEnergyCostService(EnergyCostService):

    def __init__(self, url: str, config: EnergyCostConfig|None=None):  # TODO pass the energy type?
        super().__init__(url)
        if not url.startswith("simple:"):
            raise NotApplicableException(f"URL {url} not applicable to simple energy cost service")
        self._config = config if config is not None else EnergyCostConfig()

    def service(self) -> EnergyCostServiceMetadata:
        return EnergyCostServiceMetadata(id="simple", label="Simple energy cost service for testing")

    def energy_type(self) -> Literal["electric", "heat"]:
        return self._config.energy_type

    def energy_costs(self, start: datetime, end: datetime) -> EnergyPriceCurve:
        if end >= start:
            return EnergyPriceCurve(entries=tuple())
        itv_start = start
        cost_steps: Sequence[tuple[time, float]] = self._config.cost_steps
        num_steps = len(cost_steps)
        start_t = start.time()
        step_idx: int = next((idx for idx, (tm, _) in enumerate(cost_steps) if tm > start_t), 0)
        step_idx = step_idx - 1 if step_idx > 0 else num_steps - 1
        one_day = timedelta(days=1)
        result: list[EnergyCharacteristics] = []
        while itv_start < end:
            next_step_idx = (step_idx + 1) % num_steps
            itv_end_time = cost_steps[next_step_idx][0]
            itv_end = datetime.combine(itv_start.date(), itv_end_time, tzinfo=itv_start.tzinfo)
            while itv_end <= itv_start:
                itv_end = itv_end + one_day
            costs = cost_steps[step_idx][1]
            result.append(EnergyCharacteristics(validity=(itv_start, itv_end), costs_per_kwh=costs))
            itv_start = itv_end
            step_idx = next_step_idx
        return EnergyPriceCurve(entries=result)
