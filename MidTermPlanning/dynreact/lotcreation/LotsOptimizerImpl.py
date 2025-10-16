import multiprocessing
# https://stackoverflow.com/questions/75996502/module-multiprocessing-has-no-attribute-pool-error
import multiprocessing.pool
import random
from copy import copy
from datetime import datetime
from typing import Any, Sequence

import networkx as nx
import numpy as np
import numpy.typing as npt

import dynreact.lotcreation.LotCreationGoogleOR as lcor
from dynreact.base.CostProvider import CostProvider
from dynreact.base.LotsOptimizer import LotsOptimizationAlgo, LotsOptimizer, LotsOptimizationState
from dynreact.base.PlantPerformanceModel import PlantPerformanceModel, PerformanceEstimation
from dynreact.base.model import Snapshot, ProductionPlanning, ProductionTargets, Site, OrderAssignment, Order, \
    EquipmentStatus, Lot, Equipment, EquipmentProduction, ObjectiveFunction
from dynreact.lotcreation.TabuParams import TabuParams
from dynreact.lotcreation.globaltsp import GlobalTspInput
from dynreact.lotcreation.globaltsp.BranchAndBoundWithEnsembleInput2 import GlobalSearchDefault
from dynreact.lotcreation.globaltsp.GlobalSearchBranchBound import GlobalSearchBB
from dynreact.lotcreation.globaltsp.GoogleOrSolver import GoogleOrSolver


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
        self._initialized: bool = False
        self._tabu_list: set[TabuSwap] = set()
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

    def run(self, max_iterations: int|None = None, debug: bool=False, continued: bool=False) -> LotsOptimizationState:
        niter = 0
        ntotal: int = max_iterations if max_iterations is not None else self._params.ntotal
        interrupted: bool = False
        continued = continued and self._initialized
        if continued:
            vbest: ProductionPlanning = self._state.current_solution
            target_vbest0: ObjectiveFunction = self._state.current_object_value
            target_vbest: float = target_vbest0.total_value
            vbest_global: ProductionPlanning = self._state.best_solution
            target_vbest_global: float = self._state.best_objective_value.total_value
        else:
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
            #vbest: ProductionPlanning = self._state.current_solution
            #target_vbest: float = self._state.current_object_value
            if self._base_lots is not None:  # append to existing lots
                initial_plant_assignments = {orders: plant for orders, plant in initial_plant_assignments.items() if orders not in self._base_assignments}
            vbest = self._allocator.optimize_lots(initial_plant_assignments)
            target_vbest0 = self._costs.process_objective_function(vbest)
            target_vbest = target_vbest0.total_value
            self._state.current_solution = vbest
            self._state.current_object_value = target_vbest0
            if target_vbest != self._state.history[-1].total_value:
                self._state.history.append(target_vbest0)
            vbest_global = self._state.best_solution
            target_vbest_global = self._state.best_objective_value.total_value
            if target_vbest < target_vbest_global or has_missing_forced_orders:
                vbest_global = vbest
                target_vbest_global = target_vbest
                self._state.best_solution = vbest
                self._state.best_objective_value = target_vbest0
            for listener in self._listeners:
                listener.update_solution(self._state.current_solution, self._state.current_object_value)
                if not listener.update_iteration(niter, vbest.get_num_lots(), self._state.current_object_value):
                    interrupted = True
            self._initialized = True
        total_priority = vbest.total_priority
        pool = multiprocessing.Pool() if self._params.NParallel > 1 else None
        worker_cnt: int = 0
        ilots = np.zeros(ntotal)
        # idelta = np.zeros(ntotal)
        iTarget = np.zeros(ntotal)
        iSwaps = []
        TabuList: set[TabuSwap] = self._tabu_list
        MinCount = 0
        iterations_without_shuffle: int = 0
        max_iterations_without_shuffle: int = int(ntotal/2) if ntotal >= 20 else ntotal
        rnd = random.Random(x=self._params.rand_seed)
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
            next_step: tuple[TabuSwap, ProductionPlanning, ObjectiveFunction] = self.FindNextStep(self._state.current_solution, TabuList, pool, worker_cnt)
            worker_cnt += self._params.NParallel
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
            iterations_without_shuffle += 1
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
            elif MinCount <= self._params.NMinUntilShuffle and iterations_without_shuffle < max_iterations_without_shuffle:  #
                self._state.current_solution = next_solution
                self._state.current_object_value = target_sval0
                self._state.history.append(target_sval0)
                MinCount += 1
            else:  # we haven't improved over the previous best value in a while, so reshuffle
                MinCount = 0
                iterations_without_shuffle = 0
                if max_iterations_without_shuffle >= 20:
                    max_iterations_without_shuffle = int(2*max_iterations_without_shuffle/3)
                # perform random shuffle of orders with high swap probability
                rdswap = rnd.random()

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

    def FindNextStep(self, planning: ProductionPlanning, TabuList: set[Any], pool: multiprocessing.pool.Pool|None, worker_cnt: int) -> tuple[TabuSwap, ProductionPlanning, ObjectiveFunction]:
        # sl1 = list(sol.values())  # order plant assignments
        sl1: list[OrderAssignment] = [ass for ass in planning.order_assignments.values()]
        if self._base_lots is not None:  # do not optimize the fixed orders
            sl1 = [ass for ass in sl1 if ass.order not in self._base_assignments]
            planning = planning.model_copy(deep=True)
            planning.order_assignments = {o: ass for o, ass in planning.order_assignments.items() if o not in self._base_assignments}

        # slp = [[sl1[i] for i in range(len(sl1)) if (i % self.params.NParallel) == r] for r in range(self.params.NParallel)]
        slp: list[list[OrderAssignment]] = [[sl1[i] for i in range(len(sl1)) if (i % self._params.NParallel) == r] for r in range(self._params.NParallel)]
        # slist: list[OrderAssignment], TabuList: set[Any], tabu_search: LotsAllocator, planning: ProductionPlanning
        rand_seeds = [self._params.rand_seed + worker_cnt + idx if self._params.rand_seed is not None else None for idx in range(len(slp))]
        items = [CTabuWorker(sl, TabuList, self._allocator, planning, self._params.max_tsps_per_worker, rand_seed=rand_seeds[idx]) for idx, sl in enumerate(slp)]
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
        return self._allocator.assign_lots(order_plant_assignments)[0]


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
    def assign_lots(self, order_plant_assignments: dict[str, int], timeout: float|None=None, pre_timeout: int|None=None) -> tuple[dict[int, list[Lot]], bool]:
        """Returns lots plus information if the algo ran into a timeout"""
        # remember the plants involved here
        plant_ids: set[int] = set(order_plant_assignments.values())
        result: dict[int, list[Lot]] = {}
        tsp_method = self._params.tsp_solver_global_costs
        global_costs = self._costs.path_dependent_costs(self._process)
        # solver = GlobalSearchDefault(bound_factor_upcoming_costs=0.5, timeout_pre_solvers=1) if global_costs else GoogleOrSolver()  # TODO parameters TODO option to use other solvers?
        timed_out: bool = False
        for plant_id in plant_ids:
            if plant_id < 0:
                continue
            order_ids: list[str] = [o for o, plant in order_plant_assignments.items() if plant == plant_id]
            orders: list[Order] = [self._orders[o] if self._orders is not None else self._snapshot.get_order(o, do_raise=True) for o in order_ids]
            lots, timeout_hit = self.assign_lots_internal(plant_id, orders, global_costs, self._snapshot, bound_factor=self._params.tsp_solver_global_bound_factor,
                                      timeout=timeout if timeout is not None else self._params.tsp_solver_global_timeout,
                                      pre_timeout=pre_timeout, solver_id=self._params.tsp_solver_global_costs)
            if timeout_hit:
                timed_out = True
            #lots: list[Lot] = self.assign_lots_googleor(plant_id, orders) if "googleor" in tsp_method else self.assign_lots_bf(plant_id, orders, bound_factor=self._params.tsp_solver_global_bound_factor,
            #                               timeout=self._params.tsp_solver_global_bound_timeout, init_nearest_neighbours=self._params.tsp_solver_init_nearest_neighbours)
            #if global_costs and len(orders) <= 40 and tsp_method == "googleor_global1":
            #    new_order_ids: list[str] = [o for lot in lots for o in lot.orders]
            #    orders_by_id: dict[str, Order] = {o.id: o for o in orders}
            #    orders = [orders_by_id[o] for o in new_order_ids]
            #    # brute force ordering based on global costs;
            #    lots = self.assign_lots_bf(plant_id, orders, bound_factor=self._params.tsp_solver_global_bound_factor,
            #                               timeout=self._params.tsp_solver_global_bound_timeout, init_nearest_neighbours=self._params.tsp_solver_init_nearest_neighbours)
            ## if target lot sizes are prescribed and we end up above the limit, then we try to split lots
            targets = self._targets.target_weight.get(plant_id)
            if targets is not None and targets.lot_weight_range is not None:
                min_lot, max_lot = targets.lot_weight_range
                if max_lot is not None and max_lot > 0:
                    LotsAllocator._adapt_lot_sizes(lots, orders, min_lot, max_lot, plant_id, "LC" + self._plants[plant_id].name_short)
            result[plant_id] = lots

        if self._base_lots is not None:  # in this case we only want to extend the existing lots
            addon = {p: lots[0] for p, lots in result.items()}
            result = {p: [self._adapt_base_lots(lot, addon.get(p, None))] for p, lot in self._base_lots.items()}
        return result, timed_out

    def assign_lots_internal(self, plant_id: int, orders: list[Order], has_global_costs: bool, snapshot: Snapshot,
                       bound_factor: float|None=None, timeout: float|None=None, pre_timeout: int|None=None, solver_id: str|None=None) -> tuple[list[Lot], bool|None]:
        """Returns lots, plus indicator if timeout has been hit"""
        timeout = timeout if timeout is not None and timeout > 0 else None if timeout is not None else self._params.tsp_solver_global_timeout
        # TODO better to reshuffle lots separately? At least if there are too many orders?
        plant = self._plants[plant_id]
        plant_targets = self._targets.target_weight.get(plant_id, EquipmentProduction(equipment=plant_id, total_weight=0))
        costs = self._costs
        dummy_lot = "LotDummy"
        transition_costs = np.array([[self._costs.transition_costs(plant, o1, o2) for o2 in orders] for o1 in orders], dtype=np.float32)
        start_costs = None
        prev_order: str|None = None
        if self._previous_orders is not None and plant_id in self._previous_orders:
            prev_order = self._previous_orders.get(plant_id)
            prev_obj = self._orders[prev_order] if self._orders is not None else self._snapshot.get_order(prev_order,
                                                                                                          do_raise=True)
            start_costs = np.array([self._costs.transition_costs(plant, prev_obj, order) for order in orders])
            start_costs[np.isnan(start_costs)] = 50
        num_orders = len(orders)
        if bound_factor is None:
            bound_factor = 0 if num_orders < 5 else 1 if num_orders >= 10 else 0.25 + (num_orders - 5) / 5 * 0.75
        elif bound_factor < 0:
            bound_factor = 0

        def global_costs(route: npt.NDArray[np.uint16], next_item: np.uint16, status: tuple[EquipmentStatus, ObjectiveFunction]) -> tuple[EquipmentStatus, ObjectiveFunction]:
            # Note that material structure need not be considered here, it is fixed by the order assignments to equipment
            if len(route) == 0:
                oid = orders[next_item].id
                assignments = {oid: OrderAssignment(order=oid, equipment=plant_id, lot=dummy_lot, lot_idx=1)}
                assignments.update({o.id: OrderAssignment(order=o.id, equipment=-1, lot="", lot_idx=-1) for o in orders if o.id != oid})
                status = self._costs.evaluate_equipment_assignments(plant_targets, self._process, assignments, snapshot, self._targets.period,
                                                                    previous_order=prev_order, orders_custom_priority=self._orders_custom_priority)
                return status, costs.objective_function(status)
            current: Order = orders[route[-1]]
            next: Order = orders[next_item]
            new_lot: bool = len(route) == 0 or self.create_new_lot_costs_based(transition_costs[route[-1], next_item])
            return self._costs.update_transition_costs(plant, current, next, status[0], snapshot, new_lot=new_lot, orders_custom_priority=self._orders_custom_priority)

        def eval_costs(status: tuple[EquipmentStatus, ObjectiveFunction], is_final: bool) -> float:
            # The weight deviation is irrelevant here because it is the same for all routes; we therefore get better
            # estimates by subtracting it and hence can apply better shortcutting
            return status[1].additive_costs if not is_final else status[1].total_value - status[1].weight_deviation

        empty_status = costs.equipment_status(snapshot, plant, self._targets.period, plant_targets.total_weight)
        if solver_id == "default":
            ortootls_timeout = pre_timeout if pre_timeout is not None and pre_timeout > 0 else None if pre_timeout is not None else self._params.tsp_solver_ortools_timeout
            solver = (GlobalSearchDefault(bound_factor_upcoming_costs=bound_factor, timeout_pre_solvers=ortootls_timeout) if num_orders > 5 else \
                        GlobalSearchBB(bound_factor_upcoming_costs=bound_factor)) if has_global_costs else GoogleOrSolver()
        elif solver_id == "ortools":
            solver = GoogleOrSolver()
        elif solver_id == "globalbb":
            solver = GlobalSearchBB(bound_factor_upcoming_costs=bound_factor)
        else:
            raise ValueError(f"Invalid solver id {solver_id}")
        data: GlobalTspInput = GlobalTspInput(local_transition_costs=transition_costs, local_start_costs=start_costs, empty_state=(empty_status, costs.objective_function(empty_status)),
                                              time_limit=timeout, transition_costs=global_costs, eval_costs=eval_costs)
        result = solver.find_shortest_path_global(data)
        route = result.route
        lot_count = 0
        lot_orders: list[Order] = []
        lots: list[Lot] = []
        last_idx: int|None = None
        last_order: Order | None = None
        for idx in route:
            costs = 0 if last_order is None else transition_costs[last_idx, idx]
            order: Order = orders[idx]
            # costs = 0 if last_order is None else self._costs.transition_costs(plant, last_order, order)
            if self.create_new_lot_costs_based(costs):
                lot: Lot = Lot(id="LC_" + plant.name_short + "." + f"{lot_count:02d}", equipment=plant_id, active=False,
                               status=1, orders=[o.id for o in lot_orders],
                               weight=sum(o.actual_weight for o in lot_orders))
                lots.append(lot)
                lot_count += 1
                lot_orders = []
            lot_orders.append(order)
            last_idx = idx
            last_order = order
        if len(lot_orders) > 0:
            lots.append(
                Lot(id="LC_" + plant.name_short + "." + f"{lot_count:02d}", equipment=plant_id, active=False, status=1,
                    orders=[o.id for o in lot_orders], weight=sum(o.actual_weight for o in lot_orders)))
        return lots, result.timeout_reached

    """@deprecated"""
    def assign_lots_bf(self, plant_id: int, orders: list[Order],
                       bound_factor: float|None=None, timeout: float=1, init_nearest_neighbours: bool=False) -> list[Lot]:
        timeout = timeout if timeout > 0 else None
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
        if bound_factor is None:
            bound_factor = 0 if num_orders <= 5 else 1 if num_orders >= 15 else 0.25 + (num_orders - 5) / 10 * 0.75
        elif bound_factor < 0:
            bound_factor = 0

        def global_costs(route: tuple[int, ...], trans_costs: float) -> float:   # TODO avoid recalculating transition costs?
            assignments = {orders[idx].id: OrderAssignment(equipment=plant_id, order=orders[idx].id, lot=dummy_lot, lot_idx=counter+1) for counter, idx in enumerate(route)}
            # TODO consider other keyword parameters, such as priorities
            status: EquipmentStatus = self._costs.evaluate_equipment_assignments(plant_targets, self._process, assignments, self._snapshot, self._targets.period,
                                                                    previous_order=self._previous_orders.get(plant_id) if self._previous_orders is not None else None)
            result = costs.objective_function(status).total_value
            return result

        from dynreact.lotcreation.global_tsp_bf import solve
        route, costs0 = solve(transition_costs, global_costs, start_costs=start_costs, bound_factor_upcoming_costs=bound_factor, time_limit=timeout, init_nearest_neighbours=init_nearest_neighbours)
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

    "@deprecated"
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
        # This method is used to optimize the initial configuration, therefore we apply higher timeouts than in the
        # iteration step optimization, which is on the hot path and less critical.
        or_timeout = 3*self._params.tsp_solver_ortools_timeout if self._params.tsp_solver_ortools_timeout is not None else None
        new_lots: dict[int, list[Lot]] = self.assign_lots(order_plant_assignments, timeout=self._params.tsp_solver_final_timeout, pre_timeout=or_timeout)[0]
        new_assignments: dict[str, OrderAssignment] = {}
        for plant, lots in new_lots.items():
            for lot in lots:
                for lot_idx, order in enumerate(lot.orders):
                    new_assignments[order] = OrderAssignment(equipment=plant, order=order, lot=lot.id, lot_idx=lot_idx+1)
        for order in order_plant_assignments.keys():
            if order not in new_assignments:
                new_assignments[order] = OrderAssignment(equipment=-1, order=order, lot="", lot_idx=-1)
        new_planning: ProductionPlanning = self._costs.evaluate_order_assignments(self._process, new_assignments, self._targets, self._snapshot,
                                                        total_priority=self._total_priority, previous_orders=self._previous_orders)
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

    def __init__(self,  slist: list[OrderAssignment], TabuList: set[Any], tabu_search: LotsAllocator, planning: ProductionPlanning, max_tsps: int, rand_seed: int|None=None):
        self.slist: list[OrderAssignment] = slist
        self.TabuList: set[TabuSwap] = TabuList
        self.tabu_search: LotsAllocator = tabu_search
        self.planning: ProductionPlanning = planning  # the starting point
        self.max_tsps = max_tsps
        order_ids = [ass.order for ass in self.slist]
        self.orders: dict[str, Order] = {oid: self.tabu_search._orders[oid] for oid in order_ids}
        self.rand_seed: int|None = rand_seed

    def BestN(self) -> tuple[TabuSwap, ProductionPlanning, ObjectiveFunction]:
        targets: ProductionTargets = self.tabu_search._targets
        costs: CostProvider = self.tabu_search._costs
        snapshot = self.tabu_search._snapshot
        is_lot_append: bool = self.tabu_search._base_lots is not None
        previous_orders: dict[int, str] | None = self.tabu_search._previous_orders
        planning = self.planning
        main_category: str|None = self.tabu_search._main_category
        orders_custom_priority: dict[str, int] | None = self.tabu_search._orders_custom_priority

        best_swap: TabuSwap = None
        best_solution: ProductionPlanning = None
        objective_value: float = float("inf")
        best_objective: ObjectiveFunction|None = None
        track_structure: bool = targets.material_weights is not None
        best_timed_out: bool = False
        swaps: list[TabuSwap] = self._get_swaps()
        dummy_swaps: list[TabuSwap] = []  # for those we will not solve the TSP
        if self.max_tsps >= 0 and len(swaps) > self.max_tsps:
            # every worker has a limited budget of TSPs to solve, so we need to select those
            tsp_swaps = random.Random(x=self.rand_seed).sample(swaps, k=self.max_tsps) if self.max_tsps > 0 else []
            dummy_swaps = [s for s in swaps if s not in tsp_swaps]
            swaps = tsp_swaps
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
            new_assigned_lots, timeout_hit = self.tabu_search.assign_lots(assignments_for_lc)
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
                best_timed_out = timeout_hit
        for swap in dummy_swaps:
            # here we do not solve the TSP for time budget reasons; instead a simplistic heuristic method is used
            # to hopefully find a reasonably good configuration
            swap_planning, swap_objective = self._eval_dummy_swap(swap)
            objective_fct = swap_objective.total_value
            if objective_fct < objective_value:
                objective_value = objective_fct
                best_objective = swap_objective
                best_swap = swap
                best_solution = swap_planning
                best_timed_out = True
        if best_objective is None:
            best_objective = ObjectiveFunction(total_value=objective_value)
        elif best_timed_out and self.tabu_search._params.tsp_solver_final_tsp:
            # if there are global costs, run the TSP again for the plants with new configurations but this time with higher resource budget
            plant_by_order: dict[str, int] = {o: ass.equipment for o, ass in best_solution.order_assignments.items() if ass.equipment >= 0}
            pre_timeout = 2 * self.tabu_search._params.tsp_solver_ortools_timeout if self.tabu_search._params.tsp_solver_ortools_timeout is not None else None
            final_lots, _ = self.tabu_search.assign_lots(plant_by_order, timeout=self.tabu_search._params.tsp_solver_final_timeout, pre_timeout=pre_timeout)  # : dict[int, list[Lot]]
            old_lots: dict[int, list[Lot]] = best_solution.get_lots()
            lots_differ = len(final_lots) != len(old_lots) or any(p not in old_lots for p in final_lots.keys()) or  \
                          any(CTabuWorker._lots_differ(final_lots[p], old_lots[p]) for p in final_lots.keys())
            # check if there are any differences to the previous configuration, only then recalculate the costs!
            if lots_differ:  # we know that order assignments can only differ in the ordering, not in the equipment assignments
                # adapt existing assignments, not needed any more
                assignments: dict[str, OrderAssignment] = {}
                plant_status = {}
                for p, lots in final_lots.items():
                    for lot in lots:
                        for idx, ord in enumerate(lot.orders):
                            assignments[ord] = OrderAssignment(order=ord, equipment=p, lot=lot.id, lot_idx=idx+1)
                    equipment_targets = targets.target_weight.get(p, EquipmentProduction(equipment=p, total_weight=0.0))
                    start_order = previous_orders.get(p) if previous_orders is not None else None
                    new_status: EquipmentStatus = costs.evaluate_equipment_assignments(equipment_targets, planning.process, assignments, snapshot, targets.period,
                                        track_structure=track_structure, main_category=main_category, orders_custom_priority=orders_custom_priority, previous_order=start_order)
                    plant_status[p] = new_status
                assignments.update({o: OrderAssignment(order=o, equipment=-1, lot="", lot_idx=-1) for o in planning.order_assignments.keys() if o not in assignments})
                new_sol = ProductionPlanning(process=planning.process, order_assignments=assignments, equipment_status=plant_status, target_structure=targets.material_weights,
                                                        total_priority=planning.total_priority, previous_orders=previous_orders)
                total_objectives = costs.process_objective_function(new_sol)
                if total_objectives.total_value < best_objective.total_value:
                    best_solution = new_sol
                    best_objective = total_objectives
        return best_swap, best_solution, best_objective

    def _eval_dummy_swap(self, swap: TabuSwap) -> tuple[ProductionPlanning, ObjectiveFunction]:
        targets: ProductionTargets = self.tabu_search._targets
        costs: CostProvider = self.tabu_search._costs
        snapshot = self.tabu_search._snapshot
        previous_orders: dict[int, str] | None = self.tabu_search._previous_orders
        planning = self.planning
        main_category: str | None = self.tabu_search._main_category
        orders_custom_priority: dict[str, int] | None = self.tabu_search._orders_custom_priority
        track_structure: bool = targets.material_weights is not None
        orders: dict[str, Order] = self.tabu_search._orders
        # here we do not solve the TSP for time budget reasons; instead a simplistic heuristic method is used
        # to hopefully find a reasonably good configuration
        target_plant = swap.PlantTo
        source_plant = swap.PlantFrom
        swap_order: Order = orders[swap.Order]
        plant_status: dict[int, EquipmentStatus] = dict(planning.equipment_status)  # shallow copy
        old_assignments = planning.order_assignments
        all_assignments = {o: ass for o, ass in old_assignments.items() if ass.equipment >= 0 and ass.equipment != target_plant and ass.equipment != source_plant}
        if target_plant >= 0:
            other_orders: list[str] = [o for o, ass in old_assignments.items() if ass.equipment == target_plant]
            plant = self.tabu_search._plants[target_plant]
            transition_costs_left = [costs.transition_costs(plant, orders[order], swap_order) for order in other_orders]
            transition_costs_right = [costs.transition_costs(plant, swap_order, orders[order]) for order in other_orders]
            start_order = previous_orders.get(target_plant) if previous_orders is not None else None
            new_assignments: dict[str, OrderAssignment] = {}
            if len(other_orders) == 0:
                new_assignments[swap.Order] = OrderAssignment(order=swap.Order, equipment=target_plant, lot="LC_" + plant.name_short + ".01", lot_idx=1)
            else:
                start_costs = costs.transition_costs(plant, orders[start_order], swap_order) if start_order is not None else transition_costs_right[0]
                transition_costs_left.insert(0, start_costs)
                transition_costs_right.append(transition_costs_left[-1])
                transition_costs = [(cl + cr)/2 for cl, cr in zip(transition_costs_left, transition_costs_right)]
                best_cost = min(transition_costs)
                best_cost_idx = transition_costs.index(best_cost)
                lot_count: int = 0
                lot_idx: int = 1
                last_lot: str = ""
                for idx, order in enumerate(other_orders):
                    oa = old_assignments[order]
                    if idx == best_cost_idx:
                        new_lot = idx > 0 and self.tabu_search.create_new_lot_costs_based(transition_costs_left[idx])
                        if new_lot:
                            lot_count += 1
                            lot_idx = 1
                        new_assignments[swap.Order] = OrderAssignment(order=swap.Order, equipment=target_plant, lot="LC_" + plant.name_short + "." + f"{lot_count:02d}" , lot_idx=lot_idx)
                        new_lot = self.tabu_search.create_new_lot_costs_based(transition_costs_right[idx])
                        lot_idx += 1
                    else:
                        new_lot = idx > 0 and last_lot != oa.lot
                    if new_lot:
                        lot_count += 1
                        lot_idx = 1
                    last_lot = oa.lot
                    new_assignments[order] = OrderAssignment(order=order, equipment=target_plant, lot="LC_" + plant.name_short + "." + f"{lot_count:02d}", lot_idx=lot_idx)
                    lot_idx += 1
                if best_cost_idx >= len(other_orders) :
                    new_lot = self.tabu_search.create_new_lot_costs_based(transition_costs_left[-1])
                    if new_lot:
                        lot_count += 1
                        lot_idx = 1
                    new_assignments[swap.Order] = OrderAssignment(order=swap.Order, equipment=target_plant, lot="LC_" + plant.name_short + "." + f"{lot_count:02d}", lot_idx=lot_idx)
            equipment_targets = targets.target_weight.get(target_plant, EquipmentProduction(equipment=target_plant, total_weight=0.0))
            new_status: EquipmentStatus = costs.evaluate_equipment_assignments(equipment_targets, planning.process, new_assignments, snapshot, targets.period,
                            track_structure=track_structure, main_category=main_category, orders_custom_priority=orders_custom_priority, previous_order =start_order)
            plant_status[target_plant] = new_status
            all_assignments.update(new_assignments)
        if source_plant >= 0:  # TODO we simply remove the old order without reshuffling the other orders => ?
            other_orders = [o for o, ass in old_assignments.items() if ass.equipment == source_plant]
            plant = self.tabu_search._plants[source_plant]
            new_assignments: dict[str, OrderAssignment] = {}
            if len(other_orders) > 1:
                swap_index = other_orders.index(swap.Order)
                lot_count: int = 0
                lot_idx: int = 1
                last_lot: str = ""
                new_lot = True
                for idx, order in enumerate(other_orders):
                    oa = old_assignments[order]
                    if idx == swap_index:
                        new_lot = 0 < idx < len(other_orders) - 1 and self.tabu_search.create_new_lot_costs_based(costs.transition_costs(plant, orders[other_orders[idx-1]], orders[other_orders[idx+1]]))
                        continue
                    if idx != swap_index + 1:
                        new_lot = idx > 0 and last_lot != oa.lot
                    if new_lot:
                        lot_count += 1
                        lot_idx = 1
                    last_lot = oa.lot
                    new_assignments[order] = OrderAssignment(order=order, equipment=source_plant, lot="LC_" + plant.name_short + "." + f"{lot_count:02d}", lot_idx=lot_idx)
                    lot_idx += 1
            equipment_targets = targets.target_weight.get(source_plant, EquipmentProduction(equipment=source_plant, total_weight=0.0))
            start_order = previous_orders.get(source_plant) if previous_orders is not None else None
            new_status: EquipmentStatus = costs.evaluate_equipment_assignments(equipment_targets, planning.process, new_assignments, snapshot, targets.period,
                            track_structure=track_structure, main_category=main_category, orders_custom_priority=orders_custom_priority, previous_order =start_order)
            plant_status[source_plant] = new_status
            all_assignments.update(new_assignments)
        all_assignments.update({o: ass for o, ass in old_assignments.items() if ass.equipment < 0 and o != swap.Order})
        if target_plant < 0:
            all_assignments[swap.Order] = OrderAssignment(order=swap.Order, equipment=-1, lot="", lot_idx=-1)
        planning_candidate = ProductionPlanning(process=planning.process, order_assignments=all_assignments, equipment_status=plant_status, target_structure=targets.material_weights,
                                                total_priority=planning.total_priority, previous_orders=previous_orders)
        total_objectives = costs.process_objective_function(planning_candidate)
        return planning_candidate, total_objectives


    def _get_swaps(self) -> list[TabuSwap]:
        orders = self.orders
        forbidden_assignments = self.tabu_search._forbidden_assignments
        swaps: list[TabuSwap] = []
        plants: dict[int, Equipment] = self.tabu_search._plants
        forced_orders = self.tabu_search._forced_orders
        empty_plants = []
        expiration = self.tabu_search._params.Expiration
        for assignment in self.slist:
            order: Order = orders[assignment.order]
            forbidden_plants: list[int] = forbidden_assignments.get(order.id, empty_plants)
            # sl2 = list(map(lambda x: x[0], filter(lambda x: x[1], self.PM[swp1.Order.ID].items())))

            allowed_plants: list[int] = [p for p in order.allowed_equipment if p in plants and p not in forbidden_plants]
            if assignment.equipment >= 0 and (forced_orders is None or assignment.order not in forced_orders):
                allowed_plants.append(-1)
            if len(allowed_plants) == 0:
                continue
            swaps0: Sequence[TabuSwap] = (TabuSwap(assignment.order, assignment.equipment, new_plant, expiration) for new_plant in allowed_plants if new_plant != assignment.equipment)
            for swap in swaps0:
                if swap not in self.TabuList:
                    swaps.append(swap)
        return swaps

    @staticmethod
    def _lots_differ(l1: list[Lot], l2: list[Lot]) -> bool:
        if len(l1) != len(l2):
            return True
        for lot1, lot2 in zip(l1, l2):
            if len(lot1.orders) != len(lot2.orders):
                return True
            for o1, o2 in zip(lot1.orders, lot2.orders):
                if o1 != o2:
                    return True
        return False




# must be defined in global scope for being useable with pool.imap
def BestN(tw):
    return tw.BestN()

