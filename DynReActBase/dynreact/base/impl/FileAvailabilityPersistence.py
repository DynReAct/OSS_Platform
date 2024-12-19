from datetime import datetime, date
import glob
import os

from dynreact.base.PlantAvailabilityPersistence import PlantAvailabilityPersistence
from dynreact.base.model import Site, EquipmentAvailability


class FileAvailabilityPersistence(PlantAvailabilityPersistence):

    def __init__(self, uri: str, site: Site):
        super().__init__(uri, site)
        uri_lower = uri.lower()
        if not uri_lower.startswith("default+file:"):
            raise Exception("Unexpected URI for file availability persistence: " + str(uri))
        folder = uri[len("default+file:"):]
        self._folder = os.path.join(folder, "availability") if not folder.lower().endswith("availability") else folder
        os.makedirs(folder, exist_ok=True)

    def _get_folder_plant(self, plant: int):
        return os.path.join(self._folder, "plants", str(plant))

    def _get_file_plant(self, plant: int, start_time: date):
        return os.path.join(self._get_folder_plant(plant), start_time.strftime("%Y-%m-%d") + ".json")

    @staticmethod
    def _try_parse_date(file: str) -> date|None:
        file = file.replace("\\", "/")
        if "/" in file:
            file = file[file.rindex("/")+1:]
        dt = file.replace(".json", "")
        try:
            return datetime.strptime(dt,"%Y-%m-%d").date()
        except:
            return None

    def store(self, availability: EquipmentAvailability):
        if availability is None:
            raise Exception("None")
        self._site.get_equipment(availability.equipment, do_raise=True)
        folder = self._get_folder_plant(availability.equipment)
        os.makedirs(folder, exist_ok=True)
        new_file = self._get_file_plant(availability.equipment, availability.period[0])
        json_str = availability.model_dump_json(exclude_unset=True, exclude_none=True)
        with open(new_file, "w") as file:
            file.write(json_str)

    def delete(self, plant: int, start: date, end: date) -> bool:
        folder = self._get_folder_plant(plant)
        if not os.path.isdir(folder):
            return False
        found: bool = False
        for fl in sorted(glob.glob(folder + "/*.json")):
            dt: date|None = FileAvailabilityPersistence._try_parse_date(fl)
            if dt is None:
                continue
            if dt >= start and dt < end:
                os.remove(fl)   # TODO check if fl contains the full path
                found = True
            elif dt > end:
                break
        return found

    def load(self, plant: int, start: date, end: date) -> list[EquipmentAvailability]:
        folder = self._get_folder_plant(plant)
        if not os.path.isdir(folder):
            return []
        result = []
        for fl in sorted(glob.glob(folder + "/*.json")):
            dt: date|None = FileAvailabilityPersistence._try_parse_date(fl)
            if dt is None:
                continue
            if dt >= start and dt < end:
                content = None
                with open(fl, "r") as file:
                    content = file.read()
                av = EquipmentAvailability.model_validate_json(content)
                result.append(av)
            elif dt > end:
                break
        return result

    def plant_data(self, start: date, end: date) -> list[int]:
        """
        Provides information about which plants have availability information
        :param dt:
        :return:
        """
        base = os.path.join(self._folder, "plants")
        if not os.path.isdir(base):
            return []
        result = []
        for directory in os.listdir(base):
            try:
                plant = int(directory)
                for fl in sorted(glob.glob(os.path.join(base, directory, "*.json"))):
                    dt: date | None = FileAvailabilityPersistence._try_parse_date(fl)
                    if dt is None:
                        continue
                    if dt >= start and dt < end:
                        result.append(plant)
                    if dt >= start:
                        break
            except:
                continue
        return result

    def load_all(self, start: date, end: date) -> dict[int, list[EquipmentAvailability]]:
        base = os.path.join(self._folder, "plants")
        if not os.path.isdir(base):
            return dict()
        result = {}
        for directory in os.listdir(base):
            try:
                plant = int(directory)
                availabilities = self.load(plant, start, end)
                if len(availabilities) > 0:
                    result[plant] = availabilities
            except:
                continue
        return result
