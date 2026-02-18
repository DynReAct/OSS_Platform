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
    ProcessLotCreationSettings, Lot, PlannedWorkingShift, Material
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
                        shifts: dict[int, dict[datetime, tuple[timedelta, timedelta]]]|None=None,
                        lots: dict[int, list[Lot]]|None=None, surplus_weight_costs=3, new_lot_costs=10,
                        missing_weight_costs: float=1, batch_config: str="", lot_creation: LotCreationSettings|None=None) -> tuple[DynReActSrvState, Snapshot]:
        """
        :param shifts:  dict[int, dict[shift start => (shift duration, working time)]]
        :return:
        """
        process_id = 0
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=process) for p in range(num_plants)]
        test_site = Site(
            processes=[Process(name_short=process, process_ids=[process_id])], equipment=plants,
            storages=[], material_categories=[], lot_creation=lot_creation
        )
        order_lots: dict[str, str]|None = None  # keys: order ids
        if lots is not None:
            order_lots = {}
            for lot in (lot for eq_lots in lots.values() for lot in eq_lots):
                for order in lot.orders:
                    order_lots[order] = lot.id
        orders = orders if not isinstance(orders, int) else [TestSetup.create_order(f"order_{o}", range(num_plants), order_weight,
                                                        lots={process: order_lots[f"order_{o}"]} if order_lots is not None and f"order_{o}" in order_lots else None,
                                                        current_processes=(process_id, )) for o in range(orders)]
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
                    for sh_start, (duration, working_time) in shifts.get(e, {}).items():
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
        state, snapshot = BatchMtpTest._init_for_tests(process, num_orders, order_weight=order_weight, shifts={0: shifts},
                                                       batch_config=f"00:00;P1D;{process}:50:PT1M;test", lot_creation=lot_creation_settings)
        results_persistence = state.get_results_persistence()

        def _check_solution(sol_id: str, result: LotsOptimizationState):
            assert result is not None, "Result is None"
            assert result.best_solution is not None, "Best solution is None"
            orders_assigned = [o for o, ass in result.best_solution.order_assignments.items() if ass.equipment >= 0]
            assert len(orders_assigned) == num_orders/2, f"Unexpected number of orders assigned, wanted {num_orders/2}, got {len(orders_assigned)}"

        BatchMtpTest._wait_for_solution(_check_solution, results_persistence, snapshot.timestamp, process, seconds=10)

    def test_batch_mtp_respects_existing_lots(self):
        """
        Here we consider a setting with 4 equipments, one of which is already covered with lots until the max planning horizon, so drops out.
        The other three have varying lot horizons, which must be considered by the batch planning algo.
        :return:
        """
        num_orders = 40  # of those 40 orders, 10 will be already assigned to existing lots
        order_weight = 20
        process = BatchMtpTest.process_id()
        now = DatetimeUtils.now()
        # eq 0 -> 1 day covered, eq 1: 2 days covered, eq 2: 0 days covered, eq 3: period fully covered
        lots = {
            0: [Lot(id="Plant0_01", equipment=0, active=True, status=4, orders=["order_0", "order_1"], weight=40, start_time=now, end_time=now+timedelta(days=1))],
            1: [Lot(id="Plant1_01", equipment=1, active=True, status=4, orders=["order_2", "order_3"], weight=40, start_time=now, end_time=now+timedelta(days=1)),
                Lot(id="Plant1_02", equipment=1, active=True, status=3, orders=["order_4", "order_5"], weight=40, start_time=now+timedelta(days=1), end_time=now+timedelta(days=2))],
            2: [],
            3: [Lot(id="Plant3_01", equipment=3, active=True, status=4, orders=["order_6", "order_7"], weight=40, start_time=now, end_time=now+timedelta(days=3)),
                Lot(id="Plant3_02", equipment=3, active=True, status=3, orders=["order_8", "order_9"], weight=40, start_time=now + timedelta(days=3), end_time=now+timedelta(days=6))]
        }
        pre_assigned_orders = [order for eq_lots in lots.values() for lot in eq_lots for order in lot.orders]
        total_weight = (num_orders - len(pre_assigned_orders)) * order_weight
        total_weight_per_plant = total_weight / 3
        lot_creation_settings = LotCreationSettings(processes={process: ProcessLotCreationSettings(total_size=total_weight_per_plant)}, duration=timedelta(days=1))
        state, snapshot = BatchMtpTest._init_for_tests(process, num_orders, order_weight=order_weight, batch_config=f"00:00,mode:append,lh:P5D;P1D;{process}:50:PT1M;test",
                                                    num_plants=4, lot_creation=lot_creation_settings, lots=lots)
        results_persistence = state.get_results_persistence()
        horizons: dict[int, datetime] = {eq: max(lt.end_time for lt in eq_lots) if len(eq_lots) > 0 else now for eq, eq_lots in lots.items()}

        def _check_solution(sol_id: str, result: LotsOptimizationState):
            assert result is not None, "Result is None"
            assert result.best_solution is not None, "Best solution is None"
            new_lots: dict[int, list[Lot]] = result.best_solution.get_lots()
            assert 3 not in new_lots, "New lots created for fully covered equipment"
            assert all(eq in new_lots for eq in (0,1,2)), f"No lots created for equipment {[eq for eq in (0,1,2) if eq not in new_lots]}"
            orders_assigned: list[str] = [o for o, ass in result.best_solution.order_assignments.items() if ass.equipment >= 0]
            assert not any(o in orders_assigned for o in pre_assigned_orders), f"Pre-assigned orders have been re-assigned to a new lot: {[o for o in pre_assigned_orders if o in orders_assigned]}"
            assert all(o.id in orders_assigned for o in snapshot.orders if o.id not in pre_assigned_orders), \
                f"Not all available orders have been assigned to lots: {[o.id for o in snapshot.orders if o.id not in pre_assigned_orders and o.id not in orders_assigned]}"

        BatchMtpTest._wait_for_solution(_check_solution, results_persistence, snapshot.timestamp, process, seconds=10)

    def test_batch_mtp_respects_existing_lots_and_shifts(self):
        """
        Here we consider a setting with 4 equipments, one of which is already covered with lots until the max planning horizon, so drops out.
        The other three have varying lot horizons, which must be considered by the batch planning algo. Furthermore, some equipment only has
        partial shifts.
        :return:
        """
        num_orders = 40  # of those 40 orders, 10 will be already assigned to existing lots
        order_weight = 20
        process = BatchMtpTest.process_id()
        now = DatetimeUtils.now()
        # eq 0 -> 1 day covered, eq 1: 2 days covered, eq 2: 0 days covered, eq 3: period fully covered
        lots = {
            0: [Lot(id="Plant0_01", equipment=0, active=True, status=4, orders=["order_0", "order_1"], weight=40, start_time=now, end_time=now+timedelta(days=1))],
            1: [Lot(id="Plant1_01", equipment=1, active=True, status=4, orders=["order_2", "order_3"], weight=40, start_time=now, end_time=now+timedelta(days=1)),
                Lot(id="Plant1_02", equipment=1, active=True, status=3, orders=["order_4", "order_5"], weight=40, start_time=now+timedelta(days=1), end_time=now+timedelta(days=2))],
            2: [],
            3: [Lot(id="Plant3_01", equipment=3, active=True, status=4, orders=["order_6", "order_7"], weight=40, start_time=now, end_time=now+timedelta(days=3)),
                Lot(id="Plant3_02", equipment=3, active=True, status=3, orders=["order_8", "order_9"], weight=40, start_time=now + timedelta(days=3), end_time=now+timedelta(days=6))]
        }
        pre_assigned_orders = [order for eq_lots in lots.values() for lot in eq_lots for order in lot.orders]
        total_weight = (num_orders - len(pre_assigned_orders)) * order_weight
        total_weight_per_plant = total_weight / 3
        lot_creation_settings = LotCreationSettings(processes={process: ProcessLotCreationSettings(total_size=total_weight_per_plant)}, duration=timedelta(days=1))
        max_num_shifts = 5 * 3  # 5 days times 3 shifts
        shifts = {
            0: {now + timedelta(hours=8 * idx): (timedelta(hours=8), timedelta(hours=8)) for idx in range(max_num_shifts)},
            # reduced working hours for equipment 1 in the time interval where we aim to create new lots
            1: {now + timedelta(hours=8 * idx): (timedelta(hours=8), timedelta(hours=8 if idx < 6 or idx > 9 else 4)) for idx in range(max_num_shifts)},
            2: {now + timedelta(hours=8 * idx): (timedelta(hours=8), timedelta(hours=8)) for idx in range(max_num_shifts)},
            3: {now + timedelta(hours=8 * idx): (timedelta(hours=8), timedelta(hours=8)) for idx in range(max_num_shifts)},
        }
        state, snapshot = BatchMtpTest._init_for_tests(process, num_orders, order_weight=order_weight, batch_config=f"00:00,mode:append,lh:P5D;P1D;{process}:50:PT1M;test",
                                                    num_plants=4, lot_creation=lot_creation_settings, lots=lots, shifts=shifts)
        results_persistence = state.get_results_persistence()
        horizons: dict[int, datetime] = {eq: max(lt.end_time for lt in eq_lots) if len(eq_lots) > 0 else now for eq, eq_lots in lots.items()}

        def _check_solution(sol_id: str, result: LotsOptimizationState):
            assert result is not None, "Result is None"
            assert result.best_solution is not None, "Best solution is None"
            new_lots: dict[int, list[Lot]] = result.best_solution.get_lots()
            assert 3 not in new_lots, "New lots created for fully covered equipment"
            assert all(eq in new_lots for eq in (0,1,2)), f"No lots created for equipment {[eq for eq in (0,1,2) if eq not in new_lots]}"
            orders_assigned: list[str] = [o for o, ass in result.best_solution.order_assignments.items() if ass.equipment >= 0]
            assert not any(o in orders_assigned for o in pre_assigned_orders), f"Pre-assigned orders have been re-assigned to a new lot: {[o for o in pre_assigned_orders if o in orders_assigned]}"
            num_orders_by_plant = {p: len([ass for ass in result.best_solution.order_assignments.values() if ass.equipment == p]) for p in (0,1,2)}
            assert num_orders_by_plant[1] == num_orders_by_plant[0]/2, f"Expected half the number of orders assigned to plant 1, got instead {num_orders_by_plant}"
            assert num_orders_by_plant[2] == num_orders_by_plant[0], f"Expected the smae number of orders assigned to plant 0 and 2, got instead {num_orders_by_plant}"

        BatchMtpTest._wait_for_solution(_check_solution, results_persistence, snapshot.timestamp, process, seconds=10)

    def test_batch_mtp_does_not_schedule_finished_orders(self):
        """
        Here we consider a setting where some material is already scheduled for the targeted process stage, or even the next one, and test that it is not scheduled again.
        :return:
        """
        num_processes = 4
        num_plants_per_process = 3
        order_weight = 20

        now = DatetimeUtils.now()
        processes = [Process(name_short=f"proc_{idx}", process_ids=[idx], next_steps=[f"proc_{idx+1}"] if idx < num_processes - 1 else None) for idx in range(num_processes)]
        plants_by_proc: dict[int, list[Equipment]] = {}
        plants = []
        for proc in processes:
            ids = (proc.process_ids[0] * num_plants_per_process + p for p in range(num_plants_per_process))
            new_plants = [Equipment(id=pid, name_short="Plant" + str(pid), process=proc.name_short) for pid in ids]
            plants_by_proc[proc.process_ids[0]] = new_plants
            plants = plants + new_plants
        process = processes[1].name_short
        p01 = plants_by_proc[0][1]
        p10 = plants_by_proc[1][0]
        p11 = plants_by_proc[1][1]
        p12 = plants_by_proc[1][2]
        p20 = plants_by_proc[2][0]
        p21 = plants_by_proc[2][1]
        p22 = plants_by_proc[2][2]
        p30 = plants_by_proc[3][0]
        plant_ids = [p.id for p in plants]

        existing_lots = {
            # The previous process stage
                    # this lot will finish in time to be considered at the next step
            p01.id: [Lot(id=f"{p01.name_short}_01", equipment=p01.id, active=True, status=4, orders=["allowed_order1", "allowed_order2", "forbidden_order3"],
                         weight=2*order_weight, start_time=now, end_time=now + timedelta(hours=8)),
                     Lot(id=f"{p01.name_short}_02", equipment=p01.id, active=True, status=3, orders=["forbidden_order1", "forbidden_order2"], # this one not
                         weight=2 * order_weight, start_time=now + timedelta(days=1), end_time=now + timedelta(days=3))],
            # The targeted process stage (1); all equipments at this stage already have some existing lots, lasting at least for one day
            p10.id: [Lot(id=f"{p10.name_short}_01", equipment=p10.id, active=True, status=4, orders=["forbidden_order4", "forbidden_order5"],
                         weight=2 * order_weight, start_time=now, end_time=now + timedelta(days=1))],
            p11.id: [Lot(id=f"{p11.name_short}_01", equipment=p11.id, active=True, status=3, orders=["forbidden_order6", "forbidden_order7", "forbidden_order3"],
                         weight=3 * order_weight, start_time=now, end_time=now + timedelta(days=2))],
            p12.id: [Lot(id=f"{p12.name_short}_01", equipment=p12.id, active=True, status=3, orders=["forbidden_order8", "forbidden_order9", "forbidden_order10"],
                         weight=3 * order_weight, start_time=now, end_time=now + timedelta(days=1))],
            # Below is the follow up stage
            p20.id: [Lot(id=f"{p20.name_short}_01", equipment=p20.id, active=True, status=3, orders=["forbidden_order5", "forbidden_order4", "forbidden_order11", "forbidden_order12"],
                         weight=4 * order_weight, start_time=now + timedelta(days=2), end_time=now + timedelta(days=3))],
            p21.id: [Lot(id=f"{p21.name_short}_01", equipment=p21.id, active=True, status=4, orders=["forbidden_order9a","forbidden_order13", "forbidden_order14"],
                         weight=3 * order_weight, start_time=now, end_time=now + timedelta(days=2))],
            # And the one after
            p30.id: [Lot(id=f"{p30.name_short}_01", equipment=p30.id, active=True, status=4, orders=["forbidden_order15", "forbidden_order16"],
                         weight=2 * order_weight, start_time=now, end_time=now + timedelta(days=1)),
                     Lot(id=f"{p30.name_short}_02", equipment=p30.id, active=True, status=3, orders=["forbidden_order13", "forbidden_order17"],
                         weight=2 * order_weight, start_time=now + timedelta(days=1), end_time=now + timedelta(days=2)) ],
        }
        forbidden_orders = [
            TestSetup.create_order(f"forbidden_order1", plant_ids, order_weight, current_processes=[0], lots={processes[0].name_short: existing_lots[p01.id][1].id}, current_equipment=[p01.id]),
            TestSetup.create_order(f"forbidden_order2", plant_ids, order_weight, current_processes=[0], lots={processes[0].name_short: existing_lots[p01.id][1].id}, current_equipment=[p01.id]),
            TestSetup.create_order(f"forbidden_order3", plant_ids, order_weight, current_processes=[0], lots={processes[0].name_short: existing_lots[p01.id][0].id, processes[1].name_short: existing_lots[p11.id][0].id}, current_equipment=[p01.id]),
            TestSetup.create_order(f"forbidden_order4", plant_ids, order_weight, current_processes=[1], lots={processes[1].name_short: existing_lots[p10.id][0].id, processes[2].name_short: existing_lots[p20.id][0].id}, current_equipment=[p10.id]),
            TestSetup.create_order(f"forbidden_order5", plant_ids, order_weight, current_processes=[1], lots={processes[1].name_short: existing_lots[p10.id][0].id, processes[2].name_short: existing_lots[p20.id][0].id}, current_equipment=[p10.id]),
            TestSetup.create_order(f"forbidden_order6", plant_ids, order_weight, current_processes=[1], lots={processes[1].name_short: existing_lots[p11.id][0].id}, current_equipment=[p11.id]),
            TestSetup.create_order(f"forbidden_order7", plant_ids, order_weight, current_processes=[1], lots={processes[1].name_short: existing_lots[p11.id][0].id}, current_equipment=[p11.id]),
            TestSetup.create_order(f"forbidden_order8", plant_ids, order_weight, current_processes=[1, 2], lots={processes[1].name_short: existing_lots[p12.id][0].id}, current_equipment=[p12.id, p20.id]),
            TestSetup.create_order(f"forbidden_order9", plant_ids, order_weight, current_processes=[1, 2], lots={processes[1].name_short: existing_lots[p12.id][0].id}, current_equipment=[p12.id, p22.id]),
            TestSetup.create_order(f"forbidden_order9a", plant_ids, order_weight, current_processes=[1, 2], lots={processes[2].name_short: existing_lots[p21.id][0].id}, current_equipment=[p12.id, p22.id]),
            TestSetup.create_order(f"forbidden_order9b", plant_ids, order_weight, current_processes=[1, 2]),  # already located at the follow-up step
            TestSetup.create_order(f"forbidden_order9c", plant_ids, order_weight, current_processes=[1], active_processes={processes[1].process_ids[0]: "STARTED"}),  # processing at stage 1 already started
            TestSetup.create_order(f"forbidden_order10", plant_ids, order_weight, current_processes=[1], lots={processes[1].name_short: existing_lots[p12.id][0].id}, current_equipment=[p12.id]),
            TestSetup.create_order(f"forbidden_order11", plant_ids, order_weight, current_processes=[2], lots={processes[2].name_short: existing_lots[p20.id][0].id}, current_equipment=[p20.id]),
            TestSetup.create_order(f"forbidden_order12", plant_ids, order_weight, current_processes=[2], lots={processes[2].name_short: existing_lots[p20.id][0].id}, current_equipment=[p01.id]),
            TestSetup.create_order(f"forbidden_order13", plant_ids, order_weight, current_processes=[2], lots={processes[2].name_short: existing_lots[p21.id][0].id, processes[3].name_short: existing_lots[p30.id][1].id}, current_equipment=[p21.id]),
            TestSetup.create_order(f"forbidden_order14", plant_ids, order_weight, current_processes=[2], lots={processes[2].name_short: existing_lots[p21.id][0].id}, current_equipment=[p21.id]),
            TestSetup.create_order(f"forbidden_order15", plant_ids, order_weight, current_processes=[3], lots={processes[3].name_short: existing_lots[p30.id][0].id}, current_equipment=[p30.id]),
            TestSetup.create_order(f"forbidden_order16", plant_ids, order_weight, current_processes=[3], lots={processes[3].name_short: existing_lots[p30.id][0].id}, current_equipment=[p30.id]),
            TestSetup.create_order(f"forbidden_order17", plant_ids, order_weight, current_processes=[3], lots={processes[3].name_short: existing_lots[p30.id][1].id}, current_equipment=[p30.id]),
            TestSetup.create_order(f"forbidden_order18", plant_ids, order_weight, current_processes=[2], current_equipment=[p21.id]),    # no lots, but at the wrong process stage
            TestSetup.create_order(f"forbidden_order19", plant_ids, order_weight, current_processes=[3], current_equipment=[p30.id]),
        ]
        allowed_orders = [
            TestSetup.create_order(f"allowed_order1", plant_ids, order_weight, current_processes=[0, 1], current_equipment=[p01.id, p11.id], lots={processes[0].name_short: existing_lots[p01.id][0].id}),
            TestSetup.create_order(f"allowed_order2", plant_ids, order_weight, current_processes=[0], current_equipment=[p01.id], lots={processes[0].name_short: existing_lots[p01.id][0].id})
        ] + [TestSetup.create_order(f"allowed_order{3+idx}", plant_ids, order_weight, current_processes=[1], current_equipment=[p01.id, p11.id]) for idx in range(28)]   # no lots, but at the right process stage
        orders = forbidden_orders + allowed_orders
        materials = [Material(id=f"{o.id}_{idx}", order=o.id, weight=o.actual_weight / 2, order_positions={proc: 1+idx for proc in o.lots.keys()} if o.lots is not None else None,
                              current_process=o.current_processes[idx % len(o.current_processes)]) for o in orders for idx in range(2)]
        total_weight = sum(o.actual_weight for o in orders)
        test_site = Site(
            processes=processes, equipment=plants, storages=[], material_categories=[],
            lot_creation=LotCreationSettings(duration=timedelta(days=1), processes={process: ProcessLotCreationSettings(total_size=total_weight)})
        )
        snapshot = Snapshot(timestamp=datetime(2024, 5, 1, tzinfo=timezone.utc), orders=orders, material=materials, inline_material={}, lots=existing_lots)
        transition_costs = {o.id: {o2.id: 1 if o != o2 else 0 for o2 in orders} for o in orders}   # flat costs...
        cost_provider = SimpleCostProvider("simple:costs", test_site, transition_costs=transition_costs, missing_weight_costs=1, surplus_weight_costs=3, new_lot_costs=3)
        batch_config=f"00:00,mode:append,lh:P5D;P1D;{process}:100:PT1M;test"
        cfg = DynReActSrvConfig(config_provider=StaticConfigurationProvider(test_site), lots_batch_config=batch_config,
                                snapshot_provider=StaticSnapshotProvider(test_site, snapshot),
                                cost_provider=cost_provider, results_persistence=MemoryResultsPersistence("memory:1", test_site))
        plugins = Plugins(cfg)
        state = DynReActSrvState(cfg, plugins)
        state.start()

        results_persistence = state.get_results_persistence()
        # horizons: dict[int, datetime] = {eq: max(lt.end_time for lt in eq_lots) if len(eq_lots) > 0 else now for eq, eq_lots in lots.items()}
        expected_plants = [p.id for p in (p10, p11, p12)]

        def _check_solution(sol_id: str, result: LotsOptimizationState):
            assert result is not None, "Result is None"
            assert result.best_solution is not None, "Best solution is None"
            new_lots: dict[int, list[Lot]] = result.best_solution.get_lots()
            assert all(p in new_lots for p in expected_plants), f"Lots missing for plants {[p for p in expected_plants if p not in new_lots]}"
            scheduled_orders = [o for lots in new_lots.values() for lot in lots for o in lot.orders]
            for order in allowed_orders:
                assert order.id in scheduled_orders, f"Order {order.id} not scheduled"
            assert all("forbidden" not in o for o in scheduled_orders), f"Forbidden orders scheduled: {[o for o in scheduled_orders if 'forbidden' in o]}"

        sol = BatchMtpTest._wait_for_solution(_check_solution, results_persistence, snapshot.timestamp, process, seconds=10, do_raise=True)
        #assignments = sol.best_solution.order_assignments
        #for ass in assignments.values():
        #    print(f"|  {ass.order} |  {ass.equipment} |  {ass.lot}  |")



    @staticmethod
    def _wait_for_solution(check_solution: Callable[[str, LotsOptimizationState], None],
            results_persistence: ResultsPersistence, snapshot: datetime, process: str, seconds: int=100, do_raise: bool=True) -> LotsOptimizationState|None:
        last_error = None
        last_sol = None
        for idx in range(seconds):
            existing_solutions = results_persistence.solutions(snapshot, process)
            sol = existing_solutions[0] if len(existing_solutions) > 0 else None
            try:
                assert sol is not None, "No solution found"
                last_sol = results_persistence.load(snapshot, process, sol)
                check_solution(sol, last_sol)
                last_error = None
                break
            except AssertionError as e:
                last_error = e
                time.sleep(1)
        if last_error is not None and do_raise:
            raise last_error
        return last_sol