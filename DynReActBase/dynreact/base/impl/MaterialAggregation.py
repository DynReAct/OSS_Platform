from dynreact.base.SnapshotProvider import SnapshotProvider
from dynreact.base.model import Site, Snapshot, Equipment, MaterialCategory, Order, MaterialClass


class MaterialAggregation:

    def __init__(self, site: Site, snaps: SnapshotProvider):
        self._site = site
        self._snaps = snaps
        self._categories: list[MaterialCategory] = site.material_categories

    def aggregate_categories_by_plant(self, snapshot: Snapshot, orders: list[Order]|None=None) -> dict[int, dict[str, dict[str, float]]] :
        """
        :param snapshot:
        :param orders:
        :return: aggregated material weight per plant, category and class
        """
        snaps = self._snaps
        plants: dict[int, Equipment] = {p.id: p for p in self._site.equipment}
        if orders is None:
            orders = snapshot.orders
        orders_by_id = {o.id: o for o in orders}
        # sort of cache; outer key: category, inner key: order id
        mat_class_for_order: dict[str, dict[str, MaterialClass]] = {cat.id: {} for cat in self._categories}
        # result; outer key: category, middle key: material class, inner key: plant id
        aggregate_weight: dict[int, dict[str, dict[str, float]]] = {p: {cat.id: {clz.id: 0 for clz in cat.classes} for cat in self._categories} for p in plants.keys()}
        for material in snapshot.material:
            order = orders_by_id.get(material.order)
            if order is None:
                continue
            plant = material.current_equipment
            if plant is None or plant not in plants:  # TODO?
                continue
            for category in self._categories:
                clz = mat_class_for_order[category.id].get(order.id)
                if clz is None:
                    clz = snaps.material_class_for_order(order, category)
                    mat_class_for_order[category.id][order.id] = clz
                    if clz is None:
                        continue
                aggregate_weight[plant][category.id][clz.id] += material.weight
        return aggregate_weight

    def aggregate_by_process(self, aggregation_by_plant: dict[int, dict[str, dict[str, float]]]):
        """
        :param snapshot:
        :return: aggregated material weight per process, category and class
        """
        processes = [p.name_short for p in self._site.processes]
        plants_by_process: dict[str, list[int]] = {proc: [p.id for p in self._site.get_process_equipment(proc)] for proc in processes}
        process_results: dict[str, dict[str, dict[str, float]]] = {}
        for proc in processes:
            plants: list[int] = plants_by_process[proc]
            new_agg: dict[str, dict[str, float]] = {}
            for plant in plants:
                results: dict[str, dict[str, float]] = aggregation_by_plant.get(plant)
                if results is None:
                    continue
                for cat, clz_dict in results.items():
                    if cat not in new_agg:
                        new_agg[cat] = {}
                    sub_results: dict[str, float] = new_agg[cat]
                    for clz, value in clz_dict.items():
                        if clz not in sub_results:
                            sub_results[clz] = value
                        else:
                            sub_results[clz] += value
            process_results[proc] = new_agg
        return process_results

    def aggregate_by_storage(self, aggregation_by_plant: dict[int, dict[str, dict[str, float]]]) -> dict[str, dict[str, dict[str, float]]]:
        """
        :param snapshot:
        :return: aggregated material weight per storage, category and class
        """
        storages: list[str] = [stg.name_short for stg in self._site.storages]
        plants_by_storage: dict[str, list[int]] = {stg: [p.id for p in self._site.equipment if p.storage_in == stg] for stg in storages}
        storage_results: dict[str, dict[str, dict[str, float]]] = {}
        for stg in storages:
            plants: list[int] = plants_by_storage[stg]
            new_agg: dict[str, dict[str, float]] = {}
            for plant in plants:
                results: dict[str, dict[str, float]] = aggregation_by_plant.get(plant)
                if results is None:
                    continue
                for cat, clz_dict in results.items():
                    if cat not in new_agg:
                        new_agg[cat] = {}
                    sub_results: dict[str, float] = new_agg[cat]
                    for clz, value in clz_dict.items():
                        if clz not in sub_results:
                            sub_results[clz] = value
                        else:
                            sub_results[clz] += value
            storage_results[stg] = new_agg
        return storage_results

    def aggregate(self, aggregation_by_plant: dict[int, dict[str, dict[str, float]]]) -> dict[str, dict[str, float]]:
        """
        Aggregate over all plants
        :param aggregation_by_plant:
        :return:
        """
        result: dict[str, dict[str, float]] = {}
        for plant_result in aggregation_by_plant.values():
            for cat, cat_result in plant_result.items():
                if cat not in result:
                    result[cat] = {}
                sub_result = result[cat]
                for clz, value in cat_result.items():
                    if clz not in sub_result:
                        sub_result[clz] = 0
                    sub_result[clz] += value
        return result
