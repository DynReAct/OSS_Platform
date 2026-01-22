# This file must be imported before all app files by the tests
from datetime import datetime

from dynreact.base.impl.SimpleCostProvider import SimpleCostProvider
from dynreact.base.impl.StaticConfigurationProvider import StaticConfigurationProvider
from dynreact.base.impl.StaticSnapshotProvider import StaticSnapshotProvider
from dynreact.base.model import Site, Snapshot, Order, Material, Model
from pydantic import BaseModel

from dynreact.app_config import ConfigProvider, DynReActSrvConfig

ConfigProvider.config = DynReActSrvConfig(
    config_provider="test",
    snapshot_provider="test",
    downtime_provider="test",
    cost_provider="test",
    out_directory="./tests_out",
    max_snapshot_caches=3,
    cors=False,
    auth_method=None,
)


class TestSetup:

    @staticmethod
    def set_test_providers(site: Site, snapshot: Snapshot, transition_costs: dict[str, dict[str, float]],
                           missing_weight_costs=1, surplus_weight_costs=3, new_lot_costs=10):
        """
        This method must be executed before importing the app modules
        """
        from dynreact.app_config import DynReActSrvConfig
        config = DynReActSrvConfig()
        config.lots_batch_config = ""
        config.config_provider = StaticConfigurationProvider(site)
        config.snapshot_provider = StaticSnapshotProvider(site, snapshot)
        config.cost_provider = SimpleCostProvider("simple:costs", site, transition_costs=transition_costs, missing_weight_costs=missing_weight_costs,
                                                surplus_weight_costs=surplus_weight_costs, new_lot_costs=new_lot_costs)
        from dynreact.app_config import ConfigProvider
        ConfigProvider.config = config


    @staticmethod
    def create_order(id: str, plants: list[int], weight: float, due_date: datetime|None=None):
        return Order(id=id, allowed_equipment=plants, target_weight=weight, actual_weight=weight, due_date=due_date, material_properties=TestMaterial(material_id="test"),
                     current_processes=[], active_processes={})

    @staticmethod
    def create_coils_for_orders(orders: list[Order], process: int) -> list[Material]:  # one coil per order
        return [Material(id=o.id + "1", order=o.id, weight=o.actual_weight, order_position=1, current_process=process) for o in orders]


class DynReActAssertions:
    """
    TODO move to DynReActBase?
    """

    @staticmethod
    def assert_sites_equal(site1: Site, site2: Site):
        assert len(site1.processes) == len(site2.processes), "Number of process steps not equal for sites " \
                                    + str(len(site1.processes)) + ": " + str(len(site2.processes))
        assert len(site1.equipment) == len(site2.equipment), "Number of plants not equal for site " \
                                                             + str(len(site1.equipment)) + ": " + str(len(site2.equipment))
        assert len(site1.storages) == len(site2.storages), "Number of storages not equal for site " \
                                                       + str(len(site1.storages)) + ": " + str(len(site2.storages))
        # TODO test if this works...
        assert site1 == site2, "Sites not equal"

    @staticmethod
    def assert_snapshots_equal(snapshot1: Snapshot, snapshot2: Snapshot):
        assert snapshot1.timestamp == snapshot2.timestamp, "Snapshot timestamps differ: " + str(snapshot1.timestamp) + ": " + str(snapshot2.timestamp)
        assert len(snapshot1.orders) == len(snapshot2.orders), "Snapshot orders of different lengths " + str(len(snapshot1.orders))  + ": " + str(len(snapshot2.orders))
        # TODO ?
        #assert snapshot1.orders == snapshot2.orders, "Snapshot orders differ"
        assert [o.id for o in snapshot1.orders] == [o.id for o in snapshot2.orders]
        assert len(snapshot1.material) == len(snapshot2.material), "Number of coils  differ"
        assert snapshot1.material == snapshot2.material, "Coils differ"
        assert len(snapshot1.lots) == len(snapshot2.lots), "Number of lots differ"
        assert snapshot1.lots == snapshot2.lots, "Lots differ"
        # assert snapshot1 == snapshot2, "Generic error"


class TestMaterial(Model):

    material_id: str

