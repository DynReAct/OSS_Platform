"""
Module: DataSetup data_setup.py

This module runs the setup code necessary to quickly run the functions.

Note:
    These variables should be computed only once.
    However, they are currently being computed multiple times when the module is imported in different files.
    This cannot be avoided by simply using @cache or @lru_cache(maxsize=None) from `functools`.
    Using `diskcache` may work, but I don't think this is worth adding a dependency to the project.
    The scripts run quickly anyway.
"""
from data.load_url import load_url_json_get, URL_SNAPSHOTS, URL_SNAPSHOT_DATA


def get_last_snapshot_timestamp(verbose: int = 1) -> str:
    """
    Get the timestamp of the last snapshot.

    :param int verbose: Verbosity Level.

    :return: Timestamp for the last available snapshot.
    :rtype: str
    """
    snapshots = load_url_json_get(URL_SNAPSHOTS)
    last_snapshot_timestamp = snapshots[-1]
    if verbose > 0:
        print(f"Snapshots: {snapshots}. Last snapshot: {last_snapshot_timestamp}")
    return last_snapshot_timestamp


def get_snapshot_data(snapshot_timestamp: str, verbose: int = 1) -> dict:
    """
    Get the data from the last snapshot.

    :param str sanpshot_timestamp: Timestamp for the interesting snapshot.
    :param int verbose: Verbosity Level.

    :return: Relevant data from SnapShot.
    :rtype: dict
    """
    snapshot_data = load_url_json_get(URL_SNAPSHOT_DATA.format(snapshot_timestamp=snapshot_timestamp))
    if verbose > 0:
        print(f"Successfully retrieved data of {snapshot_timestamp}.")
    return snapshot_data


def get_all_materials_params():
    """
    Get the parameters of each material, including those of the corresponding order

    :return: Dictionary with the involved materials.
    :rtype: dict
    """
    orders = LAST_SNAPSHOT_DATA['orders']
    materials = LAST_SNAPSHOT_DATA['coils']
    orders = {order['id']: order for order in orders}
    materials = {material['id']: {**material, 'order': orders[material['order']]} for material in materials}
    return materials


def get_all_resources_materials() -> dict:
    """
    Get the current materials assigned to each resource.
    
    :return: Materials assigned to a resource.
    :rtype: dict
    """
    materials = LAST_SNAPSHOT_DATA['coils']
    resource_materials = dict()
    for material in materials:
        if 'current_plant' in material:
            resource_id = material['current_plant']
            material_id = material['id']
            if resource_id not in resource_materials:
                resource_materials[resource_id] = [material_id]
            else:
                resource_materials[resource_id].append(material_id)
    return resource_materials


LAST_SNAPSHOT = get_last_snapshot_timestamp()  # Can also be 'now'
LAST_SNAPSHOT_DATA = get_snapshot_data(LAST_SNAPSHOT)

ALL_MATERIALS_PARAMS = get_all_materials_params()
ALL_RESOURCES_MATERIALS = get_all_resources_materials()

