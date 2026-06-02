from dynreact.base.model import ProductionTargets
from dynreact.ltp.LtpUtils import LtpUtils
from dynreact.ltp.ShiftAllocator import ShiftAllocator


def run_scenario():
    check_original_results: bool = False   # TODO script parameter
    result = LtpUtils.load_results("ltp_result.json")
    # FIXME
    print(" RESULT loaded... now running shifts allocation")
    shifts_allocator = ShiftAllocator(result.site, result.structure, result.shifts, result.availabilities,
                        result.storage_levels, result.equipment_to_storages, result.storages_to_equipment)  #, frozen_horizons=result.frozen_horizons)
    mtp_results, storage_levels = shifts_allocator.run(debug=True) if not check_original_results else \
                    LtpUtils.to_results(result.site, result.shifts, result.structure, result.storage_levels, result.storages_to_equipment, result.equipment_to_storages)
    # FIXME these are just the targets; more relevant:  done_storage = solution["storage_levels"][-1]["DONE"]["material_levels"]
    # print(f"Total prod {mtp_results.total_production}, materials: {mtp_results.production_targets}")
    done_storage = storage_levels[-1]["DONE"]
    by_cat = {}
    print("  TOTAL VALUE ", done_storage.filling_level)
    #print("  MATERIAL LEVELS", done_storage.material_levels)
    for cat in result.site.material_categories:
        cat_mats = [cl.id for cl in cat.classes]
        by_cat[cat.id] = sum(val for mat, val in done_storage.material_levels.items() if mat in cat_mats)
    print("  MAT LEVELS by cat ", by_cat)

    # check storage levels
    last_storages = storage_levels[-1]
    for stg in result.site.storages:
        if stg.name_short not in last_storages:
            continue
        levels = last_storages[stg.name_short]
        by_cat = {}
        for cat in result.site.material_categories:
            cat_mats = [cl.id for cl in cat.classes]
            by_cat[cat.id] = sum(val for mat, val in levels.material_levels.items() if mat in cat_mats)
        print(f"   - STG {stg.name_short}, level {levels.filling_level:.2f}, materials ", {mat: f"{l:.2f}" for mat, l in by_cat.items()})

    # check flows/equipment production
    proc = result.site.processes[4].name_short   # errors for 4, 5, final flow!
    targets = mtp_results.production_sub_targets[proc]
    last_target: ProductionTargets = targets[-1]
    total_flow_last = sum(t.total_weight for t in last_target.target_weight.values())
    by_cat = {}
    for cat in result.site.material_categories:
        cat_mats = [cl.id for cl in cat.classes]
        by_cat[cat.id] = sum(val for mat, val in last_target.material_weights.items() if mat in cat_mats)
    print(f"  TOTAL final flow for proc {proc}: {total_flow_last}, mat flows", {mat: f"{flow:.2f}" for mat, flow in by_cat.items()})





if __name__ == "__main__":
    run_scenario()
