"""
Module: DataSetup data_setup.py

This module runs the setup code necessary to quickly run the functions.

Note:
    These variables should be computed only once.
"""
import os

from dynreact.shortterm.common.data.load_url import load_url_json_get, URL_SNAPSHOTS, URL_SNAPSHOT_DATA

class DataSetup:
    """
    Class DataSetup to process snapshot data.

    Arguments:
        verbose         (int): Level of details being saved.
        snapshot_time   (str): The time of the snapshot being processed

    """

    def __init__(self, verbose: int = 1, snapshot_time: str = None):
        """
        Constructor function for the Log Class

        :param int verbose: Level of details being saved.
        :param str snapshot_time: Snapshot time in ISO8601 format, otherwise use the latest available
        """

        self.verbose = verbose

        self.last_snapshot = snapshot_time or self.get_last_snapshot_timestamp()
        self.last_snapshot_data = self.get_snapshot_data()

        self.all_materials_params = self.get_all_materials_params()
        self.all_equipment_params = self.get_all_equipments_materials()


    def get_last_snapshot_timestamp(self) -> str:
        """
        Get the timestamp of the last snapshot.

        :return: Timestamp for the last available snapshot.
        :rtype: str
        """
        snapshots = load_url_json_get(URL_SNAPSHOTS)
        last_snapshot_timestamp = snapshots[-1]
        if self.verbose > 0:
            print(f"Snapshots: {snapshots}. Last snapshot: {last_snapshot_timestamp}")
        return last_snapshot_timestamp


    def get_snapshot_data(self) -> dict:
        """
        Get the data from the last snapshot.

        :return: Relevant data from SnapShot.
        :rtype: dict
        """
        snapshot_data = load_url_json_get(URL_SNAPSHOT_DATA.format(snapshot_timestamp=self.last_snapshot))
        if self.verbose > 0:
            print(f"Successfully retrieved data of {self.last_snapshot}.")
        return snapshot_data


    def get_all_materials_params(self):
        """
        Get the parameters of each material, including those of the corresponding order

        :return: Dictionary with the involved materials.
        :rtype: dict
        """
        orders = self.last_snapshot_data['orders']
        materials = self.last_snapshot_data['material']
        orders = {order['id']: order for order in orders}
        materials = {material['id']: {**material, 'order': orders[material['order']]} for material in materials}
        return materials


    def get_all_equipments_materials(self) -> dict:
        """
        Get the current materials assigned to each equipment.

        :return: Materials assigned to equipment.
        :rtype: dict
        """
        materials = self.last_snapshot_data['material']
        equipment_materials = dict()
        for material in materials:
            if 'current_equipment' in material:
                equipment_id = material['current_equipment']
                material_id = material['id']
                if equipment_id not in equipment_materials:
                    equipment_materials[equipment_id] = [material_id]
                else:
                    equipment_materials[equipment_id].append(material_id)
        return equipment_materials


    def get_material_params(self, material_id: str) -> dict:
        """
        Get the parameters of the given material.

        :param str material_id: Id of the involved material in the production list.

        :return: Dictionary with all the parameters
        :rtype: dict
        """
        return self.all_materials_params[material_id]


    def get_equipment_materials(self, equipment_id: int) -> list[str]:
        """
        Get the list of materials for the given equipment.

        :param int equipment_id: Id of the interesting equipment

        :return: List of all the materials looking at this equipment.
        :rtype: list
        """
        return self.all_equipment_params[equipment_id]
