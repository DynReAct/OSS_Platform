"""
The LongTermPlanning module provides the interface for the LongTermPlanning algorithm.
Currently, only a dummy implementation is provided in the open-source package,
therefore it is required to develop a custom implementation for serious usage of the long-term planning.
"""

from datetime import datetime

from dynreact.base.model import Site, LongTermTargets, MidTermTargets, StorageLevel, EquipmentAvailability


class LongTermPlanning:
    """
    The long term planning interface.
    Implementation expected in module dynreact.longtermplanning.LongTermPlanningImpl
    """

    def __init__(self, uri: str, site: Site):
        self._site = site
        self._uri = uri

    def run(self, id0: str,
            structure: LongTermTargets,
            initial_storage_levels: dict[str, StorageLevel]|None=None,
            shifts: list[tuple[datetime, datetime]]|None=None,
            plant_availabilities: dict[int, EquipmentAvailability] | None=None) -> tuple[MidTermTargets, list[dict[str, StorageLevel]]]:
        """
        Execute the long-term planning optimization.

        Parameters:
            id0: a unique run id
            structure: the production targets for the optimization period
            shifts: if shifts is not specified, it may be part of the optimization target, or a pre-defined
                algorithm for shift creation can be used, depending on the implementation.
            plant_availabilities: information about plant availabilities. Keys: plant id, values: availability.
                If this is not specified or some plant is missing, then a default availability should be assumed, such as 24h per day.

        Returns:
            arg 0: the mid term production targets
            arg 1: Evolution of the storage levels over the planning sub periods (target values at the end of the shifts).
                               The list is for sub periods, the dict keys are storage ids.
        """
        raise Exception("not implemented")
