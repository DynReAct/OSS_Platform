import multiprocessing
import random
from copy import copy
from datetime import datetime
# https://stackoverflow.com/questions/75996502/module-multiprocessing-has-no-attribute-pool-error
import multiprocessing.pool
from typing import Any, Sequence

import networkx as nx
import numpy as np
from dynreact.base.CostProvider import CostProvider
from dynreact.base.LotsOptimizer import LotsOptimizationAlgo, LotsOptimizer, LotsOptimizationState
from dynreact.base.PlantPerformanceModel import PlantPerformanceModel, PerformanceEstimation
from dynreact.base.model import Snapshot, ProductionPlanning, ProductionTargets, Site, OrderAssignment, Order, \
    EquipmentStatus, Lot, Equipment, EquipmentProduction, ObjectiveFunction

from dynreact.lotcreation.TabuParams import TabuParams
import dynreact.lotcreation.LotCreationGoogleOR as lcor


class TabuSwap:

    def __init__(self, order: str, PlantFrom: int, PlantTo: int, Expiration: int=100):
        self.Order: str = order
        self.PlantFrom: int = PlantFrom
        self.PlantTo: int = PlantTo
        self.Expiration: int = Expiration

    def __eq__(self, value):
        return self.Order == value.Order and self.PlantFrom == value.PlantFrom and self.PlantTo == value.PlantTo

    def __hash__(self):
        return self.Order.__hash__() ^ self.PlantFrom.__hash__() ^ self.PlantTo.__hash__()

    def __str__(self):
        return "Order " + str(self.Order) + ": " + str(self.PlantFrom) + " -> " + str(self.PlantTo)


