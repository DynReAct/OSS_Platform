from datetime import datetime
from typing import Sequence

from dynreact.base.NotApplicableException import NotApplicableException
from dynreact.base.ProductionHistoryReader import ProductionHistoryReader
from dynreact.base.model import Site, ProductionTargets, EquipmentProduction, MaterialClass, MaterialCategory


class DummyHistoryReader(ProductionHistoryReader):
    """
    Assumes equipment has always been running at full capacity
    """

    def __init__(self, url: str, site: Site):
        super().__init__(url, site)
        if not url.startswith("dummy:"):
            raise NotApplicableException(f"URL {url} not applicable to dummy history reader")

    @staticmethod
    def _share_for_material_class(cl: MaterialClass, cat: MaterialCategory) -> float:
        if cl.default_share is not None:
            return cl.default_share
        if cl.is_default:
            others = sum(DummyHistoryReader._share_for_material_class(cl2, cat) for cl2 in cat.classes if cl2 != cl)
            return max(1. - others, 0.)
        return 0.

    def production_aggregate(self, process: str, start: datetime, end: datetime, equipment: Sequence[int]|None=None, material_filter: Sequence[str]|None=None) -> ProductionTargets:
        equipment = equipment if equipment is not None else [e.id for e in self._site.get_process_equipment(process, do_raise=True)]
        duration_hours = (end-start).total_seconds()/3_600 if end > start else 0.
        default_capacity = 1.
        capacities = [self._site.get_equipment(e, do_raise=True).throughput_capacity or default_capacity for e in equipment]
        mat_cats = self._site.material_categories
        equipment_objects = [self._site.get_equipment(e, do_raise=True) for e in equipment]
        empty = tuple()
        total_material_weight: dict[str, float] = {}
        target_weight: dict[int, EquipmentProduction] = {}
        for e_idx, e in enumerate(equipment_objects):
            excluded_materials: Sequence[str] = e.material_constraints.excluded if e.material_constraints is not None else empty
            capacity = capacities[e_idx]
            if material_filter is not None:
                if all(mat in excluded_materials for mat in material_filter):
                    continue
                material_allowed = [mat for mat in material_filter if mat not in excluded_materials]
                filter_cat = next(cat for cat in mat_cats if any(cl.id == material_allowed[0] for cl in cat.classes))
                filter_shares = min(1, sum(DummyHistoryReader._share_for_material_class(cl, filter_cat) for cl in filter_cat.classes if cl.id in material_allowed))
                filter_missing = sum(DummyHistoryReader._share_for_material_class(cl, filter_cat) for cl in filter_cat.classes if cl.id in excluded_materials)
                if filter_missing > 0:
                    filter_shares = min(1., filter_shares / (1-filter_missing)) if filter_missing < 1-1e-4 else 0
                if filter_shares <= 0:
                    continue
                capacity = capacity * filter_shares   # This capacity reduction will also apply to other categories
                excluded_materials = list(excluded_materials) + [cl.id for cl in filter_cat.classes if cl.id not in material_filter and cl.id not in excluded_materials]
            all_materials: dict[str, float] = {}
            for cat in mat_cats:
                mat_excluded = [cl.id for cl in cat.classes if cl.id in excluded_materials]
                missing = sum(DummyHistoryReader._share_for_material_class(cl, cat) for cl in cat.classes if cl.id in mat_excluded)
                if missing >= 1 - 1e-4:
                    shares = {cl.id: 0 for cl in cat.classes if cl.id not in mat_excluded}
                else:
                    shares = {cl.id: DummyHistoryReader._share_for_material_class(cl, cat) * capacity * duration_hours/(1 - missing) for cl in cat.classes if cl.id not in mat_excluded}
                all_materials = all_materials | shares
            target_weight[e.id] = EquipmentProduction(equipment=e.id, total_weight=capacity * duration_hours, material_weights=all_materials)
            for mat, weight in all_materials.items():
                if mat not in total_material_weight:
                    total_material_weight[mat] = 0.
                total_material_weight[mat] += weight
        return ProductionTargets(process=process, period=(start, end), target_weight=target_weight, material_weights=total_material_weight)

