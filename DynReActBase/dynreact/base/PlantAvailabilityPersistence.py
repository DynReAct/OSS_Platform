from datetime import date

from dynreact.base.model import Site, EquipmentAvailability


class PlantAvailabilityPersistence:
    """
    A service to load and store plant availability information
    Implementation expected in dynreact.availability.AvailabilityPersistenceImpl
    """

    def __init__(self, url: str, site: Site):
        self._url = url
        self._site = site

    def store(self, availability: EquipmentAvailability):
        raise Exception("not implemented")

    def delete(self, plant: int, start: date, end: date) -> bool:
        raise Exception("not implemented")

    def load(self, plant: int, start: date, end: date) -> list[EquipmentAvailability]:
        raise Exception("not implemented")

    def plant_data(self, start: date, end: date) -> list[int]:
        """
        Provides information about which plants have availability information
        :param start:
        :param end:
        :return:
        """
        raise Exception("not implemented")

    def load_all(self, start: date, end: date) -> dict[int, list[EquipmentAvailability]]:
        """
        :param start:
        :param end:
        :return: a dictionary with keys = plant ids, values = availability data
        """
        raise Exception("not implemented")