# TODO populate lot weight field
class TabuSearch(LotsOptimizer):

    def __init__(self, site: Site, process: str, costs: CostProvider, snapshot: Snapshot, targets: ProductionTargets,
                 initial_solution: ProductionPlanning, min_due_date: datetime|None = None,
                 # the next two are for initialization from a previous optimization run
                 best_solution: ProductionPlanning|None = None, history: list[ObjectiveFunction] | None = None,
                 parameters: dict[str, Any] | None = None,
                 performance_models: list[PlantPerformanceModel] | None = None,
                 orders_custom_priority: dict[str, int] | None = None,
                 forced_orders:  list[str]|None = None,
                 base_lots: list[Lot]|None = None
                 ):
        super().__init__(site, process, costs, snapshot, targets, initial_solution, min_due_date=min_due_date,
                         best_solution=best_solution, history=history, parameters=parameters, performance_models=performance_models,
                         orders_custom_priority=orders_custom_priority, forced_orders=forced_orders, base_lots=base_lots)
        self._params: TabuParams = TabuParams()
        self._performance_restrictions: list[PerformanceEstimation]|None = None
        self._forbidden_assignments: dict[str, list[int]] = {}
        self._orders_custom_priority = orders_custom_priority
        self._order_priorities = None if self._orders is None else {o.id: o.priority for o in self._orders.values()}
        if orders_custom_priority is not None:
            self._order_priorities.update(orders_custom_priority)
        self._allocator: LotsAllocator = LotsAllocator(process, {p.id: p for p in self._plants}, self._orders, self._snapshot, self._costs,
                                              self._targets, self._params, self._total_priority, self._forbidden_assignments, self._forced_orders, self._previous_orders,
                                              self._base_lots, self._base_lot_weights,  self._base_assignments, self._main_category,self._orders_custom_priority)

    def _init_performance_models(self, initial_plant_assignments: dict[str, int]) -> dict[str, int]:
        if self._performance_models is None or len(self._performance_models) == 0 or self._orders is None:
            return initial_plant_assignments
        changed: bool = False
        for plant in self._plant_ids:
            orders = [o for o in self._orders.values() if plant in o.allowed_equipment]
            restrictions: list[PerformanceEstimation] =  [performance for performances in (model.bulk_performance(plant, orders) for model in self._performance_models)
                                                          for performance in performances.results if performance.performance < 1]
            if restrictions is not None and len(restrictions) > 0:
                self._performance_restrictions = restrictions
                for restriction in (r for r in restrictions if r.performance < 0.3):  # ok?
                    if restriction.order not in self._forbidden_assignments:
                        self._forbidden_assignments[restriction.order] = []
                    self._forbidden_assignments[restriction.order].append(restriction.equipment)
                initial_forbidden: list[str] = [order for order, plants in self._forbidden_assignments.items() if
                                                initial_plant_assignments[order] in plants]
                if len(initial_forbidden) > 0:
                    changed = True
                for order in initial_forbidden:
                    initial_plant_assignments.pop(order)
        if changed:  # need to adapt optimization state
            best_is_current: bool = self._state.best_solution == self._state.current_solution
            new_assignments = {o: ass for o, ass in self._state.current_solution.order_assignments.items() if o in initial_plant_assignments}
            planning = self._costs.evaluate_order_assignments(self._process, new_assignments, targets=self._targets, snapshot=self._snapshot,
                                                            total_priority=self._total_priority, previous_orders=self._previous_orders)
            objective: ObjectiveFunction = self._costs.process_objective_function(planning)
            self._state.current_solution = planning
            self._state.current_object_value = objective
            if best_is_current:
                self._state.best_solution = planning
                self._state.best_objective_value = objective
        return initial_plant_assignments

    def run(self, max_iterations: int|None = None, debug: bool=False) -> LotsOptimizationState:
        initial_plant_assignments: dict[str, int] = {order: ass.equipment for order, ass in self._state.current_solution.order_assignments.items()}
        has_missing_forced_orders = False
        if self._forced_orders is not None:
            missing = [o for o in self._forced_orders if initial_plant_assignments.get(o, -1) < 0]
            has_missing_forced_orders = len(missing) > 0
            for o in missing:
                order = self._orders.get(o)
                equipment = [e for e in order.allowed_equipment if e in self._plant_ids]
                if len(equipment) > 0:
                    initial_plant_assignments[o] = equipment[0]
        initial_plant_assignments = self._init_performance_models(initial_plant_assignments)
        TabuList: set[TabuSwap] = set()
        ntotal: int = max_iterations if max_iterations is not None else self._params.ntotal
        ilots = np.zeros(ntotal)
        idelta = np.zeros(ntotal)
        iTarget = np.zeros(ntotal)
        iSwaps = []
        mini = -1
        MinCount = 0
        niter = 0
        tlo = []
        pool = multiprocessing.Pool() if self._params.NParallel > 1 else None

        #vbest: ProductionPlanning = self._state.current_solution
        #target_vbest: float = self._state.current_object_value
        if self._base_lots is not None:  # append to existing lots
            initial_plant_assignments = {orders: plant for orders, plant in initial_plant_assignments.items() if orders not in self._base_assignments}
        vbest: ProductionPlanning = self._allocator.optimize_lots(initial_plant_assignments)
        total_priority = vbest.total_priority
        target_vbest0: ObjectiveFunction = self._costs.process_objective_function(vbest)
        target_vbest: float = target_vbest0.total_value
        self._state.current_solution = vbest
        self._state.current_object_value = target_vbest0
        if target_vbest != self._state.history[-1].total_value:
            self._state.history.append(target_vbest0)
        vbest_global: ProductionPlanning = self._state.best_solution
        target_vbest_global: float = self._state.best_objective_value.total_value
        if target_vbest < target_vbest_global or has_missing_forced_orders:
            vbest_global = vbest
            target_vbest_global = target_vbest
            self._state.best_solution = vbest
            self._state.best_objective_value = target_vbest0
        interrupted: bool = False
        for listener in self._listeners:
            listener.update_solution(self._state.current_solution, self._state.current_object_value)
            if not listener.update_iteration(niter, vbest.get_num_lots(), self._state.current_object_value):
                interrupted = True
        while niter < ntotal and not interrupted:
            # planning: ProductionPlanning = self._costs.evaluate_order_assignments(self._process, s_best, self._targets, self._snapshot)
            # target_vbest = FTarget(vbest, self.PDict, self.params)
            # target_vbest = self._costs.process_objective_function(vbest)
            if target_vbest == self._costs.optimum_possible_costs(self._process, len(vbest.equipment_status.keys())):
                self._state.current_solution = vbest
                self._state.best_solution = vbest
                self._state.current_object_value = target_vbest0
                self._state.best_objective_value = target_vbest0
                if target_vbest != self._state.history[-1].total_value:
                    self._state.history.append(target_vbest0)
                # optimal solution found
                break
            next_step: tuple[TabuSwap, ProductionPlanning, ObjectiveFunction] = self.FindNextStep(self._state.current_solution, TabuList, pool)
            if next_step is None or next_step[0] is None:
                # continue  # TODO what's the point of continuing... nothing will change in the next iteration?
                break
            swp: TabuSwap = next_step[0]
            next_solution: ProductionPlanning = next_step[1]
            #swp: TabuSwap = next_step[0]
            #ssol: ProductionPlanning = next_step[1]
            #sval: float = next_step[1]
            #
            #nlots = sum(map(lambda s: s.NLots if s is not None else 0, sval.values()))
            nlots: int = next_solution.get_num_lots()
            # Note: this is use case specific, but we do not really need it here
            # delta = sum(map(lambda s: s[1].DeltaW if s[1] is not None else s[0].WTarget, sval.items()))
            #target_sval = FTarget(sval, self.PDict, self._params)
            target_sval0 = next_step[2]
            target_sval = target_sval0.total_value
            if target_sval < target_vbest:
                vbest = next_solution
                mini = niter
                target_vbest0 = target_sval0
                target_vbest = target_sval
                self._state.current_solution = vbest
                self._state.current_object_value = target_sval0
                self._state.history.append(target_sval0)
                if target_sval < target_vbest_global:
                    self._state.best_solution = vbest
                    self._state.best_objective_value = target_sval0
                    target_vbest_global = target_vbest
                    vbest_global = vbest
                    #if self._params.InstantSaveMinimum:
                    #    print("Minimum saving not implemented!!!!")
                        #FormatUtils.solution_to_xls(
                        #    GetFileName("Lots_" + str(mini) + "_", "xlsx", vbest_global, self.PDict, self.params), self.sol,
                        #    PSDict,
                        #    SnapshotDto(PDict=self.PDict, ODict=self.ODict, PM=self.PM, LM=self.LM, OCt=self.OCt))
            elif MinCount <= self._params.NMinUntilShuffle:  #
                self._state.current_solution = next_solution
                self._state.current_object_value = target_sval0
                self._state.history.append(target_sval0)
                MinCount += 1
            else:  # we haven't improved over the previous best value in a while, so reshuffle
                MinCount = 0
                # perform random shuffle of orders with high swap probability
                rdswap = random.random()

                lots: dict[int, list[Lot]] = self._state.current_solution.get_lots()
                swap_probabilities: dict[str, float] = {lot.id: 1/len(lot.orders) for lots_list in lots.values() for lot in lots_list}
                order_plant_assignment = {ass.order: ass.equipment for ass in self._state.current_solution.order_assignments.values()}
                for assignment in self._state.current_solution.order_assignments.values():
                    order = self._orders.get(assignment.order)
                    if self._forced_orders is not None and assignment.order in self._forced_orders:
                        continue
                    swap_probability: float = swap_probabilities[assignment.lot] if assignment.lot in swap_probabilities else 1
                    if order is not None and self._order_priorities[order.id] > 0:  # either order priority or custom priority
                        swap_probability = swap_probability / (self._order_priorities[order.id] + 0.5)
                    if swap_probability < rdswap:
                        continue
                    pto = -1
                    TabuList.add(TabuSwap(assignment.order, assignment.equipment, pto, self._params.Expiration))  # add shuffle to tabu list to enable new solutions
                    order_plant_assignment[assignment.order] = pto
                if self._base_lots is not None:  # append to existing lots
                    for order in self._base_assignments.keys():
                        if order in order_plant_assignment:
                            order_plant_assignment.pop(order)
                new_planning: ProductionPlanning = self._allocator.optimize_lots(order_plant_assignment)
                nlots = new_planning.get_num_lots()
                vbest = new_planning
                target_vbest0 = self._costs.process_objective_function(new_planning)
                target_vbest = target_vbest0.total_value  # or target_sval?
                self._state.current_solution = vbest
                self._state.current_object_value = target_vbest0
                self._state.history.append(target_vbest0)
                target_sval = target_vbest
            ilots[niter] = nlots
            # idelta[niter] = delta
            iTarget[niter] = target_sval
            iSwaps.append(swp)

            #iLC = sum(map(lambda x: x.LC, filter(lambda p: p is not None, PSDict.values())))
            #iNCaps = sum(map(lambda x: x.NCaps, filter(lambda p: p is not None, PSDict.values())))
            #iNCDiam = sum(map(lambda x: x.NCDiam, filter(lambda p: p is not None, PSDict.values())))
            #iClottot = sum(map(lambda x: x.Clottot, filter(lambda p: p is not None, PSDict.values())))
            #print(str(niter) + "th iteration: nlots: " + str(nlots) + ", delta: " + str(delta) + ", LC: " + str(
            #    iLC) + ", NCaps: " + str(iNCaps) + ", NCDiam: " + str(iNCDiam) + ", CLotTot: " + str(
            #    iClottot) + ", FTarget: " + str(iTarget[niter]) + ", Swap: " + str(swp))
            if debug:
                print(niter, "th iteration: nlots:", nlots, ", target value: ", target_sval, ", swap:", swp)

            for listener in self._listeners:
                listener.update_solution(self._state.current_solution, self._state.current_object_value)
                if not listener.update_iteration(niter, nlots, self._state.current_object_value):
                    interrupted = True
                #listener.UpdateSolution(self.sol, PSDict, self.PM, self.LM, self.ODict, self.PDict, self.OCt)
                #if not listener.UpdateIteration(niter, nlots, delta, iLC, iNCaps, iNCDiam, iClottot, iTarget[niter],
                #                                swp):
                #    do_break = True
            niter += 1

        if pool is not None:
            pool.close()
            pool.join()
            pool.terminate()

        if target_vbest < target_vbest_global:
            self._state.current_solution = vbest
            self._state.best_solution = vbest
            self._state.current_object_value = target_vbest0
            self._state.history.append(target_vbest0)
            self._state.best_objective_value = target_vbest0

        for listener in self._listeners:
            listener._completed()

        #if threading.current_thread() is threading.main_thread():  # ?
        #    plt.plot(range(niter), iTarget[0:niter])
        #    plt.savefig(GetFileName("Lots_", "png", vbest_global, self.PDict, self.params))
        return copy(self._state)

    def FindNextStep(self, planning: ProductionPlanning, TabuList: set[Any], pool: multiprocessing.pool.Pool|None) -> tuple[TabuSwap, ProductionPlanning, ObjectiveFunction]:
        # sl1 = list(sol.values())  # order plant assignments
        sl1: list[OrderAssignment] = [ass for ass in planning.order_assignments.values()]
        if self._base_lots is not None:  # do not optimize the fixed orders
            sl1 = [ass for ass in sl1 if ass.order not in self._base_assignments]
            planning = planning.model_copy(deep=True)
            planning.order_assignments = {o: ass for o, ass in planning.order_assignments.items() if o not in self._base_assignments}

        # slp = [[sl1[i] for i in range(len(sl1)) if (i % self.params.NParallel) == r] for r in range(self.params.NParallel)]
        slp: list[list[OrderAssignment]] = [[sl1[i] for i in range(len(sl1)) if (i % self._params.NParallel) == r] for r in range(self._params.NParallel)]
        # slist: list[OrderAssignment], TabuList: set[Any], tabu_search: LotsAllocator, planning: ProductionPlanning
        items = [CTabuWorker(sl, TabuList, self._allocator, planning) for sl in slp]
        solutions: list[tuple[TabuSwap, ProductionPlanning, ObjectiveFunction]] = []

        # parallel tabu search loop
        if self._params.NParallel > 1:
            for result in pool.imap(BestN, items):
                solutions.append(result)
        else:  # serial tabu search loop
            solutions.append(items[0].BestN())

        swpbest: TabuSwap = None
        best_solution: ProductionPlanning = None
        objective_value = ObjectiveFunction(total_value=float("inf"))

        for item in solutions:
            if item[2].total_value < objective_value.total_value:
                objective_value = item[2]
                swpbest = item[0]
                best_solution = item[1]

        if swpbest is None:
            return None, None, None

        for tli in TabuList:
            tli.Expiration -= 1

        TabuList.intersection_update(set(filter(lambda tli: tli.Expiration > 0, TabuList)))
        TabuList.add(TabuSwap(swpbest.Order, swpbest.PlantFrom, swpbest.PlantTo, self._params.Expiration))  # add also swap to prevent cycles
        TabuList.add(TabuSwap(swpbest.Order, swpbest.PlantTo, swpbest.PlantFrom, self._params.Expiration))

        #if self._base_lots is not None:  # might not be necessary => to be checked
        #    new_assignments = self._base_assignments.copy()
        #    new_assignments.update(best_solution.order_assignments)
        #    best_solution = self._costs.evaluate_order_assignments(self._process, new_assignments, self._targets, self._snapshot,
        #                                            orders_custom_priority=self._orders_custom_priority)  # total priority  ?
        #    objective_value = self._costs.process_objective_function(best_solution)
        return swpbest, best_solution, objective_value

    def update_transition_costs(self, plant: Equipment, current: Order, next: Order, status: EquipmentStatus, snapshot: Snapshot,
                                current_material: Any | None = None, next_material: Any | None = None,
                                orders_custom_priority: dict[str, int] | None = None) -> tuple[EquipmentStatus, ObjectiveFunction]:
        new_lot: bool = self._allocator.create_new_lot(plant, current, next, current_material=current_material, next_material=next_material)
        return self._costs.update_transition_costs(plant, current, next, status, snapshot, new_lot, current_material=current_material,
                                                   next_material=next_material, orders_custom_priority=orders_custom_priority)

    def assign_lots(self, order_plant_assignments: dict[str, int]) -> dict[int, list[Lot]]:
        return self._allocator.assign_lots(order_plant_assignments)


