import time
import unittest
from datetime import datetime, timezone, timedelta
from typing import Sequence

from dynreact.app_config import DynReActSrvConfig
from dynreact.base.LotsOptimizer import LotsOptimizationState
from dynreact.base.impl.MemoryResultsPersistence import MemoryResultsPersistence
from dynreact.base.impl.SimpleCostProvider import SimpleCostProvider
from dynreact.base.impl.StaticConfigurationProvider import StaticConfigurationProvider
from dynreact.base.impl.StaticSnapshotProvider import StaticSnapshotProvider
from dynreact.base.model import Site, Snapshot, Equipment, Process, Order, LotCreationSettings, \
    ProcessLotCreationSettings
from dynreact.plugins import Plugins
from dynreact.state import DynReActSrvState
from tests.integrationtests.TestSetup import TestSetup


class BatchMtpTest(unittest.TestCase):

    _process = "testProcess"
    _proc_cnt: int = 0

    @staticmethod
    def process_id() -> str:
        proc = f"{BatchMtpTest._process}_{BatchMtpTest._proc_cnt}"
        BatchMtpTest._proc_cnt += 1
        return proc

    @staticmethod
    def _init_for_tests(process: str, orders: int|Sequence[Order], order_weight: float=10, num_plants: int=1, transition_costs: dict[str, dict[str, float]]|None=None,
                        surplus_weight_costs=3, new_lot_costs=10,
                        missing_weight_costs: float=1, batch_config: str="", lot_creation: LotCreationSettings|None=None) -> tuple[DynReActSrvState, Snapshot]:
        process_id = 0
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=process) for p in range(num_plants)]
        test_site = Site(
            processes=[Process(name_short=process, process_ids=[process_id])], equipment=plants,
            storages=[], material_categories=[], lot_creation=lot_creation
        )
        orders = orders if not isinstance(orders, int) else [TestSetup.create_order(f"order_{o}", range(num_plants), order_weight, current_processes=(process_id, )) for o in range(orders)]
        snapshot = Snapshot(timestamp=datetime(2024, 5, 1, tzinfo=timezone.utc),
                            orders=orders, material=TestSetup.create_coils_for_orders(orders, process_id),
                            inline_material={}, lots={})
        if transition_costs is None:
            transition_costs = {o.id: {o2.id: 1 if o != o2 else 0 for o2 in orders} for o in orders}
        cost_provider = SimpleCostProvider("simple:costs", test_site, transition_costs=transition_costs,missing_weight_costs=missing_weight_costs,
                                           surplus_weight_costs=surplus_weight_costs, new_lot_costs=new_lot_costs)
        # not in line with annotated types, but explicitly allowed for test purposes
        cfg = DynReActSrvConfig(config_provider=StaticConfigurationProvider(test_site), lots_batch_config=batch_config,
                                snapshot_provider=StaticSnapshotProvider(test_site, snapshot), cost_provider=cost_provider,
                                results_persistence=MemoryResultsPersistence("memory:1", test_site))
        plugins = Plugins(cfg)
        state = DynReActSrvState(cfg, plugins)
        state.start()
        # Must come before all app imports
        #TestSetup.set_test_providers(test_site, snapshot, transition_costs, missing_weight_costs=missing_weight_costs, batch_config=batch_config)
        return state, snapshot

    def test_batch_mtp_works_basic(self):
        num_orders = 5
        order_weight = 50
        total_weight = 3 * order_weight
        process = BatchMtpTest.process_id()
        lot_creation_settings = LotCreationSettings(processes={process: ProcessLotCreationSettings(total_size=total_weight)}, duration=timedelta(days=1))
        state, snapshot = BatchMtpTest._init_for_tests(process, num_orders, order_weight=order_weight, lot_creation=lot_creation_settings,
                                                      batch_config=f"00:00;P1D;{process}:10:PT1M;test")
        results_persistence = state.get_results_persistence()

        def _check_solution(sol_id: str, result: LotsOptimizationState):
            assert result is not None, "Result is None"
            assert result.best_solution is not None, "Best solution is None"
            orders_assigned = len([o for o, ass in result.best_solution.order_assignments.items() if ass.equipment >= 0])
            assert orders_assigned > 0, "No orders assigned?"
            assert orders_assigned < num_orders, "All orders assigned, despite a smaller target amount provided"

        last_error = None
        for idx in range(100):
            existing_solutions = results_persistence.solutions(snapshot.timestamp, process)
            sol = existing_solutions[0] if len(existing_solutions) > 0 else None
            try:
                assert sol is not None, "No solution found"
                _check_solution(sol, results_persistence.load(snapshot.timestamp, process, sol))
                last_error = None
                break
            except AssertionError as e:
                last_error = e
                time.sleep(1)
        if last_error is not None:
            raise last_error

    def test_batch_mtp_scales_tons_to_duration(self):
        num_orders = 10
        order_weight = 20
        assigned_orders_per_day = 3
        process = BatchMtpTest.process_id()
        total_weight = assigned_orders_per_day * order_weight
        lot_creation_settings = LotCreationSettings(processes={process: ProcessLotCreationSettings(total_size=total_weight)}, duration=timedelta(days=1))
        # here we ask the batch job to create lots for two days in advance, whereas the lot creation settings apply to a single day
        # Therefore, we expect six orders to be assigned in the final solution
        state, snapshot = BatchMtpTest._init_for_tests(process, num_orders, order_weight=order_weight, batch_config=f"00:00;P2D;{process}:10:1m;test", lot_creation=lot_creation_settings)
        results_persistence = state.get_results_persistence()

        def _check_solution(sol_id: str, result: LotsOptimizationState):
            assert result is not None, "Result is None"
            assert result.best_solution is not None, "Best solution is None"
            orders_assigned = len([o for o, ass in result.best_solution.order_assignments.items() if ass.equipment >= 0])
            assert orders_assigned == 2 * assigned_orders_per_day, f"Unexpected number of orders assigned, wanted {2 * assigned_orders_per_day}, got {orders_assigned}"

        last_error = None
        for idx in range(100):
            existing_solutions = results_persistence.solutions(snapshot.timestamp, process)
            sol = existing_solutions[0] if len(existing_solutions) > 0 else None
            try:
                assert sol is not None, "No solution found"
                _check_solution(sol, results_persistence.load(snapshot.timestamp, process, sol))
                last_error = None
                break
            except AssertionError as e:
                last_error = e
                time.sleep(1)
        if last_error is not None:
            raise last_error

    # TODO
    #def test_batch_mtp_respects_start_orders(self):
    #    pass

    # TODO
    #def test_batch_mtp_respects_equipment_availability(self):
    #    pass


