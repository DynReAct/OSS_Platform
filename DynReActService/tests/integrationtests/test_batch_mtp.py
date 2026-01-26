import time
import unittest
from datetime import datetime, timezone
from typing import Sequence

from dynreact.base.LotsOptimizer import LotsOptimizationState
from dynreact.base.model import Site, Snapshot, Equipment, Process,Order
from tests.integrationtests.TestSetup import TestSetup


class BatchMtpTest(unittest.TestCase):

    process = "testProcess"

    @staticmethod
    def _init_for_tests(orders: int|Sequence[Order], order_weight: float=10, num_plants: int=1, transition_costs: dict[str, dict[str, float]]|None=None,
                        missing_weight_costs: float=1, batch_config: str="") -> tuple[Site, Snapshot]:
        process_id = 0
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=BatchMtpTest.process) for p in range(num_plants)]
        test_site = Site(
            processes=[Process(name_short=BatchMtpTest.process, process_ids=[process_id])], equipment=plants,
            storages=[], material_categories=[]
        )
        orders = orders if not isinstance(orders, int) else [TestSetup.create_order(f"order_{o}", range(num_plants), order_weight, current_processes=(process_id, )) for o in range(orders)]
        snapshot = Snapshot(timestamp=datetime(2024, 5, 1, tzinfo=timezone.utc),
                            orders=orders, material=TestSetup.create_coils_for_orders(orders, process_id),
                            inline_material={}, lots={})
        if transition_costs is None:
            transition_costs = {o.id: {o2.id: 1 if o != o2 else 0 for o2 in orders} for o in orders}
        # Must come before all app imports
        TestSetup.set_test_providers(test_site, snapshot, transition_costs, missing_weight_costs=missing_weight_costs, batch_config=batch_config)
        return test_site, snapshot

    def test_batch_mtp_works_basic(self):
        num_orders = 5
        order_weight = 50
        total_weight = 3 * order_weight
        # TODO how to specify the target values for the batch job? => need to evaluate plant availability and capacity
        site, snapshot = BatchMtpTest._init_for_tests(4, batch_config=f"00:00;{BatchMtpTest.process}:10:1m;test")
        from dynreact.app import state  # start dynreact app
        results_persistence = state.get_results_persistence()
        existing_solutions = []
        for idx in range(100):
            existing_solutions = results_persistence.solutions(snapshot.timestamp, BatchMtpTest.process)
            if len(existing_solutions) > 0:
                break
            time.sleep(1)
        assert len(existing_solutions) > 0, "No batch operation result found"
        assert len(existing_solutions) == 1, "Multiple batch operation results found => ?"
        result: LotsOptimizationState = results_persistence.load(snapshot.timestamp, BatchMtpTest.process, existing_solutions[0])
        assert result is not None, "Result is None"
        assert result.best_solution is not None, "Best solution is None"