class LotsAllocator:
    """
    The functionality of this class has been moved out of TabuOptimizer so that it can be passed to the worker, instead
    of the full optimizer instance. In particular, this avoids having to pickle the user-defined listeners, which often fails.
    """

    def __init__(self, process: str, plants: dict[int, Equipment], orders: dict[str, Order]|None, snapshot: Snapshot, costs: CostProvider,
                    targets: ProductionTargets, params: TabuParams, total_priority: int|None, forbidden_assignments: dict[str, list[int]],
                    forced_orders: list[str]|None, previous_orders: dict[int, str]|None, base_lots: dict[int, Lot]|None, base_lot_weights: dict[int, float]|None,
                    base_assignments: dict[str, OrderAssignment]|None, main_category: str|None, orders_custom_priority: dict[str, int] | None):
        self._process = process
        self._plants = plants
        self._orders = orders
        self._snapshot = snapshot
        self._costs = costs
        self._targets = targets
        self._params = params
        self._forbidden_assignments = forbidden_assignments
        self._total_priority = total_priority
        self._forced_orders = forced_orders
        self._previous_orders = previous_orders
        self._base_lots = base_lots
        self._base_lot_weights = base_lot_weights
        self._base_assignments = base_assignments
        self._main_category = main_category
        self._orders_custom_priority = orders_custom_priority

    # previously: CalcSolution (although it also determined the PlantStatus objects)
    def assign_lots(self, order_plant_assignments: dict[str, int]) -> dict[int, list[Lot]]:
        # remember the plants involved here
        plant_ids: set[int] = set(order_plant_assignments.values())
        result: dict[int, list[Lot]] = {}
        global_costs = self._costs.path_dependent_costs(self._process)
        for plant_id in plant_ids:
            if plant_id < 0:
                continue
            order_ids: list[str] = [o for o, plant in order_plant_assignments.items() if plant == plant_id]
            orders: list[Order] = [self._orders[o] if self._orders is not None else self._snapshot.get_order(o, do_raise=True) for o in order_ids]
            lots: list[Lot] = self.assign_lots_googleor(plant_id, orders)
            if global_costs and len(orders) <= 50:
                new_order_ids: list[str] = [o for lot in lots for o in lot.orders]
                orders_by_id: dict[str, Order] = {o.id: o for o in orders}
                orders = [orders_by_id[o] for o in new_order_ids]
                # brute force ordering based on global costs;
                lots = self.assign_lots_bf(plant_id, orders)
            # if target lot sizes are prescribed and we end up above the limit, then we try to split lots
            targets = self._targets.target_weight.get(plant_id)
            if targets is not None and targets.lot_weight_range is not None:
                min_lot, max_lot = targets.lot_weight_range
                if max_lot is not None and max_lot > 0:
                    LotsAllocator._adapt_lot_sizes(lots, orders, min_lot, max_lot, plant_id, "LC" + self._plants[plant_id].name_short)
            result[plant_id] = lots

        if self._base_lots is not None:  # in this case we only want to extend the existing lots
            addon = {p: lots[0] for p, lots in result.items()}
            result = {p: [self._adapt_base_lots(lot, addon.get(p, None))] for p, lot in self._base_lots.items()}
        return result

    def assign_lots_bf(self, plant_id: int, orders: list[Order]) -> list[Lot]:
        # TODO better to reshuffle lots separately? At least if there are too many orders?
        plant = self._plants[plant_id]
        plant_targets = self._targets.target_weight.get(plant_id, EquipmentProduction(equipment=plant_id, total_weight=0))
        costs = self._costs
        dummy_lot = "LotDummy"
        transition_costs = np.array([[self._costs.transition_costs(plant, o1, o2) for o2 in orders] for o1 in orders])
        start_costs=None
        if self._previous_orders is not None and plant_id in self._previous_orders:
            prev_order: str = self._previous_orders.get(plant_id)
            prev_obj = self._orders[prev_order] if self._orders is not None else self._snapshot.get_order(prev_order, do_raise=True)
            start_costs = np.array([self._costs.transition_costs(plant, prev_obj, order) for order in orders])
            start_costs[np.isnan(start_costs)] = 50
        num_orders = len(orders)
        bound_factor = 0 if num_orders <= 5 else 1 if num_orders >= 15 else 0.25 + (num_orders - 5) / 10 * 0.75

        def global_costs(route: tuple[int, ...], trans_costs: float) -> float:   # TODO avoid recalculating transition costs?
            assignments = {orders[idx].id: OrderAssignment(equipment=plant_id, order=orders[idx].id, lot=dummy_lot, lot_idx=counter+1) for counter, idx in enumerate(route)}
            # TODO consider other keyword parameters
            status: EquipmentStatus = self._costs.evaluate_equipment_assignments(plant_targets, self._process, assignments, self._snapshot, self._targets.period,
                                                                    previous_order=self._previous_orders.get(plant_id) if self._previous_orders is not None else None)
            result = costs.objective_function(status).total_value
            return result


        from dynreact.lotcreation.global_tsp_bf import solve
        route, costs0 = solve(transition_costs, global_costs, start_costs=start_costs, bound_factor_upcoming_costs=bound_factor, time_limit=1)  # TODO time limit configurable?
        lot_count = 0
        lot_orders: list[Order] = []
        lots: list[Lot] = []
        last_order: Order | None = None
        for idx in route:
            order: Order = orders[idx]
            costs = 0 if last_order is None else self._costs.transition_costs(plant, last_order, order)
            if self.create_new_lot_costs_based(costs):
                lot: Lot = Lot(id="LC_" + plant.name_short + "." + f"{lot_count:02d}", equipment=plant_id, active=False,
                               status=1, orders=[o.id for o in lot_orders], weight=sum(o.actual_weight for o in lot_orders))
                lots.append(lot)
                lot_count += 1
                lot_orders = []
            lot_orders.append(order)
        if len(lot_orders) > 0:
            lots.append(Lot(id="LC_" + plant.name_short + "." + f"{lot_count:02d}", equipment=plant_id, active=False, status=1,
                    orders=[o.id for o in lot_orders], weight=sum(o.actual_weight for o in lot_orders)))
        return lots

    def assign_lots_googleor(self, plant_id: int, orders: list[Order]) -> list[Lot]:
        plant: Equipment = self._plants[plant_id]
        sz: int = len(orders)
        sTM = np.array(
            [[self._costs.transition_costs(plant, o1, o2) for o2 in orders] for o1 in orders]
        )
        sTM[np.isnan(sTM)] = self._params.CostNaN
        G = nx.DiGraph(sTM) if len(sTM) > 0 else nx.DiGraph()
        # connection order consideration
        sT0 = None
        if self._previous_orders is not None:
            prev_order: str = self._previous_orders.get(plant_id)
            if prev_order is not None:
                prev_obj = self._orders[prev_order] if self._orders is not None else self._snapshot.get_order(
                    prev_order, do_raise=True)
                sT0 = np.array([self._costs.transition_costs(plant, prev_obj, order) for order in orders])
                sT0[np.isnan(sT0)] = 50
        spath = lcor.path_converingOR(sTM, sT0)
        dict_subgraph = {}
        pos = 0
        sc = 0
        for i in range(sz - 1):
            if self.create_new_lot_costs_based(sTM[spath[i]][spath[i + 1]]):
                dict_subgraph[sc] = (nx.subgraph(G, spath[pos:i + 1]), spath[pos:i + 1])
                pos = i + 1
                sc += 1

        # last subpath
        dict_subgraph[sc] = (nx.subgraph(G, spath[pos:sz]), spath[pos:sz])

        # relabel graph nodes to orderIDs
        # sll = list(sl.keys()) # = order_ids
        # rlb = {i: sll[i] for i in range(sz)}
        rlb = {i: orders[i].id for i in range(sz)}
        dict_subgraph = {i: (nx.relabel_nodes(k[0], rlb), list(map(lambda x: rlb[x], k[1]))) for i, k in
                         dict_subgraph.items()}
        # assign solution element to lot
        lots: list[Lot] = []

        for idx, g in enumerate(dict_subgraph.values()):
            # for oid in g[1]: sol[oid].Lot = g
            # TODO status?
            # prepend LC_ to distinguish generated lots from pre-existing ones
            lot: Lot = Lot(id="LC_" + plant.name_short + "." + f"{idx:02d}", equipment=plant_id, active=False,
                           status=1, orders=g[1])
            lots.append(lot)
        return lots
        # due_dates = [o.due_date for o in orders if o.due_date is not None]
        # mdate = datetime(1, 1, 1) if len(due_dates) == 0 else min(due_dates)
        # cclottot = sum([sTM[spath[i]][spath[i + 1]] for i in range(sz - 1)])
        # handle setup coils
        # if sz > 0 and sT0 is not None: cclottot += sT0[spath[0]]

        # sval = SolutionValue(
        #    len(dict_subgraph),
        #    abs(p.WTarget - sum(map(lambda s: s.Order.Weight, sl.values()))),
        #    mdate,
        #    len(sl),
        #    dict_subgraph,
        #    sum(map(lambda sli: min(map(lambda pi: LM[p.ID][pi], sli.Order.CPlants)) if len(
        #        sli.Order.CPlants) > 0 else 0, sl.values())),
        #    CTabuSearch.CountCaps(dict_subgraph, sl),
        #    cclottot,
        #    CTabuSearch.CountCDiam(dict_subgraph, sl)
        # )


    def _adapt_base_lots(self, base_lot: Lot, addition: Lot | None):
        if addition is None:
            return base_lot
        trans_costs = self.create_new_lot_costs_based(self._costs.transition_costs(self._plants[base_lot.equipment], self._orders[base_lot.orders[-1]], self._orders[addition.orders[0]]))
        if self.create_new_lot_costs_based(trans_costs):
            return base_lot
        max_lot = None
        targets = self._targets.target_weight.get(base_lot.equipment)
        if targets is not None and targets.lot_weight_range is not None:
            max_lot = targets.lot_weight_range[1]
        new_lot = base_lot.model_copy(deep=True)
        weight: float = self._base_lot_weights[base_lot.equipment]
        for order in addition.orders:
            if max_lot is not None:
                order_obj = self._orders[order]
                if weight + order_obj.actual_weight > max_lot:
                    break
                weight += order_obj.actual_weight
            new_lot.orders.append(order)
            new_lot.weight = weight
        return new_lot

    def create_new_lot(self, plant: Equipment, current: Order, next: Order, current_material: Any | None = None, next_material: Any | None = None) -> bool:
        costs = self._costs.transition_costs(plant, current, next, current_material=current_material, next_material=next_material)
        return self.create_new_lot_costs_based(costs)

    def create_new_lot_costs_based(self, transition_costs: float) -> bool:
        return transition_costs > self._params.TAllowed

    def optimize_lots(self, order_plant_assignments: dict[str, int]) -> ProductionPlanning:
        new_lots: dict[int, list[Lot]] = self.assign_lots(order_plant_assignments)
        new_assignments: dict[str, OrderAssignment] = {}
        for plant, lots in new_lots.items():
            for lot in lots:
                for lot_idx, order in enumerate(lot.orders):
                    new_assignments[order] = OrderAssignment(equipment=plant, order=order, lot=lot.id, lot_idx=lot_idx+1)
        new_planning: ProductionPlanning = self._costs.evaluate_order_assignments(self._process, new_assignments, self._targets, self._snapshot,
                                                        total_priority=self._total_priority, previous_orders=self._previous_orders)
        for order, plant in order_plant_assignments.items():
            if plant < 0:
                new_planning.order_assignments[order] = OrderAssignment(equipment=-1, order=order, lot="", lot_idx=-1)
        return new_planning

    @staticmethod
    def _adapt_lot_sizes(lots: list[Lot], orders: list[Order], min_lot: float, max_lot: float, plant_id: int, lot_prefix: str):
        """Changes lots list in place"""
        lot_replacements: dict[int, list[Lot]] = {}
        for idx, lot in enumerate(lots):
            lot_orders = [o for o in orders if o.id in lot.orders]
            total_weight = sum(o.actual_weight for o in lot_orders)
            if total_weight > max_lot and abs(total_weight - max_lot) / max_lot > 0.02 and total_weight / 2 >= min_lot:
                new_sub_lots = []
                remaining_weight = total_weight
                sub_lot_weight = 0
                current_lot = []
                sub_lot_idx = 0
                for order_idx, order in enumerate(lot_orders):
                    current_weight = order.actual_weight
                    if sub_lot_weight + current_weight > max_lot and sub_lot_weight >= min_lot and sub_lot_weight > 0:
                        new_sub_lots.append(Lot(id=lot_prefix + "." + f"{idx + sub_lot_idx:02d}", orders=[o.id for o in current_lot],
                                equipment=plant_id, active=False, status=1))
                        sub_lot_idx += 1
                        current_lot = [order]
                        sub_lot_weight = current_weight
                    else:
                        sub_lot_weight += current_weight
                        current_lot.append(order)
                if len(current_lot) > 0:
                    new_sub_lots.append(Lot(id=lot_prefix + "." + f"{idx + sub_lot_idx:02d}", orders=[o.id for o in current_lot],
                            equipment=plant_id, active=False, status=1))
                if len(new_sub_lots) > 1:
                    for l_idx in range(idx + 1, len(lots)):  # rename remaining lots
                        other_lot = lots[l_idx]
                        other_lot.id = lot_prefix + "." + f"{l_idx + len(new_sub_lots) - 1:02d}"
                    lot_replacements[idx] = new_sub_lots
        if len(lot_replacements) > 0:
            for idx in reversed(list(lot_replacements.keys())):
                new_lots = lot_replacements[idx]
                lots.pop(idx)
                for l_idx, lot in enumerate(new_lots):
                    lots.insert(idx + l_idx, lot)


