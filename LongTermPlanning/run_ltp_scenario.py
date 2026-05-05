from dynreact.ltp2.LtpUtils import LtpUtils
from dynreact.ltp2.ShiftAllocator2 import ShiftAllocator2


def run_scenario():
    result = LtpUtils.load_results("ltp_result.json")
    # FIXME
    print(" RESULT loaded... now running shifts allocation")
    print("DE storage level", result.storage_levels.get("DE"))
    shifts_allocator = ShiftAllocator2(result.site, result.structure, result.shifts, result.availabilities,
                        result.storage_levels, result.equipment_to_storages, result.storages_to_equipment)
    mtp_results, storage_levels = shifts_allocator.run()
    print("DE final storage levels", [sl["DE"].filling_level for sl in storage_levels if "DE" in sl])
    sub_ts = mtp_results.production_sub_targets["TDS"]
    #print("  SUB target length", len(sub_ts), ", equipments ", set(key for st in sub_ts for key in st.target_weight.keys()))
    td1 = 2
    td2 = 31
    print("TD1 production", [st.target_weight[td1].total_weight for st in sub_ts if td1 in st.target_weight])
    print("TD2 production", [st.target_weight[td2].total_weight for st in sub_ts if td2 in st.target_weight])
    print("   MATeRIAL prod", [st.material_weights for st in sub_ts[:3]])

if __name__ == "__main__":
    run_scenario()
