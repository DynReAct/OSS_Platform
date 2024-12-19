import math
import unittest
from datetime import datetime, timezone, timedelta

from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.model import Site, Snapshot, Equipment, Process, EquipmentStatus, Order
from fastapi.testclient import TestClient

from dynreact.service.model import EquipmentTransitionStateful
# Must come before all app imports
from tests.integrationtests.TestSetup import TestSetup, DynReActAssertions


class ServiceTest(unittest.TestCase):

    process = "testProcess"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        process_id = 0
        num_plants = 1
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=ServiceTest.process) for p in range(num_plants)]
        test_site = Site(
            processes=[Process(name_short=ServiceTest.process, process_ids=[process_id])],
            equipment=plants,
            storages=[]
        )
        orders = [TestSetup.create_order("a", range(num_plants), 10), TestSetup.create_order("b", range(num_plants), 10)]
        snapshot = Snapshot(timestamp=datetime(2024, 5, 1, tzinfo=timezone.utc),
                            orders=orders, material=TestSetup.create_coils_for_orders(orders, process_id),
                            inline_material={}, lots={})
        transition_costs = {"a": {"b": 1}, "b": {"a": 2}}  # in this example it is cheaper to produce a first then b, than vice versa
        missing_weight_costs = 1
        # Must come before all app imports
        TestSetup.set_test_providers(test_site, snapshot, transition_costs, missing_weight_costs=missing_weight_costs)

        from dynreact.service.service import fastapi_app
        self._site = test_site
        self._snapshot = snapshot
        self._transition_costs = transition_costs
        self._missing_weight_costs = missing_weight_costs
        self._client = TestClient(fastapi_app)

    def test_site_request_works(self):
        response = self._client.get("/site", headers={"Accept": "application/json"})
        response.raise_for_status()
        json_resp = response.json()
        site_resp: Site = Site.model_validate(json_resp)
        DynReActAssertions.assert_sites_equal(site_resp, self._site)

    def test_snashot_list_request_works(self):
        response = self._client.get("/snapshots", headers={"Accept": "application/json"})
        response.raise_for_status()
        json_resp = response.json()
        assert len(json_resp) == 1, "Unexpected number of snapshots " + str(len(json_resp))
        timestamp = DatetimeUtils.parse_date(json_resp[0])
        assert timestamp == self._snapshot.timestamp, "Unexpected snapshot timestamp " + str(timestamp) + ", expected " + str(self._snapshot.timestamp)

    def test_snapshot_request_works(self):
        endpoint = "/snapshots/" + DatetimeUtils.format(self._snapshot.timestamp)
        response = self._client.get(endpoint, headers={"Accept": "application/json"})
        response.raise_for_status()
        json_resp = response.json()
        snapshot: Snapshot = Snapshot.model_validate(json_resp)
        # fails... might be a pydantic bug
        #assert snapshot == self._snapshot, "Snapshots do not match"
        DynReActAssertions.assert_snapshots_equal(snapshot, self._snapshot)

    def test_transition_costs(self):
        order1 = self._snapshot.orders[0].id
        order2 = self._snapshot.orders[1].id
        from dynreact.service.model import EquipmentTransition
        body = EquipmentTransition(equipment=self._site.equipment[0].id, snapshot_id=self._snapshot.timestamp, current=order1, next=order2)
        response = self._client.post("/costs/transitions", content=body.model_dump_json(),
                                     headers={"Accept": "application/json", "Content-Type": "application/json"})
        response.raise_for_status()
        costs: float = response.json()
        assert isinstance(costs, float), "Numeric response expected, got " + str(costs) + " of " + str(type(costs))
        assert math.isclose(costs, self._transition_costs[order1][order2]), "Unexpected transition costs " + str(costs) \
                                                        + ", expected " + str(self._transition_costs[order1][order2])
        # and the other way round
        body = EquipmentTransition(equipment=self._site.equipment[0].id, snapshot_id=self._snapshot.timestamp, current=order2, next=order1)
        response = self._client.post("/costs/transitions", content=body.model_dump_json(),
                                     headers={"Accept": "application/json", "Content-Type": "application/json"})
        response.raise_for_status()
        costs: float = response.json()
        assert math.isclose(costs, self._transition_costs[order2][order1]), "Unexpected transition costs " + str(costs) \
                                                        + ", expected " + str(self._transition_costs[order2][order1])

    def test_stateful_transition_costs1(self):
        plant_id = self._site.equipment[0].id
        snapshots_response = self._client.get("/snapshots", headers={"Accept": "application/json"})
        snapshots_response.raise_for_status()
        timestamp_formatted = snapshots_response.json()[0]
        snapshot_id: datetime = DatetimeUtils.parse_date(timestamp_formatted)
        planning_period = (snapshot_id, snapshot_id + timedelta(days=1))
        target_weight = 20
        endpoint = f"/costs/status/{plant_id}/{timestamp_formatted}?planning_horizon=1d&target_weight={target_weight}"
        status_resp = self._client.get(endpoint, headers={"Accept": "application/json"})
        status_resp.raise_for_status()
        status: EquipmentStatus = EquipmentStatus.model_validate(status_resp.json())
        self.assertAlmostEqual(status.planning.target_fct, self._missing_weight_costs * target_weight,
                               msg="Unexpected target function value for empty production")
        endpoint = "/costs/transitions-stateful"
        transition: EquipmentTransitionStateful = EquipmentTransitionStateful(equipment=plant_id, snapshot_id=snapshot_id,
                                                                              current="", next="", equipment_status=status)
        prev: Order|None = None
        for order in self._snapshot.orders:
            transition.current = prev.id if prev is not None else ""  # required field!
            transition.next = order.id
            transition.equipment_status = status
            transition_resp = self._client.post(endpoint, content=transition.model_dump_json(),
                            headers={"Accept": "application/json", "Content-Type": "application/json"})
            transition_resp.raise_for_status()
            status = EquipmentStatus.model_validate(transition_resp.json())
            prev = order
        self.assertAlmostEqual(status.planning.target_fct, 1, msg="Unexpected target function value")


if __name__ == '__main__':
    unittest.main()