class TabuAlgorithm(LotsOptimizationAlgo):

    def __init__(self, site: Site):
        super().__init__(site)

    def _create_instance_internal(self, process: str, snapshot: Snapshot, targets: ProductionTargets,
                                  costs: CostProvider, initial_solution: ProductionPlanning, min_due_date: datetime|None = None,
                                  # the next two are for initialization from a previous optimization run
                                  best_solution: ProductionPlanning | None = None, history: list[ObjectiveFunction] | None = None,
                                  performance_models: list[PlantPerformanceModel] | None = None,
                                  parameters: dict[str, Any] | None = None,
                                  orders_custom_priority: dict[str, int] | None = None,
                                  forced_orders: list[str] | None = None,
                                  base_lots: dict[int, Lot] | None = None
                                  ) -> TabuSearch:
        return TabuSearch(self._site, process, costs, snapshot, targets, initial_solution=initial_solution, min_due_date=min_due_date,
                          best_solution=best_solution, history=history, parameters=parameters, performance_models=performance_models,
                          orders_custom_priority=orders_custom_priority, forced_orders=forced_orders, base_lots=base_lots)


class CTabuWorker:

    def __init__(self,  slist: list[OrderAssignment], TabuList: set[Any], tabu_search: LotsAllocator, planning: ProductionPlanning):
        self.slist: list[OrderAssignment] = slist
        self.TabuList: set[TabuSwap] = TabuList
        self.tabu_search: LotsAllocator = tabu_search
        self.planning: ProductionPlanning = planning  # the starting point

    def BestN(self) -> tuple[TabuSwap, ProductionPlanning, ObjectiveFunction]:
        order_ids = [ass.order for ass in self.slist]
        orders: dict[str, Order] = {oid: self.tabu_search._orders[oid] for oid in order_ids}
        plants: dict[int, Equipment] = self.tabu_search._plants
        params: TabuParams = self.tabu_search._params
        targets: ProductionTargets = self.tabu_search._targets
        costs: CostProvider = self.tabu_search._costs
        forced_orders = self.tabu_search._forced_orders
        snapshot = self.tabu_search._snapshot
        forbidden_assignments = self.tabu_search._forbidden_assignments
        is_lot_append: bool = self.tabu_search._base_lots is not None
        previous_orders: dict[int, str] | None = self.tabu_search._previous_orders
        planning = self.planning
        main_category: str|None = self.tabu_search._main_category
        orders_custom_priority: dict[str, int] | None = self.tabu_search._orders_custom_priority

        best_swap: TabuSwap = None
        best_solution: ProductionPlanning = None
        objective_value: float = float("inf")
        best_objective: ObjectiveFunction|None = None
        empty_plants = []
        track_structure: bool = targets.material_weights is not None
        for assignment in self.slist:
            order: Order = orders[assignment.order]
            forbidden_plants: list[int] = forbidden_assignments.get(order.id, empty_plants)
            # sl2 = list(map(lambda x: x[0], filter(lambda x: x[1], self.PM[swp1.Order.ID].items())))

            allowed_plants: list[int] = [p for p in order.allowed_equipment if p in plants and p not in forbidden_plants]
            if assignment.equipment >= 0 and (forced_orders is None or assignment.order not in forced_orders):
                allowed_plants.append(-1)
            if len(allowed_plants) == 0:
                continue
            # nbh = list(filter(lambda swp: swp not in self.TabuList and swp.PlantFrom != swp.PlantTo,
            #                      [TabuSwap(swp1.Order.ID, swp1.AssignedPlant, s, self.params.Expiration) for s in sl2]))
            swaps: Sequence[TabuSwap] = \
                (TabuSwap(assignment.order, assignment.equipment, new_plant, params.Expiration) for new_plant in allowed_plants if new_plant != assignment.equipment)
            swaps = (swap for swap in swaps if swap not in self.TabuList)
            for swp in swaps:

                order_assignments: dict[str, OrderAssignment] = planning.order_assignments
                # the tricky part in the new assignments is to get the order right... for each plant, orders should be sorted according to the lots, and unassigned orders should come last
                new_assignments: dict[str, OrderAssignment] = {key: ass for key, ass in planning.order_assignments.items() if
                                                ass.equipment >= 0 and ass.equipment != swp.PlantTo and ass.equipment != swp.PlantFrom}  # dict(self.planning.order_assignments)  # shallow copy
                affected_orders: list[str] = [o for o, ass in order_assignments.items() if ass.equipment >= 0 and (ass.equipment == swp.PlantFrom or ass.equipment == swp.PlantTo) and ass.order != swp.Order]

                plant_status: dict[int, EquipmentStatus] = dict(planning.equipment_status)  # shallow copy
                # reset plant solutions for swap
                assignments_for_lc = {o: order_assignments[o].equipment for o in affected_orders if order_assignments[o].equipment >= 0}
                if swp.PlantTo >= 0:
                    assignments_for_lc[swp.Order] = swp.PlantTo
                new_assigned_lots: dict[int, list[Lot]] = self.tabu_search.assign_lots(assignments_for_lc)
                if is_lot_append:  # expensive, only required if we are appending to existing lots
                    for plant, lots in new_assigned_lots.items():
                        for lot in lots:
                            for idx,o in enumerate(lot.orders):
                                new_assignments[o] = OrderAssignment(order=o, equipment=plant, lot=lot.id, lot_idx=idx+1)
                    for o, ass in order_assignments.items():
                        if o not in new_assignments:
                            new_assignments[o] = OrderAssignment(order=o, equipment=-1, lot="", lot_idx=-1)
                    for plant in list(plant_status.keys()):
                        equipment_targets = targets.target_weight.get(plant, EquipmentProduction(equipment=plant, total_weight=0.0))
                        start_order = previous_orders.get(plant) if previous_orders is not None else None
                        new_status: EquipmentStatus = costs.evaluate_equipment_assignments(equipment_targets, planning.process, new_assignments, snapshot, targets.period,
                                    track_structure=track_structure, main_category=main_category, orders_custom_priority=orders_custom_priority, previous_order=start_order)
                        plant_status[plant] = new_status
                else:
                    if swp.PlantFrom >= 0:
                        plant_status[swp.PlantFrom] = None
                        assigned_lots: list[Lot] = new_assigned_lots.get(swp.PlantFrom, [])
                        for lot in assigned_lots:
                            for idx, order_id in enumerate(lot.orders):
                                new_assignments[order_id] = OrderAssignment(equipment=swp.PlantFrom, order=order_id, lot=lot.id, lot_idx=idx+1)
                                if order_id != swp.Order and order_id in affected_orders:
                                    affected_orders.remove(order_id)
                        equipment_targets = targets.target_weight.get(swp.PlantFrom, EquipmentProduction(equipment=swp.PlantFrom, total_weight=0.0))
                        start_order = previous_orders.get(swp.PlantFrom) if previous_orders is not None else None
                        new_status: EquipmentStatus = costs.evaluate_equipment_assignments(equipment_targets, planning.process, new_assignments, snapshot, targets.period,
                                        track_structure=track_structure, main_category=main_category, orders_custom_priority=orders_custom_priority, previous_order =start_order)
                        plant_status[swp.PlantFrom] = new_status
                    if swp.PlantTo >= 0:
                        plant_status[swp.PlantTo] = None
                        assigned_lots: list[Lot] = new_assigned_lots.get(swp.PlantTo, [])
                        for lot in assigned_lots:
                            for idx, order_id in enumerate(lot.orders):
                                new_assignments[order_id] = OrderAssignment(equipment=swp.PlantTo, order=order_id, lot=lot.id, lot_idx=idx + 1)
                                if order_id != swp.Order and order_id in affected_orders:
                                    affected_orders.remove(order_id)
                        equipment_targets = targets.target_weight.get(swp.PlantTo, EquipmentProduction(equipment=swp.PlantTo, total_weight=0.0))
                        start_order = previous_orders.get(swp.PlantTo) if previous_orders is not None else None
                        new_status: EquipmentStatus = costs.evaluate_equipment_assignments(equipment_targets, planning.process,new_assignments, snapshot, targets.period,
                                       track_structure=track_structure, main_category=main_category, orders_custom_priority=orders_custom_priority, previous_order =start_order)
                        plant_status[swp.PlantTo] = new_status
                    # reappend unassigned
                    for order_id in affected_orders:
                        new_assignments[order_id] = OrderAssignment(order=order_id, equipment=-1, lot="", lot_idx=-1)
                    for order_id, ass in order_assignments.items():
                        if ass.equipment < 0 and order_id != swp.Order:
                            new_assignments[order_id] = ass
                if swp.Order not in new_assignments:
                    new_assignments[swp.Order] = OrderAssignment(order=swp.Order, equipment=-1, lot="", lot_idx=-1)
                if not is_lot_append:
                    assert len(new_assignments) == len(order_assignments), "Assignments missing"
                planning_candidate = ProductionPlanning(process=planning.process, order_assignments=new_assignments,
                                   equipment_status=plant_status, target_structure=targets.material_weights,
                                   total_priority=planning.total_priority,
                                    previous_orders=previous_orders)
                total_objectives = costs.process_objective_function(planning_candidate)
                #total_objectives = CostProvider.sum_objectives([self.costs.objective_function(status) for status in plant_status.values()])
                objective_fct = total_objectives.total_value
                if objective_fct < objective_value:
                    objective_value = objective_fct
                    best_objective = total_objectives
                    best_swap = swp
                    best_solution = planning_candidate
        if best_objective is None:
            best_objective = ObjectiveFunction(total_value=objective_value)
        return best_swap, best_solution, best_objective


# must be defined in global scope for being useable with pool.imap
def BestN(tw):
    return tw.BestN()

