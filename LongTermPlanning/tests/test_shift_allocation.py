import unittest
from datetime import datetime, timezone, timedelta

import numpy as np

from dynreact.base.model import Storage, Equipment, Site, Process, LongTermTargets, StorageLevel, EquipmentAvailability, \
    ProductionTargets, MaterialCategory, MaterialClass
from dynreact.ltp.ShiftAllocator import ShiftAllocator


class ShiftAllocationTest(unittest.TestCase):

    def test_shift_allocation_works_basic(self):
        """
        Basic setup with two processes and two storages, requiring a single shift to fulfil the demand.
        """
        processes = ["test_proc0", "test_proc1"]
        storages = [Storage(name_short="A", equipment=[0], capacity_weight=100),
                    Storage(name_short="B", equipment=[1], capacity_weight=100),
                    Storage(name_short="DONE", equipment=[])]
        # capacity: 24t/day
        plants = [Equipment(id=0, name_short="Plant0", process=processes[0], storage_in="A", storages_out=["B"], throughput_capacity=1),
                  Equipment(id=1, name_short="Plant1", process=processes[1], storage_in="B", storages_out=["DONE"], throughput_capacity=1),]
        site = Site(
            processes=[Process(name_short=process, process_ids=[idx]) for idx, process in enumerate(processes)],
            equipment=plants, storages=storages, material_categories=[]
        )
        start = datetime(year=2026, month=5, day=1, tzinfo=timezone.utc)
        end = datetime(year=2026, month=5, day=3, tzinfo=timezone.utc)
        period = (start, end)
        structure = LongTermTargets(period=period, production_targets={}, total_production=6)  # can be produced in a single shift
        initial_storage_levels: dict[str, StorageLevel] = {
            "A": StorageLevel(storage="A", filling_level=0.5, timestamp=start, material_levels={}),
            "B": StorageLevel(storage="B", filling_level=0.5, timestamp=start, material_levels={})
        }
        # two days, 6 shifts
        shifts: list[tuple[datetime, datetime]] = [(start + timedelta(hours=8 * idx), start + timedelta(hours=8 * (idx + 1))) for idx in range(6)]
        num_shifts = len(shifts)
        plant_availabilities: dict[int, EquipmentAvailability] = {p: EquipmentAvailability(equipment=p, period=period, daily_baseline=timedelta(days=1)) for p in (0, 1)}
        # initial result: evenly distributed production, 1 hour per shift
        equipment_to_storages = {0: {"B": np.ones(shape=(1, num_shifts), dtype=np.float64)}, 1: {"DONE": np.ones(shape=(1, num_shifts), dtype=np.float64)}}
        storages_to_equipment = {"A": {0: np.ones(shape=(1, num_shifts), dtype=np.float64)}, "B": {1: np.ones(shape=(1, num_shifts), dtype=np.float64)}}
        done_level = np.array([[idx for idx in range(num_shifts+1)]], dtype=np.float64)
        storage_levels = {"A": 0.5 * np.ones(shape=(1, num_shifts+1), dtype=np.float64), "B": 0.5 * np.ones(shape=(1, num_shifts+1), dtype=np.float64), "DONE": done_level}
        allocator = ShiftAllocator(site, structure, shifts, plant_availabilities, storage_levels, equipment_to_storages, storages_to_equipment, rand_seed=42)
        result, levels = allocator.run()
        assert all(proc in result.production_sub_targets for proc in processes), f"Process missing in allocator result: {next(proc for proc in processes if proc not in result.production_sub_targets)}"
        proc0_targets: list[ProductionTargets] = result.production_sub_targets[processes[0]]
        active_shifts0 = [t for t in proc0_targets if 0 in t.target_weight and t.target_weight[0].total_weight >= 1e-4]
        assert len(active_shifts0) == 1, f"Expected a single active shift for equipment 0, got production rates {[t.target_weight[0].total_weight if 0 in t.target_weight else None for t in proc0_targets]}"
        proc1_targets: list[ProductionTargets] = result.production_sub_targets[processes[1]]
        active_shifts1 = [t for t in proc1_targets if 1 in t.target_weight and t.target_weight[1].total_weight >= 1e-4]
        assert len(active_shifts1) == 1, f"Expected a single active shift for equipment 1, got production rates {[t.target_weight[1].total_weight if 1 in t.target_weight else None for t in proc1_targets]}"
        storage_levels2: dict[str, list[float]] = {stg: [level_dict[stg].filling_level for level_dict in levels if stg in level_dict] for stg in ("A", "B", "DONE")}
        negative_storage = next((stg for stg, lvl in storage_levels2.items() if any(l < 0 for l in lvl)), None)
        assert negative_storage is None, f"Storage with negative level found: {negative_storage}"

    def test_shift_allocation_works_with_classes(self):
        """
        A simple setup with material classes
        """
        processes = ["test_proc0", "test_proc1"]
        storages = [Storage(name_short="A", equipment=[0], capacity_weight=100),
                    Storage(name_short="B", equipment=[1], capacity_weight=100),
                    Storage(name_short="DONE", equipment=[])]
        # capacity: 24t/day
        plants = [Equipment(id=0, name_short="Plant0", process=processes[0], storage_in="A", storages_out=["B"], throughput_capacity=1),
                  Equipment(id=1, name_short="Plant1", process=processes[1], storage_in="B", storages_out=["DONE"], throughput_capacity=1), ]
        mat_cats = [
            MaterialCategory(id="cat0", classes=[
                MaterialClass(id="cat0_class0", category="cat0"),
                MaterialClass(id="cat0_class1", category="cat0"),
                MaterialClass(id="cat0_class2", category="cat0"),
            ]),
            MaterialCategory(id="cat1", classes=[
                MaterialClass(id="cat1_class0", category="cat1"),
                MaterialClass(id="cat1_class1", category="cat1"),
            ])
        ]
        site = Site(
            processes=[Process(name_short=process, process_ids=[idx]) for idx, process in enumerate(processes)],
            equipment=plants, storages=storages, material_categories=mat_cats
        )
        # 4 days of production, equipment capacity: 96t
        start = datetime(year=2026, month=5, day=1, tzinfo=timezone.utc)
        end = datetime(year=2026, month=5, day=5, tzinfo=timezone.utc)
        period = (start, end)
        # requires exactly half the capacity on average
        structure = LongTermTargets(period=period, total_production=48, production_targets={
            "cat0_class0": 16, "cat0_class1": 16, "cat0_class2": 16,
            "cat1_class0": 24, "cat1_class1": 24
        })
        """
        initial_storage_levels: dict[str, StorageLevel] = {
            "A": StorageLevel(storage="A", filling_level=0.5, timestamp=start, material_levels={
                "cat0_class0": 0.05, "cat0_class1": 0.05, "cat0_class2": 0.4,
                "cat1_class0": 0.05, "cat1_class1": 0.45
            }),
            "B": StorageLevel(storage="B", filling_level=0.5, timestamp=start, material_levels={
                "cat0_class0": 0.05, "cat0_class1": 0.2, "cat0_class2": 0.25,
                "cat1_class0": 0, "cat1_class1": 0.5
            })
        }
        """
        # four days, 12 shifts
        shifts: list[tuple[datetime, datetime]] = [(start + timedelta(hours=8 * idx), start + timedelta(hours=8 * (idx + 1))) for idx in range(12)]
        num_shifts = len(shifts)
        plant_availabilities: dict[int, EquipmentAvailability] = {p: EquipmentAvailability(equipment=p, period=period, daily_baseline=timedelta(days=1)) for p in (0, 1)}
        # need to start with a config that is valid but may easily lead to an invalid shift-adapted result
        # initial result: evenly distributed production, equipment operating at half capacity all the time
        mat_shape = sum(1 for cat in mat_cats for _ in cat.classes) + 1
        hours_per_shift = 8
        equipment_to_storages = {
            0: {"B": 0.5 * hours_per_shift * np.ones(shape=(mat_shape, num_shifts), dtype=np.float64)},
            1: {"DONE": 0.5 * hours_per_shift * np.ones(shape=(mat_shape, num_shifts), dtype=np.float64)}}
        # amounts per class
        equipment_to_storages[0]["B"][0:3, :] = 0.5 / 3 * hours_per_shift
        equipment_to_storages[0]["B"][3:5, :] = 0.5 / 2 * hours_per_shift
        equipment_to_storages[1]["DONE"][0:3, :] = 0.5 / 3 * hours_per_shift
        equipment_to_storages[1]["DONE"][3:5, :] = 0.5 / 2 * hours_per_shift
        storages_to_equipment = {
            "A": {0: 0.5 * hours_per_shift * np.ones(shape=(mat_shape, num_shifts), dtype=np.float64)},
            "B": {1: 0.5 * hours_per_shift * np.ones(shape=(mat_shape, num_shifts), dtype=np.float64)}}
        storages_to_equipment["A"][0][0:3, :] = 0.5 / 3 * hours_per_shift
        storages_to_equipment["A"][0][3:5, :] = 0.5 / 2 * hours_per_shift
        storages_to_equipment["B"][1][0:3, :] = 0.5 / 3 * hours_per_shift
        storages_to_equipment["B"][1][3:5, :] = 0.5 / 2 * hours_per_shift

        done_level = np.zeros(shape=(mat_shape, num_shifts + 1), dtype=np.float64)
        for mat in range(0, 3):
            done_level[mat, :] = [0.5 / 3 * hours_per_shift * idx for idx in range(num_shifts + 1)]
        for mat in range(3, 5):
            done_level[mat, :] = [0.5 / 2 * hours_per_shift * idx for idx in range(num_shifts + 1)]
        done_level[5, :] = [0.5 * hours_per_shift * idx for idx in range(num_shifts + 1)]

        storage_levels = {"A": 0.5 * np.ones(shape=(mat_shape, num_shifts + 1), dtype=np.float64),
                          "B": 0.5 * np.ones(shape=(mat_shape, num_shifts + 1), dtype=np.float64), "DONE": done_level}
        # large storage capacity, evenly distributed material content
        storage_levels["A"][0:3, :] = 0.5 / 3
        storage_levels["A"][3:5, :] = 0.5 / 2
        storage_levels["B"][0:3, :] = 0.5 / 3
        storage_levels["B"][3:5, :] = 0.5 / 2

        allocator = ShiftAllocator(site, structure, shifts, plant_availabilities, storage_levels, equipment_to_storages, storages_to_equipment, rand_seed=42)
        result, levels = allocator.run()
        assert all(proc in result.production_sub_targets for proc in processes), f"Process missing in allocator result: {next(proc for proc in processes if proc not in result.production_sub_targets)}"
        proc0_targets: list[ProductionTargets] = result.production_sub_targets[processes[0]]
        storage_levels2: dict[str, list[float]] = { stg: [level_dict[stg].filling_level for level_dict in levels if stg in level_dict] for stg in ("A", "B", "DONE")}
        negative_storage = next(((stg, lvl) for stg, lvl in storage_levels2.items() if any(l < 0 for l in lvl)), None)
        assert negative_storage is None, f"Storage with negative level found: {negative_storage}"
        active_shifts0 = [t for t in proc0_targets if 0 in t.target_weight and t.target_weight[0].total_weight >= 1e-4]
        active_count = len(active_shifts0)
        assert active_count < num_shifts, "All shifts allocated for process 0"
        assert active_count > 0, "No shifts allocated for process 0"
        for stg_levels in levels:
            assert all(stg in stg_levels for stg in ("A", "B", "DONE")), f"Storage missing in levels {stg_levels.keys()}"
            for stg, lvl in stg_levels.items():
                assert all(lv >= -1e-3 for mat, lv in lvl.material_levels.items()), (f"Negative storage level in storage "
                                                                                     f"{stg} for material {next((mat, lv) for mat, lv in lvl.material_levels.items() if lv < -1e-3)}")
                class1 = [lvl.material_levels[mat.id] for mat in mat_cats[0].classes]
                class2 = [lvl.material_levels[mat.id] for mat in mat_cats[1].classes]
                class1_sum = sum(class1)
                class2_sum = sum(class2)
                total = lvl.filling_level
                assert abs(total - class1_sum) < 0.1, f"Material category 0 values ({class1}) do not add up to total amount {total} for storage {stg}"
                assert abs(total - class2_sum) < 0.1, f"Material category 1 values ({class2}) do not add up to total amount {total} for storage {stg}"
                # some uncertainty must be allowed in the shift allocation
        total = levels[-1].get("DONE").filling_level
        assert abs(structure.total_production - total) < 4, f"Expected total production of {structure.total_production}, got {total}"

    def test_shift_allocation_does_not_lead_to_negative_storage_levels0(self):
        """
        A setup where at some point there is not enough material of type A in storage to fulfil the demand,
        therefore other material must be produced first.
        """
        processes = ["test_proc0", "test_proc1"]
        storages = [Storage(name_short="A", equipment=[0], capacity_weight=32),
                    Storage(name_short="B", equipment=[1], capacity_weight=32),
                    Storage(name_short="DONE", equipment=[])]
        # capacity: 24t/day
        plants = [Equipment(id=0, name_short="Plant0", process=processes[0], storage_in="A", storages_out=["B"], throughput_capacity=1),
                  Equipment(id=1, name_short="Plant1", process=processes[1], storage_in="B", storages_out=["DONE"], throughput_capacity=1), ]
        mat_cats = [
            MaterialCategory(id="cat0", classes=[
                                        MaterialClass(id="cat0_class0", category="cat0"),
                                        MaterialClass(id="cat0_class1", category="cat0"),
                                        MaterialClass(id="cat0_class2", category="cat0"),
            ]),
            MaterialCategory(id="cat1", classes=[
                                        MaterialClass(id="cat1_class0", category="cat1"),
                                        MaterialClass(id="cat1_class1", category="cat1"),
            ])
        ]
        site = Site(
            processes=[Process(name_short=process, process_ids=[idx]) for idx, process in enumerate(processes)],
            equipment=plants, storages=storages, material_categories=mat_cats
        )
        # 4 days of production, equipment capacity: 96t
        start = datetime(year=2026, month=5, day=1, tzinfo=timezone.utc)
        end = datetime(year=2026, month=5, day=5, tzinfo=timezone.utc)
        period = (start, end)
        # requires exactly half the capacity on average
        structure = LongTermTargets(period=period, total_production=48, production_targets={
            "cat0_class0": 16, "cat0_class1": 16, "cat0_class2": 16,
            "cat1_class0": 24, "cat1_class1": 24
        })
        """
        initial_storage_levels: dict[str, StorageLevel] = {
            "A": StorageLevel(storage="A", filling_level=0.5, timestamp=start, material_levels={
                "cat0_class0": 0.05, "cat0_class1": 0.05, "cat0_class2": 0.4,
                "cat1_class0": 0.05, "cat1_class1": 0.45
            }),
            "B": StorageLevel(storage="B", filling_level=0.5, timestamp=start, material_levels={
                "cat0_class0": 0.05, "cat0_class1": 0.2, "cat0_class2": 0.25,
                "cat1_class0": 0, "cat1_class1": 0.5
            })
        }
        """
        # four days, 12 shifts
        shifts: list[tuple[datetime, datetime]] = [(start + timedelta(hours=8 * idx), start + timedelta(hours=8 * (idx + 1))) for idx in range(12)]
        num_shifts = len(shifts)
        plant_availabilities: dict[int, EquipmentAvailability] = {p: EquipmentAvailability(equipment=p, period=period, daily_baseline=timedelta(days=1)) for p in (0, 1)}
        # need to start with a config that is valid but may easily lead to an invalid shift-adapted result
        # initial result: evenly distributed production, equipment operating at half capacity all the time
        mat_shape = sum(1 for cat in mat_cats for _ in cat.classes) + 1
        hours_per_shift = 8
        equipment_to_storages = {0: {"B": 0.5 * hours_per_shift * np.ones(shape=(mat_shape, num_shifts), dtype=np.float64)},
                                 1: {"DONE": 0.5 * hours_per_shift * np.ones(shape=(mat_shape, num_shifts), dtype=np.float64)}}
        # amounts per class
        equipment_to_storages[0]["B"][0:3, :] = 0.5 / 3 * hours_per_shift
        equipment_to_storages[0]["B"][3:5, :] = 0.5 / 2 * hours_per_shift
        equipment_to_storages[1]["DONE"][0:3, :] = 0.5 / 3 * hours_per_shift
        equipment_to_storages[1]["DONE"][3:5, :] = 0.5 / 2 * hours_per_shift
        storages_to_equipment = {"A": {0: 0.5 * hours_per_shift * np.ones(shape=(mat_shape, num_shifts), dtype=np.float64)},
                                 "B": {1: 0.5 * hours_per_shift * np.ones(shape=(mat_shape, num_shifts), dtype=np.float64)}}
        storages_to_equipment["A"][0][0:3, :] = 0.5 / 3 * hours_per_shift
        storages_to_equipment["A"][0][3:5, :] = 0.5 / 2 * hours_per_shift
        storages_to_equipment["B"][1][0:3, :] = 0.5 / 3 * hours_per_shift
        storages_to_equipment["B"][1][3:5, :] = 0.5 / 2 * hours_per_shift

        done_level = np.zeros(shape=(mat_shape, num_shifts + 1), dtype=np.float64)
        for mat in range(0, 3):
            done_level[mat, :] = [0.5 / 3 * hours_per_shift * idx for idx in range(num_shifts + 1)]
        for mat in range(3, 5):
            done_level[mat, :] = [0.5 / 2 * hours_per_shift * idx for idx in range(num_shifts + 1)]
        done_level[5, :] = [0.5 * hours_per_shift * idx for idx in range(num_shifts + 1)]

        storage_levels = {"A": 0.5 * np.ones(shape=(mat_shape, num_shifts + 1), dtype=np.float64),
                          "B": 0.5 * np.ones(shape=(mat_shape, num_shifts + 1), dtype=np.float64), "DONE": done_level}
        # storage capacity is 32, so a relative value of 0.05 corresponds to 1.6t => enough to support the initial flow of 1.33t per material per shift,
        # but not enough to support twice as much in a naive shift-allocated adaptation
        storage_levels["A"][0:2, :] = 0.05
        storage_levels["A"][3, :] = 0.4
        storage_levels["A"][3, :] = 0.05
        storage_levels["A"][4, :] = 0.45
        storage_levels["B"][0:2, :] = 0.05
        storage_levels["B"][3, :] = 0.4
        storage_levels["B"][3, :] = 0.05
        storage_levels["B"][4, :] = 0.45
        allocator = ShiftAllocator(site, structure, shifts, plant_availabilities, storage_levels, equipment_to_storages, storages_to_equipment, rand_seed=42)
        result, levels = allocator.run()
        assert all(proc in result.production_sub_targets for proc in
                   processes), f"Process missing in allocator result: {next(proc for proc in processes if proc not in result.production_sub_targets)}"
        proc0_targets: list[ProductionTargets] = result.production_sub_targets[processes[0]]
        storage_levels2: dict[str, list[float]] = {stg: [level_dict[stg].filling_level for level_dict in levels if stg in level_dict] for stg in ("A", "B", "DONE")}
        negative_storage = next((stg for stg, lvl in storage_levels2.items() if any(l < 0 for l in lvl)), None)
        assert negative_storage is None, f"Storage with negative level found: {negative_storage}"
        active_shifts0 = [t for t in proc0_targets if 0 in t.target_weight and t.target_weight[0].total_weight >= 1e-4]
        active_count = len(active_shifts0)
        #  print("Active shifts ", active_count)
        assert active_count < num_shifts, "All shifts allocated for process 0"
        assert active_count > 0, "No shifts allocated for process 0"
        final_done_level: StorageLevel = levels[-1].get("DONE")
        assert final_done_level is not None, "DONE storage missing"
        # print("FINAL content", final_done_level.filling_level, " material levels ", final_done_level.material_levels)
        class1 = [final_done_level.material_levels[mat.id] for mat in mat_cats[0].classes]
        class2 = [final_done_level.material_levels[mat.id] for mat in mat_cats[1].classes]
        class1_sum = sum(class1)
        class2_sum = sum(class2)
        total = final_done_level.filling_level
        assert abs(total - class1_sum) < 0.1, f"Material category 0 values ({class1}) do not add up to total amount {total}"
        assert abs(total - class2_sum) < 0.1, f"Material category 1 values ({class2}) do not add up to total amount {total}"
        # some uncertainty must be allowed in the shift allocation
        assert abs(structure.total_production - total) < 4, f"Expected total production of {structure.total_production}, got {total}"

    def test_shift_allocation_does_not_lead_to_negative_production0(self):
        """
        A setup where at some point negative production values might arise
        """
        process = "test_proc"
        storages = [Storage(name_short="A", equipment=[0], capacity_weight=100),
                    Storage(name_short="DONE", equipment=[])]
        # capacity: 24t/day
        plants = [Equipment(id=0, name_short="Plant0", process=process, storage_in="A", storages_out=["DONE"], throughput_capacity=1) ]
        mat_cats = [
            MaterialCategory(id="cat0", classes=[
                                        MaterialClass(id="cat0_class0", category="cat0"),
                                        MaterialClass(id="cat0_class1", category="cat0"),
                                        MaterialClass(id="cat0_class2", category="cat0"),
            ]),
            MaterialCategory(id="cat1", classes=[
                                        MaterialClass(id="cat1_class0", category="cat1"),
                                        MaterialClass(id="cat1_class1", category="cat1"),
            ])
        ]
        site = Site(
            processes=[Process(name_short=process, process_ids=[0])],
            equipment=plants, storages=storages, material_categories=mat_cats
        )
        # 1 days of production, equipment capacity: 24t
        start = datetime(year=2026, month=5, day=1, tzinfo=timezone.utc)
        end = datetime(year=2026, month=5, day=2, tzinfo=timezone.utc)
        period = (start, end)
        # requires exactly half the capacity on average
        structure = LongTermTargets(period=period, total_production=12, production_targets={
            "cat0_class0": 4, "cat0_class1": 4, "cat0_class2": 4,
            "cat1_class0": 6, "cat1_class1": 6
        })
        # 1 day, 3 shifts
        shifts: list[tuple[datetime, datetime]] = [(start + timedelta(hours=8 * idx), start + timedelta(hours=8 * (idx + 1))) for idx in range(3)]
        num_shifts = len(shifts)
        plant_availabilities: dict[int, EquipmentAvailability] = {0: EquipmentAvailability(equipment=0, period=period, daily_baseline=timedelta(days=1))}
        # need to start with a config that is valid but may easily lead to an invalid shift-adapted result
        # initial result: evenly distributed production, equipment operating at half capacity all the time
        mat_shape = sum(1 for cat in mat_cats for _ in cat.classes) + 1
        hours_per_shift = 8
        equipment_to_storages = {0: {"DONE": 0.5 * hours_per_shift * np.ones(shape=(mat_shape, num_shifts), dtype=np.float64)}}
        equipment_to_storages[0]["DONE"][3:5, :] = 0.5 / 2 * hours_per_shift
        # amounts per class; shift 0
        equipment_to_storages[0]["DONE"][0:3, 0] = 0.5 / 3 * hours_per_shift
        # shift 1
        equipment_to_storages[0]["DONE"][0, 1] = 0.     # do not schedule mat 0 at all in shift 1 => overall target will be negative, due to spillover from shift 0
        equipment_to_storages[0]["DONE"][1:3, 1] = 0.5 / 2 * hours_per_shift
        # shift 2 => compensate
        equipment_to_storages[0]["DONE"][0, 2] = 0.5 * 2/3 * hours_per_shift
        equipment_to_storages[0]["DONE"][1:3, 2] = 0.5 / 6 * hours_per_shift

        storages_to_equipment = {"A": {0: 0.5 * hours_per_shift * np.ones(shape=(mat_shape, num_shifts), dtype=np.float64)}}
        storages_to_equipment["A"][0][3:5, :] = 0.5 / 2 * hours_per_shift
        # shift 0
        storages_to_equipment["A"][0][0:3, 0] = 0.5 / 3 * hours_per_shift
        # shift 1
        storages_to_equipment["A"][0][0, 1] = 0.
        storages_to_equipment["A"][0][1:3, 1] = 0.5 / 2 * hours_per_shift
        # shift 2
        storages_to_equipment["A"][0][0, 1] = 0.5 * 2/3 * hours_per_shift
        storages_to_equipment["A"][0][1:3, 1] = 0.5 / 6 * hours_per_shift
        done_level = np.zeros(shape=(mat_shape, num_shifts + 1), dtype=np.float64)
        done_level[0, :] = (0., 0.5 / 3 * hours_per_shift, 0.5 / 3 * hours_per_shift, 0.5 * hours_per_shift)
        done_level[1, :] = (0., 0.5 / 3 * hours_per_shift, 0.5 * 5/6 * hours_per_shift, 0.5 * hours_per_shift)
        done_level[2, :] = (0., 0.5 / 3 * hours_per_shift, 0.5 * 5/6 * hours_per_shift, 0.5 * hours_per_shift)
        for mat in range(3, 5):
            done_level[mat, :] = [0.5 / 2 * hours_per_shift * idx for idx in range(num_shifts + 1)]
        done_level[5, :] = [0.5 * hours_per_shift * idx for idx in range(num_shifts + 1)]

        storage_levels = {"A": 0.5 * np.ones(shape=(mat_shape, num_shifts + 1), dtype=np.float64),
                          "DONE": done_level}
        allocator = ShiftAllocator(site, structure, shifts, plant_availabilities, storage_levels, equipment_to_storages, storages_to_equipment, rand_seed=42)
        result, levels = allocator.run()
        assert process in result.production_sub_targets, f"Process missing in allocator result: {process}"
        proc0_targets: list[ProductionTargets] = result.production_sub_targets[process]
        classes_cats1 = [cl.id for cl in mat_cats[0].classes]
        classes_cats2 = [cl.id for cl in mat_cats[1].classes]
        for idx, target in enumerate(proc0_targets):
            assert target.material_weights is not None, f"Material weights none in shift {idx}"
            assert 0 in target.target_weight, f"Equipment missing in target weights in shift {idx}"
            assert target.target_weight[0].total_weight >= 0, f"Total equipment production negative in shift {idx}: {target.target_weight[0].total_weight}"
            assert all(weight >= 0 for weight in target.material_weights.values()), \
                f"Negative production in shift {idx}  for material class: {next((mat, weight) for mat, weight in target.material_weights.items() if weight < 0)}"
            weight_cat1 = sum(weight for mat, weight in target.material_weights.items() if mat in classes_cats1)
            weight_cat2 = sum(weight for mat, weight in target.material_weights.items() if mat in classes_cats2)
            assert abs(weight_cat1-weight_cat2) < 1e-3, f"Different total material weight for categories 1 and 2: {weight_cat1}, {weight_cat2} in shift {idx}"

    def test_shift_allocation_does_not_lead_to_negative_production1(self):
        """
        A setup where at some point negative production values might arise
        """
        process = "test_proc"
        storages = [Storage(name_short="A", equipment=[0], capacity_weight=100),
                    Storage(name_short="DONE", equipment=[])]
        # capacity: 24t/day
        plants = [Equipment(id=0, name_short="Plant0", process=process, storage_in="A", storages_out=["DONE"], throughput_capacity=1) ]
        mat_cats = [
            MaterialCategory(id="cat0", classes=[
                                        MaterialClass(id="cat0_class0", category="cat0"),
                                        MaterialClass(id="cat0_class1", category="cat0"),
                                        MaterialClass(id="cat0_class2", category="cat0"),
            ]),
            MaterialCategory(id="cat1", classes=[
                                        MaterialClass(id="cat1_class0", category="cat1"),
                                        MaterialClass(id="cat1_class1", category="cat1"),
            ])
        ]
        site = Site(
            processes=[Process(name_short=process, process_ids=[0])],
            equipment=plants, storages=storages, material_categories=mat_cats
        )
        # 1 days of production, equipment capacity: 24t
        start = datetime(year=2026, month=5, day=1, tzinfo=timezone.utc)
        end = datetime(year=2026, month=5, day=2, tzinfo=timezone.utc)
        period = (start, end)
        # requires exactly half the capacity on average
        structure = LongTermTargets(period=period, total_production=12, production_targets={
            "cat0_class0": 4, "cat0_class1": 4, "cat0_class2": 4,
            "cat1_class0": 6, "cat1_class1": 6
        })
        # 1 day, 3 shifts
        shifts: list[tuple[datetime, datetime]] = [(start + timedelta(hours=8 * idx), start + timedelta(hours=8 * (idx + 1))) for idx in range(3)]
        num_shifts = len(shifts)
        plant_availabilities: dict[int, EquipmentAvailability] = {0: EquipmentAvailability(equipment=0, period=period, daily_baseline=timedelta(days=1))}
        # need to start with a config that is valid but may easily lead to an invalid shift-adapted result
        # initial result: evenly distributed production, equipment operating at half capacity all the time
        mat_shape = sum(1 for cat in mat_cats for _ in cat.classes) + 1
        hours_per_shift = 8
        equipment_to_storages = {0: {"DONE": np.ones(shape=(mat_shape, num_shifts), dtype=np.float64)}}
        # amounts per class; shift 0: half used
        equipment_to_storages[0]["DONE"][0:3, 0] = 0.5 / 3 * hours_per_shift
        equipment_to_storages[0]["DONE"][3:5, :] = 0.5 / 2 * hours_per_shift
        equipment_to_storages[0]["DONE"][5, 0] = 0.5 * hours_per_shift
        # shift 1 => full prod
        equipment_to_storages[0]["DONE"][0, 1] = 0.     # do not schedule mat 0 at all in shift 1 => overall target will be negative, due to spillover from shift 0
        equipment_to_storages[0]["DONE"][1:3, 1] = 1 / 2 * hours_per_shift
        equipment_to_storages[0]["DONE"][3:5, 1] = 1 / 2 * hours_per_shift
        equipment_to_storages[0]["DONE"][5, 1] = hours_per_shift
        # shift 2 => full prod
        equipment_to_storages[0]["DONE"][0, 2] = 2/3 * hours_per_shift
        equipment_to_storages[0]["DONE"][1:3, 2] = 1/6 * hours_per_shift
        equipment_to_storages[0]["DONE"][3:5, 2] = 1/2 * hours_per_shift
        equipment_to_storages[0]["DONE"][5, 2] = hours_per_shift

        storages_to_equipment = {"A": {0: hours_per_shift * np.ones(shape=(mat_shape, num_shifts), dtype=np.float64)}}
        # shift 0
        storages_to_equipment["A"][0][0:3, 0] = 0.5 / 3 * hours_per_shift
        storages_to_equipment["A"][0][3:5, 0] = 0.5 / 2 * hours_per_shift
        storages_to_equipment["A"][0][5, 0] = 0.5 * hours_per_shift
        # shift 1
        storages_to_equipment["A"][0][0, 1] = 0.
        storages_to_equipment["A"][0][1:3, 1] = 1 / 2 * hours_per_shift
        storages_to_equipment["A"][0][3:5, 1] = 1 / 2 * hours_per_shift
        storages_to_equipment["A"][0][5, 1] = hours_per_shift
        # shift 2
        storages_to_equipment["A"][0][0, 1] = 2/3 * hours_per_shift
        storages_to_equipment["A"][0][1:3, 1] = 1/6 * hours_per_shift
        storages_to_equipment["A"][0][3:5, 1] = 1/2 * hours_per_shift
        storages_to_equipment["A"][0][5, 1] = hours_per_shift

        done_level = np.zeros(shape=(mat_shape, num_shifts + 1), dtype=np.float64)
        done_level[0, :] = (0., 1/6 * hours_per_shift, 1/6 * hours_per_shift, 5/6 * hours_per_shift)
        done_level[1, :] = (0., 1/6 * hours_per_shift, 2/3 * hours_per_shift, 5/6 * hours_per_shift)
        done_level[2, :] = (0., 1/6 * hours_per_shift, 2/3 * hours_per_shift, 5/6 * hours_per_shift)
        for mat in range(3, 5):
            done_level[mat, :] = (0., 1/4 * hours_per_shift, 3/4 * hours_per_shift, 5/4 * hours_per_shift)
        done_level[5, :] = (0., 1/2 * hours_per_shift, 3/4 * hours_per_shift, 5/2 * hours_per_shift)

        storage_levels = {"A": 0.5 * np.ones(shape=(mat_shape, num_shifts + 1), dtype=np.float64),
                          "DONE": done_level}
        allocator = ShiftAllocator(site, structure, shifts, plant_availabilities, storage_levels, equipment_to_storages, storages_to_equipment, rand_seed=42)
        result, levels = allocator.run()
        assert process in result.production_sub_targets, f"Process missing in allocator result: {process}"
        proc0_targets: list[ProductionTargets] = result.production_sub_targets[process]
        classes_cats1 = [cl.id for cl in mat_cats[0].classes]
        classes_cats2 = [cl.id for cl in mat_cats[1].classes]
        for idx, target in enumerate(proc0_targets):
            assert target.material_weights is not None, f"Material weights none in shift {idx}"
            assert 0 in target.target_weight, f"Equipment missing in target weights in shift {idx}"
            assert target.target_weight[0].total_weight >= 0, f"Total equipment production negative in shift {idx}: {target.target_weight[0].total_weight}"
            assert all(weight >= 0 for weight in target.material_weights.values()), \
                f"Negative production in shift {idx} for material class: {next((mat, weight) for mat, weight in target.material_weights.items() if weight < 0)}"
            weight_cat1 = sum(weight for mat, weight in target.material_weights.items() if mat in classes_cats1)
            weight_cat2 = sum(weight for mat, weight in target.material_weights.items() if mat in classes_cats2)
            assert abs(weight_cat1-weight_cat2) < 1e-3, f"Different total material weight for categories 1 and 2: {weight_cat1}, {weight_cat2} in shift {idx}"