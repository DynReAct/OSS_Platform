import time
import unittest
from datetime import datetime, timezone, timedelta
from typing import Sequence, Callable

from dynreact.app_config import DynReActSrvConfig
from dynreact.base.LotsOptimizer import LotsOptimizationState
from dynreact.base.ResultsPersistence import ResultsPersistence
from dynreact.base.ShiftsProvider import ShiftsProvider
from dynreact.base.impl.DatetimeUtils import DatetimeUtils
from dynreact.base.impl.MemoryResultsPersistence import MemoryResultsPersistence
from dynreact.base.impl.SimpleCostProvider import SimpleCostProvider
from dynreact.base.impl.StaticConfigurationProvider import StaticConfigurationProvider
from dynreact.base.impl.StaticSnapshotProvider import StaticSnapshotProvider
from dynreact.base.model import Site, Snapshot, Equipment, Process, Order, LotCreationSettings, \
    ProcessLotCreationSettings, Lot, PlannedWorkingShift
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
                        shifts: dict[datetime, tuple[timedelta, timedelta]]|None=None,
                        lots: dict[int, list[Lot]]|None=None, surplus_weight_costs=3, new_lot_costs=10,
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
                            inline_material={}, lots=lots if lots is not None else {})
        if transition_costs is None:
            transition_costs = {o.id: {o2.id: 1 if o != o2 else 0 for o2 in orders} for o in orders}
        cost_provider = SimpleCostProvider("simple:costs", test_site, transition_costs=transition_costs,missing_weight_costs=missing_weight_costs,
                                           surplus_weight_costs=surplus_weight_costs, new_lot_costs=new_lot_costs)
        shifts_provider = None
        if shifts is not None:
            shifts_provider = ShiftsProvider("test_shifts:1", test_site)

            def load_all(start: datetime, end: datetime|None=None, limit: int|None=100, equipments: Sequence[int]|None=None) -> dict[int, Sequence[PlannedWorkingShift]]:
                equipments = [e for e in equipments if any(p.id == e for p in plants)] if equipments is not None else [p.id for p in plants]
                result: dict[int, Sequence[PlannedWorkingShift]] = {}
                for e in equipments:
                    e_shifts: list[PlannedWorkingShift] = []
                    for sh_start, (duration, working_time) in shifts.items():
                        sh_end = sh_start + duration
                        if sh_end <= start or (end is not None and sh_start >= end):
                            continue
                        e_shifts.append(PlannedWorkingShift(equipment=e, period=(sh_start, sh_end), worktime=working_time))
                    result[e] = e_shifts
                return result
            shifts_provider.load_all = load_all
        # not in line with annotated types, but explicitly allowed for test purposes
        cfg = DynReActSrvConfig(config_provider=StaticConfigurationProvider(test_site), lots_batch_config=batch_config,
                                snapshot_provider=StaticSnapshotProvider(test_site, snapshot), cost_provider=cost_provider,
                                shifts_provider=shifts_provider,
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

        BatchMtpTest._wait_for_solution(_check_solution, results_persistence, snapshot.timestamp, process, seconds=10)

    def test_batch_mtp_scales_tons_to_duration(self):
        num_orders = 10
        order_weight = 20
        assigned_orders_per_day = 3
        process = BatchMtpTest.process_id()
        total_weight = assigned_orders_per_day * order_weight
        lot_creation_settings = LotCreationSettings(processes={process: ProcessLotCreationSettings(total_size=total_weight)}, duration=timedelta(days=1))
        # here we ask the batch job to create lots for two days in advance, whereas the lot creation settings apply to a single day
        # Therefore, we expect six orders to be assigned in the final solution
        state, snapshot = BatchMtpTest._init_for_tests(process, num_orders, order_weight=order_weight, batch_config=f"00:00;P2D;{process}:10:PT1M;test", lot_creation=lot_creation_settings)
        results_persistence = state.get_results_persistence()

        def _check_solution(sol_id: str, result: LotsOptimizationState):
            assert result is not None, "Result is None"
            assert result.best_solution is not None, "Best solution is None"
            orders_assigned = len([o for o, ass in result.best_solution.order_assignments.items() if ass.equipment >= 0])
            assert orders_assigned == 2 * assigned_orders_per_day, f"Unexpected number of orders assigned, wanted {2 * assigned_orders_per_day}, got {orders_assigned}"

        BatchMtpTest._wait_for_solution(_check_solution, results_persistence, snapshot.timestamp, process, seconds=10)

    def test_batch_mtp_respects_start_orders(self):
        """
        Here we create two groups of orders with 3 orders each, which have low internal transition costs, but high costs between groups. The first group has lowest costs,
        so it would be most efficient to schedule only those, but the start order is from the other group, therefore
        the second group should win.
        """
        num_orders = 6
        order_weight = 20

        process = BatchMtpTest.process_id()
        total_weight = 2 * order_weight
        transition_costs = {f"order_{order}": {f"order_{order2}": 0 if order == order2 else 0.5 if order < 3 and order2 < 3 else 1 if order >= 3 and order2 >= 3 else 25
                                               for order2 in range(num_orders)} for order in range(num_orders)}
        lot_creation_settings = LotCreationSettings(processes={process: ProcessLotCreationSettings(total_size=total_weight)}, duration=timedelta(days=1))
        start_order = "order_3"
        now = DatetimeUtils.now()
        existing_lots: dict[int, list[Lot]] = {0: [Lot(id="lot1", equipment=0, active=True, status=4, orders=[start_order],
                                                       weight=order_weight, start_time=now-timedelta(hours=1), end_time=now)]}
        # here we ask the batch job to create lots for two days in advance, whereas the lot creation settings apply to a single day
        # Therefore, we expect six orders to be assigned in the final solution
        state, snapshot = BatchMtpTest._init_for_tests(process, num_orders, order_weight=order_weight,batch_config=f"00:00;P1D;{process}:50:PT1M;test",
                                                       lots=existing_lots, transition_costs=transition_costs, lot_creation=lot_creation_settings)
        results_persistence = state.get_results_persistence()

        def _check_solution(sol_id: str, result: LotsOptimizationState):
            assert result is not None, "Result is None"
            assert result.best_solution is not None, "Best solution is None"
            orders_assigned = [o for o, ass in result.best_solution.order_assignments.items() if ass.equipment >= 0]
            assert len(orders_assigned) == 2, f"Unexpected number of orders assigned, wanted 2, got {len(orders_assigned)}"
            order_ids = [int(o[6:]) for o in orders_assigned]
            assert all(o >= 3 for o in order_ids), f"Unexpected orders assigned, expected only orders from group 2 (ids >= 3), but found {order_ids}"
            assert all(o != 3 for o in order_ids), f"Start order reassigned: {order_ids}"

        BatchMtpTest._wait_for_solution(_check_solution, results_persistence, snapshot.timestamp, process, seconds=10)

    def test_batch_mtp_respects_equipment_availability(self):
        """
        Here we specify that the equipment only produces part-time, therefore less material can be assigned to it
        :return:
        """
        num_orders = 10
        order_weight = 20
        process = BatchMtpTest.process_id()
        total_weight = num_orders * order_weight   # normally we'd want to produce all orders, but the equipment is only available half of the time
        lot_creation_settings = LotCreationSettings(processes={process: ProcessLotCreationSettings(total_size=total_weight)}, duration=timedelta(days=1))
        now = DatetimeUtils.now()
        shifts = {now + timedelta(hours=8*idx): (timedelta(hours=8), timedelta(hours=4)) for idx in range(3)}
        state, snapshot = BatchMtpTest._init_for_tests(process, num_orders, order_weight=order_weight, shifts=shifts,
                                                       batch_config=f"00:00;P1D;{process}:50:PT1M;test", lot_creation=lot_creation_settings)
        results_persistence = state.get_results_persistence()

        def _check_solution(sol_id: str, result: LotsOptimizationState):
            assert result is not None, "Result is None"
            assert result.best_solution is not None, "Best solution is None"
            orders_assigned = [o for o, ass in result.best_solution.order_assignments.items() if ass.equipment >= 0]
            assert len(orders_assigned) == num_orders/2, f"Unexpected number of orders assigned, wanted {num_orders/2}, got {len(orders_assigned)}"

        BatchMtpTest._wait_for_solution(_check_solution, results_persistence, snapshot.timestamp, process, seconds=10)

    # TODO
    #def test_batch_mtp_respects_existing_lots(self):
    #    pass

    @staticmethod
    def _wait_for_solution(check_solution: Callable[[str, LotsOptimizationState], None],
            results_persistence: ResultsPersistence, snapshot: datetime, process: str, seconds: int=100):
        last_error = None
        for idx in range(seconds):
            existing_solutions = results_persistence.solutions(snapshot, process)
            sol = existing_solutions[0] if len(existing_solutions) > 0 else None
            try:
                assert sol is not None, "No solution found"
                check_solution(sol, results_persistence.load(snapshot, process, sol))
                last_error = None
                break
            except AssertionError as e:
                last_error = e
                time.sleep(1)
        if last_error is not None:
            raise last_error