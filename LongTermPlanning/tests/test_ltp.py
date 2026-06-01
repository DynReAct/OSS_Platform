import unittest
from datetime import datetime, timezone, timedelta

from dynreact.base.model import Site, LongTermTargets, StorageLevel, EquipmentAvailability, Process, Equipment, Storage, \
    ProductionTargets, MaterialConstraint, MaterialCategory, MaterialClass, Lot
from dynreact.ltp.LtpInstance import LtpInstance


class LtpTest(unittest.TestCase):

    @staticmethod
    def _ensure_initial_storage_levels_match(initial_levels: dict[str, StorageLevel], resulting_levels: list[dict[str, StorageLevel]]):
        result_initial_levels = resulting_levels[0]
        assert all(stg in initial_levels for stg in result_initial_levels.keys() if stg != "DONE"), \
                    "Storage in result that is not found in initial levels " + next(stg for stg in result_initial_levels.keys() if stg not in initial_levels and stg != "DONE")
        assert all(stg in result_initial_levels for stg in initial_levels.keys()), \
                    "Initial storage not found in result levels " + next(stg for stg in initial_levels.keys() if stg not in result_initial_levels)
        for stg, result_level in result_initial_levels.items():
            if stg not in initial_levels and stg == "DONE":
                continue
            initial_level = initial_levels[stg]
            if initial_level.filling_level < 1e-4 and result_level.filling_level < 1e-4:
                continue
            avg = (initial_level.filling_level + result_level.filling_level)/2
            # more than 5% deviation
            assert abs(initial_level.filling_level - result_level.filling_level) / avg < 5e-2, \
                f"Large deviation between specified initial level and result initial level for storage {stg}: specified {initial_level.filling_level}, found {result_level.filling_level}"
            if result_level.material_levels and initial_level.material_levels:
                all_materials = set(list(result_level.material_levels.keys()) + list(initial_level.material_levels.keys()))
                for mat in all_materials:
                    mat_initial = initial_level.material_levels.get(mat, 0) / avg
                    mat_result = result_level.material_levels.get(mat, 0) / avg
                    if mat_initial < 1e-4 and mat_result < 1e-4:
                        continue
                    mat_avg = (mat_initial + mat_result)/2
                    assert abs(mat_initial - mat_result) / mat_avg < 5e-2, \
                        f"Large deviation between specified initial level and result initial level for storage {stg}, material {mat}. " + \
                        f"Specified {initial_level.material_levels.get(mat, 0)}, found {result_level.material_levels.get(mat, 0)}. Total level: {initial_level.filling_level}."

    def test_ltp_setup_works_single_proc0(self):
        """
        A single process with two equipments, no material classes
        """
        process = "test_proc"
        num_plants = 2
        storages = [Storage(name_short="A", equipment=list(range(num_plants)), capacity_weight=100),
                    Storage(name_short="DONE", equipment=[])]
        # capacity: 24t/day
        plants = [Equipment(id=p, name_short="Plant" + str(p), process=process, storage_in="A",
                            storages_out=["DONE"], throughput_capacity=1) for p in range(num_plants)]
        site = Site(
            processes=[Process(name_short=process, process_ids=[0])],
            equipment=plants, storages=storages, material_categories=[]
        )
        start = datetime(year=2026, month=5, day=1, tzinfo=timezone.utc)
        end = datetime(year=2026, month=5, day=2, tzinfo=timezone.utc)
        period = (start, end)
        structure = LongTermTargets(period=period, production_targets={}, total_production=48)
        initial_storage_levels: dict[str, StorageLevel] = {"A": StorageLevel(storage="A", filling_level=0.5,
                                                    timestamp=start, material_levels={})}
        shifts: list[tuple[datetime, datetime]] = [(start+timedelta(hours=8*idx), start+timedelta(hours=8*(idx+1)))
                                                   for idx in range(3)]
        plant_availabilities: dict[int, EquipmentAvailability] = {p: EquipmentAvailability(equipment=p, period=period,
                                                        daily_baseline=timedelta(days=1)) for p in range(num_plants)}
        instance = LtpInstance("test0", site, structure, initial_storage_levels, shifts, plant_availabilities)
        # TODO return structure
        targets, storage_levels = instance.start(fail_on_validation_error=True)
        LtpTest._ensure_initial_storage_levels_match(initial_storage_levels, storage_levels)

        sub_targets0: dict[str, list[ProductionTargets]] = targets.production_sub_targets
        assert process in sub_targets0, f"Process not scheduled: {process}"
        sub_targets: list[ProductionTargets] = sub_targets0[process]
        assert len(sub_targets) == 3, f"Unexpected number of shifts, wanted: 3, got {len(sub_targets)}"
        assert all(p in st.target_weight for st in sub_targets for p in range(num_plants)), \
            f"Missing equipment in some or all shifts: {[list(st.target_weight.keys()) for st in sub_targets]}"
        assert abs(targets.total_production - 48) < 1e-3, \
            f"Unexpected total production per day, got {targets.total_production}, wanted: 48"
        assert all(abs(st.target_weight[p].total_weight - 8) < 1e-3 for st in sub_targets for p in range(num_plants)), \
            f"Equipment not scheduled at full capacity in some or all shifts: { {{p: val for p, val in st.target_weight.items()} for st in sub_targets} }"

    def test_ltp_setup_works_two_procs0(self):
        """
        Two consecutive processes with a single equipment each, no material classes.
        The first plant is unavailable on the first day of the target period.
        """
        process0 = "test_proc0"
        process1 = "test_proc1"
        process_ids = [process0, process1]
        storages = [Storage(name_short="A", equipment=[0], capacity_weight=100),
                    Storage(name_short="B", equipment=[1], capacity_weight=100),
                    Storage(name_short="DONE", equipment=[])]
        # capacity: 24t/day
        plants = [Equipment(id=0, name_short="Plant0", process=process0, storage_in="A", storages_out=["B"], throughput_capacity=1),
                  Equipment(id=1, name_short="Plant1", process=process1, storage_in="B", storages_out=["DONE"], throughput_capacity=1)]
        processes = [Process(name_short=process0, process_ids=[0], next_steps=[process1]), Process(name_short=process1, process_ids=[1])]
        site = Site(processes=processes, equipment=plants, storages=storages, material_categories=[])
        start = datetime(year=2026, month=5, day=1, tzinfo=timezone.utc)
        end = datetime(year=2026, month=5, day=4, tzinfo=timezone.utc)
        period = (start, end)
        structure = LongTermTargets(period=period, production_targets={}, total_production=24)
        initial_storage_levels: dict[str, StorageLevel] = {
            "A": StorageLevel(storage="A", filling_level=0.5, timestamp=start, material_levels={}),
            "B": StorageLevel(storage="B", filling_level=0, timestamp=start, material_levels={})
        }
        shifts: list[tuple[datetime, datetime]] = [(start+timedelta(hours=8*idx), start+timedelta(hours=8*(idx+1))) for idx in range(9)]
        plant_availabilities: dict[int, EquipmentAvailability] = {
            # Unavailable on day 1, available on day 2
            0: EquipmentAvailability(equipment=0, period=period, daily_baseline=timedelta(days=1), deltas={start.date(): -timedelta(days=1)}),
            1: EquipmentAvailability(equipment=1, period=period, daily_baseline=timedelta(days=1))
        }
        instance = LtpInstance("test1", site, structure, initial_storage_levels, shifts, plant_availabilities)
        targets, storage_levels = instance.start(fail_on_validation_error=True)
        LtpTest._ensure_initial_storage_levels_match(initial_storage_levels, storage_levels)
        sub_targets0: dict[str, list[ProductionTargets]] = targets.production_sub_targets
        assert all(process in sub_targets0 for process in process_ids), \
            f"Process not scheduled: {next(p for p in process_ids if p not in sub_targets0)}"
        targets0 = sub_targets0[process0]
        active_targets0 = [t for t in targets0 if t.target_weight is not None and 0 in t.target_weight and t.target_weight[0].total_weight > 1e-3]
        assert len(active_targets0) > 0, "No shifts scheduled for process 0"
        day1_start = start + timedelta(days=1)
        assert all(t.period[0] >= day1_start for t in active_targets0), \
            f"Process0 scheduled for day 0, despite non-availability: {next(t for t in active_targets0 if t.period[0] < day1_start)}"
        day2_start = day1_start + timedelta(days=1)
        targets1 = sub_targets0[process1]
        active_targets1 = [t for t in targets1 if t.target_weight is not None and 1 in t.target_weight and t.target_weight[1].total_weight > 1e-3]
        assert len(active_targets1) > 0, "No shifts scheduled for process 1"
        assert all(t.period[0] >= day2_start for t in active_targets1), \
            f"Process1 scheduled for day 0 or 1, despite non-availability: {next(t for t in active_targets1 if t.period[0] < day2_start)}"
        assert abs(targets.total_production - 24) < 1e-3, \
            f"Unexpected total production per day, got {targets.total_production}, wanted: 24"
        #print("  Shifts equipment 0 ", [t.period[0] for t in active_targets0])
        #print("  Shifts equipment 1 ", [t.period[0] for t in active_targets1])

    def test_material_structure_works_single_proc(self):
        """
        A test setup with two equipments in one process stage, only one of which can produce all
        material types. But it is not available all the time.
        """
        process = "test_proc"
        num_plants = 2
        mat1 = "matclass1"
        mat2 = "matclass2"
        storages = [Storage(name_short="A", equipment=list(range(num_plants)), capacity_weight=100),
                    Storage(name_short="DONE", equipment=[])]
        mat_cats = [MaterialCategory(id="cat1", name="Material Category 1", classes=[
            MaterialClass(id=mat1, name="Class 1", category="cat1"),
            MaterialClass(id=mat2, name="Class 2", category="cat1", allowed_equipment={process: [0]}),
        ])]
        # capacity: 24t/day
        plants = [Equipment(id=0, name_short="Plant0", process=process, storage_in="A", storages_out=["DONE"], throughput_capacity=1),
                  Equipment(id=1, name_short="Plant1", process=process, storage_in="A", storages_out=["DONE"], throughput_capacity=1,
                            material_constraints=MaterialConstraint(excluded=[mat2]))]
        site = Site(
            processes=[Process(name_short=process, process_ids=[0])],
            equipment=plants, storages=storages, material_categories=mat_cats
        )
        start = datetime(year=2026, month=5, day=1, tzinfo=timezone.utc)
        end = datetime(year=2026, month=5, day=3, tzinfo=timezone.utc)
        period = (start, end)
        structure = LongTermTargets(period=period, total_production=96,
                                # the mat2 target cannot be reached in this example
                                production_targets={mat1: 48, mat2: 48})
        initial_storage_levels: dict[str, StorageLevel] = {"A": StorageLevel(storage="A", filling_level=1,
                                                    timestamp=start, material_levels={mat1: 0.5, mat2: 0.5})}
        shifts: list[tuple[datetime, datetime]] = [(start+timedelta(hours=8*idx), start+timedelta(hours=8*(idx+1)))
                                                   for idx in range(6)]
        plant_availabilities: dict[int, EquipmentAvailability] = {
            # the equipment without material constraints is not available on day 1; therefore a limited amount
            # of material 2 can be produced at all
            0: EquipmentAvailability(equipment=0, period=period, daily_baseline=timedelta(days=1), deltas={start.date(): -timedelta(days=1)}),
            1: EquipmentAvailability(equipment=1, period=period, daily_baseline=timedelta(days=1))
        }
        instance = LtpInstance("test2", site, structure, initial_storage_levels, shifts, plant_availabilities)
        targets, storage_levels = instance.start(fail_on_validation_error=True)
        LtpTest._ensure_initial_storage_levels_match(initial_storage_levels, storage_levels)
        sub_targets0: dict[str, list[ProductionTargets]] = targets.production_sub_targets
        assert process in sub_targets0, f"Process not scheduled: {process}"
        sub_targets: list[ProductionTargets] = sub_targets0[process]
        assert len(sub_targets) == 6, f"Unexpected number of shifts, wanted: 6, got {len(sub_targets)}"
        total_eq0 = sum(st.target_weight[0].total_weight for st in sub_targets if 0 in st.target_weight)
        total_eq1 = sum(st.target_weight[1].total_weight for st in sub_targets if 1 in st.target_weight)
        assert abs(total_eq0 - 24) < 1e-3, \
            f"Unexpected amount of material scheduled for equipment 0, wanted 24t, got {total_eq0}t"
        assert abs(total_eq1 - 48) < 1e-3, \
            f"Unexpected amount of material scheduled for equipment 0, wanted 48t, got {total_eq0}t"
        mat1_total = sum(st.material_weights[mat1] for st in sub_targets if st.material_weights is not None and mat1 in st.material_weights)
        mat2_total = sum(st.material_weights[mat2] for st in sub_targets if st.material_weights is not None and mat2 in st.material_weights)
        assert mat1_total >= 48 - 1e-3, f"Unexpected amount of material 1 scheduled, expected >= 48t, got {mat1_total}t"
        assert mat2_total <= 24 + 1e-3, f"Unexpected amount of material 2 scheduled, expected <= 24t, got {mat2_total}t"

    def test_frozen_lots_work(self):
        """
        Validate that frozen lots are respected. In this setup only material class 1 should be produced, but
        there are frozen lots for class 2 already, which must be respected.
        """
        process1 = "proc1"
        process2 = "proc2"
        processes = (process1, process2)
        mat1 = "matclass1"
        mat2 = "matclass2"
        # The storages must always be filled at least to 1/4 capacity to avoid equipment running dry
        storage_capacity = 32
        storages = [Storage(name_short="A", equipment=[0], capacity_weight=storage_capacity),
                    Storage(name_short="B", equipment=[1], capacity_weight=storage_capacity),
                    Storage(name_short="DONE", equipment=[])]
        mat_cats = [MaterialCategory(id="cat1", name="Material Category 1", classes=[
            MaterialClass(id=mat1, name="Class 1", category="cat1"), MaterialClass(id=mat2, name="Class 2", category="cat1"),
        ])]
        # capacity: 24t/day
        plants = [Equipment(id=0, name_short="Plant0", process=process1, storage_in="A", storages_out=["B"], throughput_capacity=1),
                  Equipment(id=1, name_short="Plant1", process=process2, storage_in="B", storages_out=["DONE"], throughput_capacity=1)]
        site = Site(
            processes=[Process(name_short=process1, process_ids=[0], next_steps=[process2]), Process(name_short=process2, process_ids=[1])],
            equipment=plants, storages=storages, material_categories=mat_cats
        )
        start = datetime(year=2026, month=5, day=1, tzinfo=timezone.utc)
        end = datetime(year=2026, month=5, day=3, tzinfo=timezone.utc)
        period = (start, end)
        structure = LongTermTargets(period=period, total_production=48,
                                    # No mat2 material planned, but already in lots
                                    production_targets={mat1: 48, mat2: 0})
        initial_storage_levels: dict[str, StorageLevel] = {
            # Input storage init: only material 1 => need to add material 2 immediately so equipment 1 can continue producing its mat2 lots
            "A": StorageLevel(storage="A", filling_level=0.5, timestamp=start, material_levels={mat1: 0.25, mat2: 0.25}),
            "B": StorageLevel(storage="B", filling_level=0.25, timestamp=start, material_levels={mat1: 0, mat2: 0.25})
        }
        shifts: list[tuple[datetime, datetime]] = [(start + timedelta(hours=8 * idx), start + timedelta(hours=8 * (idx + 1))) for idx in range(6)]
        plant_availabilities: dict[int, EquipmentAvailability] = {
            0: EquipmentAvailability(equipment=0, period=period, daily_baseline=timedelta(days=1)),
            1: EquipmentAvailability(equipment=1, period=period, daily_baseline=timedelta(days=1))
        }
        eq1 = plants[-1].id
        lots1 = [Lot(id=f"Lot_{eq1}.{idx}", equipment=eq1, active=True, status=4, orders=[f"order_{idx*3 + oidx}" for oidx in range(3)], processing_status="PENDING",
                     weight=8, material_weights={mat2: 8}, start_time=start + timedelta(hours=idx*8), end_time=start + timedelta(hours=(idx+1)*8)) for idx in range(3)]
        instance = LtpInstance("test3", site, structure, initial_storage_levels, shifts, plant_availabilities, frozen_lots={1: lots1})
        targets, storage_levels = instance.start(fail_on_validation_error=True)
        LtpTest._ensure_initial_storage_levels_match(initial_storage_levels, storage_levels)
        sub_targets0: dict[str, list[ProductionTargets]] = targets.production_sub_targets
        assert all(process in sub_targets0 for process in processes), f"Process not scheduled: {next(process for process in processes if process not in sub_targets0)}"
        assert all(len(sub_targets) == 6 for sub_targets in sub_targets0.values()), f"Unexpected number of shifts, wanted: 6, got { {proc: len(targets) for proc, targets in sub_targets0.items()} }"
        last_done_level: StorageLevel = storage_levels[-1]["DONE"]
        mat1_level: float | None = last_done_level.material_levels.get(mat1)
        mat2_level: float|None = last_done_level.material_levels.get(mat2)
        assert mat2_level is not None and mat2_level >= 18, f"Unexpected low level of material 2 produced, got {mat2_level}t, wanted 24t according to frozen lots."
        assert mat1_level is not None and mat1_level >= 18, f"Unexpected low level of material 1 produced, got {mat1_level}t, wanted 48t (realistically only 24t possible)."




