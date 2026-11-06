"""Exercise agent requests through the real HTTP endpoint and analytical provider."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest import TestCase, main
from unittest.mock import patch

from fastapi.testclient import TestClient
from dynreact.base.model import Site, Snapshot, Order, Material, EquipmentStatus, EquipmentProduction, PlanningData
from dynreact.cost.CostCalculatorImpl import SampleCostProvider
from dynreact.service import service
from dynreact.shortterm.common.data import data_functions as agent


class EmptyLineCostsTest(TestCase):
    def setUp(self):
        root = Path(__file__).resolve().parents[3]
        self.site = Site.model_validate_json((root / 'DynReActService/data/site.json').read_text())
        self.plant = self.site.get_equipment(7)
        now = datetime(2024, 12, 31, 11, tzinfo=timezone.utc)
        orders = [Order(id=oid, target_weight=40, actual_weight=40,
                        allowed_equipment=[7], current_equipment=[7],
                        current_processes=[3], active_processes={},
                        material_properties=dict(width=width, thickness_initial=0.6,
                                                 thickness_final=0.2, finishing_type='ftype1'))
                  for oid, width in [('order7', 995), ('order3', 980)]]
        self.materials = [Material(id=mid, order=o.id, weight=weight, order_position=1,
                                   current_process=3)
                          for mid, o, weight in zip(['a', 'b'], orders, [11, 15])]
        self.snapshot = Snapshot(timestamp=now, orders=orders, material=self.materials,
                                 inline_material={}, lots={})
        self.status = EquipmentStatus(targets=EquipmentProduction(equipment=7, total_weight=100),
                                      snapshot_id=now, planning_period=(now, now+timedelta(days=1)),
                                      current_material=[], planning=PlanningData(delta_weight=100))
        self.provider = SampleCostProvider('sampleuc:costs', self.site)
        # Isolate optimizer selection, retaining the actual analytical update.
        optimizer = SimpleNamespace(update_transition_costs=lambda plant, current, next, status, snapshot, **kw:
            self.provider.update_transition_costs(plant, current, next, status, snapshot, False, **kw))
        factory = SimpleNamespace(create_instance=lambda *a, **kw: optimizer)
        for patcher in [patch.object(service, '_get_snapshot_plant', return_value=(self.snapshot, self.plant)),
                        patch.object(service, '_get_cost_provider', return_value=self.provider),
                        patch.object(service.state, 'get_lots_optimization', return_value=factory)]:
            patcher.start()
            self.addCleanup(patcher.stop)
        self.client = TestClient(service.fastapi_app)

    def post(self, path, payload):
        response = self.client.post(path, json=payload)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def params(self, index):
        m = self.materials[index]
        return dict(id=m.id, order=dict(id=m.order, allowed_equipment=[7]))

    def test_agent_and_service_advance_empty_line_without_mutating_candidates(self):
        initial = self.status.model_dump(mode='json')
        with patch.object(agent, 'load_url_json_post', side_effect=self.post) as calls:
            cost, first = agent.get_transition_cost_and_status(self.params(0), initial, 0)
            self.assertEqual(calls.call_count, 1)
            self.assertIsNone(calls.call_args.kwargs['payload']['current_order'])
            self.assertEqual(cost, 0)
            self.assertEqual(first['current_order'], 'order7')
            self.assertEqual(first['current_material'], ['a'])
            self.assertEqual(first['planning']['delta_weight'], 89)
            self.assertEqual(first['planning']['lot_weights'], [11])
            self.assertEqual(first['planning']['orders_count'], 1)
            self.assertIsNone(initial['current_order'])
            self.assertEqual(initial['planning']['delta_weight'], 100)
            cost, second = agent.get_transition_cost_and_status(self.params(1), first, 0)
            self.assertEqual(cost, 2.5)
            self.assertEqual(second['current_order'], 'order3')
            self.assertEqual(second['current_material'], ['b'])
            self.assertEqual(second['planning']['delta_weight'], 74)
            self.assertEqual(second['planning']['lot_weights'], [26])
            self.assertEqual(first['current_order'], 'order7')
            self.assertEqual(first['planning']['delta_weight'], 89)

    def test_same_order_material_advances_weight_without_extra_order(self):
        first, _ = self.provider.update_transition_costs(
            self.plant, None, self.snapshot.orders[0], self.status, self.snapshot,
            True, next_material=self.materials[0])
        material = self.materials[0].model_copy(update=dict(id='a2', weight=4))
        second, _ = self.provider.update_transition_costs(
            self.plant, self.snapshot.orders[0], self.snapshot.orders[0], first,
            self.snapshot, False, next_material=material)
        self.assertEqual(second.current_material, ['a', 'a2'])
        self.assertEqual(second.planning.delta_weight, 85)
        self.assertEqual(second.planning.lot_weights, [15])
        self.assertEqual(second.planning.orders_count, 1)
        self.assertEqual(second.planning.transition_costs, 0)
        self.assertEqual(first.planning.delta_weight, 89)

    def test_missing_material_is_rejected_for_empty_line(self):
        response = self.client.post('/costs/transitions-stateful', json=dict(
            equipment=7, snapshot_id=self.snapshot.timestamp.isoformat(), current_order=None,
            next_order='order7', next_material='missing',
            equipment_status=self.status.model_dump(mode='json')))
        self.assertEqual(response.status_code, 404)


if __name__ == '__main__':
    main()
