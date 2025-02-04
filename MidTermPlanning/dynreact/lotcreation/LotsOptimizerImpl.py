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


class TabuSearch(LotsOptimizer):

    def __init__(self, site: Site, process: str, costs: CostProvider, snapshot: Snapshot, targets: ProductionTargets,
                 initial_solution: ProductionPlanning, min_due_date: datetime|None = None,
                 # the next two are for initialization from a previous optimization run
                 best_solution: ProductionPlanning|None = None, history: list[ObjectiveFunction] | None = None,
                 parameters: dict[str, any] | None = None,
                 performance_models: list[PlantPerformanceModel] | None = None
                 ):
        super().__init__(site, process, costs, snapshot, targets, initial_solution, min_due_date=min_due_date,
                         best_solution=best_solution, history=history, parameters=parameters, performance_models=performance_models)
        self._params: TabuParams = TabuParams()
        self._performance_restrictions: list[PerformanceEstimation]|None = None
        self._forbidden_assignments: dict[str, list[int]] = {}

    def _init_performance_models(self, initial_plant_assignments: dict[str, int]) -> dict[str, int]:
        if self._performance_models is None or len(self._performance_models) == 0 or self._orders is None:
            return initial_plant_assignments
        changed: bool = False
        for plant in self._plant_ids:
            orders = [o for o in self._orders.values() if plant in o.allowed_equipment]
            restrictions: list[PerformanceEstimation] = \
                [performance for performances in
                 (model.bulk_performance(plant, orders) for model in self._performance_models) for performance in
                 performances if performance.performance < 1]
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
            planning = self._costs.evaluate_order_assignments(self._process, new_assignments, targets=self._targets, snapshot=self._snapshot)
            objective: ObjectiveFunction = self._costs.process_objective_function(planning)
            self._state.current_solution = planning
            self._state.current_object_value = objective
            if best_is_current:
                self._state.best_solution = planning
                self._state.best_objective_value = objective
        return initial_plant_assignments

    def run(self, max_iterations: int|None = None, debug: bool=False) -> LotsOptimizationState:
        initial_plant_assignments: dict[str, int] = {order: ass.equipment for order, ass in self._state.current_solution.order_assignments.items()}
        initial_plant_assignments = self._init_performance_models(initial_plant_assignments)
        TabuList = set()
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
        vbest: ProductionPlanning = self.optimize_lots(initial_plant_assignments)
        target_vbest0: ObjectiveFunction = self._costs.process_objective_function(vbest)
        target_vbest: float = target_vbest0.total_value
        self._state.current_solution = vbest
        self._state.current_object_value = target_vbest0
        if target_vbest != self._state.history[-1].total_value:
            self._state.history.append(target_vbest0)
        vbest_global: ProductionPlanning = self._state.best_solution
        target_vbest_global: float = self._state.best_objective_value.total_value
        if target_vbest < target_vbest_global:
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
            #
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
                    swap_probability: float = swap_probabilities[assignment.lot] if assignment.lot in swap_probabilities else 1
                    if swap_probability < rdswap:
                        continue
                    if self._min_due_date is not None:
                        order = self._orders.get(assignment.order)
                        if order is not None and order.due_date is not None and order.due_date <= self._min_due_date:
                            continue
                    pto = -1
                    TabuList.add(TabuSwap(assignment.order, assignment.equipment, pto, self._params.Expiration))  # add shuffle to tabu list to enable new solutions
                    order_plant_assignment[assignment.order] = pto
                new_planning: ProductionPlanning = self.optimize_lots(order_plant_assignment)
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

    def update_transition_costs(self, plant: Equipment, current: Order, next: Order, status: EquipmentStatus, snapshot: Snapshot,
                                current_material: Any | None = None, next_material: Any | None = None) -> tuple[EquipmentStatus, ObjectiveFunction]:
        new_lot: bool = self.create_new_lot(plant, current, next, current_material=current_material, next_material=next_material)
        return self._costs.update_transition_costs(plant, current, next, status, snapshot, new_lot, current_material=current_material, next_material=next_material)

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
                    new_assignments[order] = OrderAssignment(equipment=plant, order=order, lot=lot.id, lot_idx=lot_idx)
        new_planning: ProductionPlanning = self._costs.evaluate_order_assignments(self._process, new_assignments, self._targets, self._snapshot)
        for order, plant in order_plant_assignments.items():
            if plant < 0:
                new_planning.order_assignments[order] = OrderAssignment(equipment=-1, order=order, lot="", lot_idx=-1)
        return new_planning

    # previously: CalcSolution (although it also determined the PlantStatus objects)
    def assign_lots(self, order_plant_assignments: dict[str, int]) -> dict[int, list[Lot]]:
        # FIXME what if a plant does not currently have any assigned orders? Then it drops out here. Better
        # remember the plants involved here
        plant_ids: set[int] = set(order_plant_assignments.values())
        result: dict[int, list[Lot]] = {}
        for plant_id in plant_ids:
            if plant_id < 0:
                continue
            plant: Equipment = next(p for p in self._plants if p.id == plant_id)
            # sl = dict(filter(lambda s: s[1].AssignedPlant == p.ID, sol.items()))
            order_ids: list[str] = [o for o, plant in order_plant_assignments.items() if plant == plant_id]
            orders: list[Order] = [self._orders[o] if self._orders is not None else self._snapshot.get_order(o, do_raise=True) for o in order_ids]
            #sz = len(sl);  # sTM = np.zeros((sz, sz))
            sz: int = len(order_ids)
            #sTM = np.array(
            #    [[costs.TCostVA(i.Order.Attributes, j.Order.Attributes, p) for j in sl.values()] for i in sl.values()])
            sTM = np.array(
                [[self._costs.transition_costs(plant, o1, o2) for o2 in orders] for o1 in orders]
            )
            sTM[np.isnan(sTM)] = self._params.CostNaN
            G = nx.DiGraph(sTM) if len(sTM) > 0 else nx.DiGraph()

            # TODO connection order consideration
            """
            sT0 = None
            oc = None
            if OCt is not None:
                if plant_id in OCt:
                    oc = OCt[plant_id]
                    if oc is None or oc.Attributes is None:
                        continue
                    sT0 = np.array([costs.TCostVA(oc.Attributes, i.Order.Attributes, p) for i in sl.values()])
                    sT0[np.isnan(sT0)] = CostNaN
            """

            spath = lcor.path_converingOR(sTM) #, sT0)

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
            #sll = list(sl.keys()) # = order_ids
            #rlb = {i: sll[i] for i in range(sz)}
            rlb = {i: order_ids[i] for i in range(sz)}
            dict_subgraph = {i: (nx.relabel_nodes(k[0], rlb), list(map(lambda x: rlb[x], k[1]))) for i, k in
                             dict_subgraph.items()}
            # assign solution element to lot
            lots: list[Lot] = []

            for idx, g in enumerate(dict_subgraph.values()):
                #for oid in g[1]: sol[oid].Lot = g
                # TODO status?
                # prepend LC_ to distinguish generated lots from pre-existing ones
                lot: Lot = Lot(id="LC_" + plant.name_short + "." + f"{idx:02d}", equipment=plant_id, active=True, status=0, orders=g[1])
                lots.append(lot)
            result[plant_id] = lots
            #due_dates = [o.due_date for o in orders if o.due_date is not None]
            #mdate = datetime(1, 1, 1) if len(due_dates) == 0 else min(due_dates)
            #cclottot = sum([sTM[spath[i]][spath[i + 1]] for i in range(sz - 1)])
            # TODO handle setup coils
            #if sz > 0 and sT0 is not None: cclottot += sT0[spath[0]]

            #sval = SolutionValue(
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
            #)

            #PSDict[plant_id] = sval
            #delta += sval.DeltaW
            #nlots += sval.NLots

        return result

    def FindNextStep(self, planning: ProductionPlanning, TabuList: set[Any], pool: multiprocessing.pool.Pool|None) -> tuple[TabuSwap, ProductionPlanning, ObjectiveFunction]:
        # sl1 = list(sol.values())  # order plant assignments
        sl1: list[OrderAssignment] = [ass for ass in planning.order_assignments.values()]
        # slp = [[sl1[i] for i in range(len(sl1)) if (i % self.params.NParallel) == r] for r in range(self.params.NParallel)]
        slp: list[list[OrderAssignment]] = [[sl1[i] for i in range(len(sl1)) if (i % self._params.NParallel) == r] for r in range(self._params.NParallel)]
        plants = {plant.id: plant for plant in self._plants}
        items = [CTabuWorker(self._costs, sl, TabuList, self._params, self, plants, self._snapshot, self._targets, planning, self._min_due_date) for sl in slp]
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

        return swpbest, best_solution, objective_value


class TabuAlgorithm(LotsOptimizationAlgo):

    def __init__(self, site: Site):
        super().__init__(site)

    def _create_instance_internal(self, process: str, snapshot: Snapshot, targets: ProductionTargets,
                                  costs: CostProvider, initial_solution: ProductionPlanning, min_due_date: datetime|None = None,
                                  # the next two are for initialization from a previous optimization run
                                  best_solution: ProductionPlanning | None = None, history: list[ObjectiveFunction] | None = None,
                                  performance_models: list[PlantPerformanceModel] | None = None,
                                  parameters: dict[str, any] | None = None
                                  ) -> TabuSearch:
        return TabuSearch(self._site, process, costs, snapshot, targets, initial_solution=initial_solution, min_due_date=min_due_date,
                          best_solution=best_solution, history=history, parameters=parameters, performance_models=performance_models)


class CTabuWorker:

    def __init__(self, costs: CostProvider, slist: list[OrderAssignment], TabuList: set[Any], params: TabuParams, tabuSearch,
                 plants: dict[int, Equipment],
                 snapshot: Snapshot, targets: ProductionTargets, planning: ProductionPlanning, min_due_date: datetime|None):
        self.slist: list[OrderAssignment] = slist
        order_ids = [ass.order for ass in slist]
        self.orders: dict[int, Order] = {oid: tabuSearch._orders[oid] for oid in order_ids}
        self.plants: dict[int, Equipment] = plants

        #self.PM = PM
        self.TabuList: set[TabuSwap] = TabuList
        self.params = params
        self.tabu_search = tabuSearch
        self.targets: ProductionTargets = targets
        self.planning: ProductionPlanning = planning
        self.costs = costs
        self.snapshot = snapshot
        self._min_due_date: datetime|None = min_due_date

    def BestN(self) -> tuple[TabuSwap, ProductionPlanning, ObjectiveFunction]:
        best_swap: TabuSwap = None
        best_solution: ProductionPlanning = None
        objective_value: float = float("inf")
        best_objective: ObjectiveFunction|None = None
        empty_plants = []
        for assignment in self.slist:
            order: Order = self.orders[assignment.order]
            forbidden_plants: list[int] = self.tabu_search._forbidden_assignments.get(order.id, empty_plants)
            # sl2 = list(map(lambda x: x[0], filter(lambda x: x[1], self.PM[swp1.Order.ID].items())))

            allowed_plants: list[int] = [p for p in order.allowed_equipment if p in self.plants and p not in forbidden_plants]
            if assignment.equipment >= 0 and (self._min_due_date is None or order.due_date is None or order.due_date > self._min_due_date):
                allowed_plants.append(-1)
            if len(allowed_plants) == 0:
                continue
            # nbh = list(filter(lambda swp: swp not in self.TabuList and swp.PlantFrom != swp.PlantTo,
            #                      [TabuSwap(swp1.Order.ID, swp1.AssignedPlant, s, self.params.Expiration) for s in sl2]))
            swaps: Sequence[TabuSwap] = \
                (TabuSwap(assignment.order, assignment.equipment, new_plant, self.params.Expiration) for new_plant in allowed_plants if new_plant != assignment.equipment)
            swaps = (swap for swap in swaps if swap not in self.TabuList)
            for swp in swaps:

                order_assignments: dict[str, OrderAssignment] = dict(self.planning.order_assignments)  # shallow copy
                order_assignments[swp.Order] = OrderAssignment(order=swp.Order, equipment=swp.PlantTo, lot="", lot_idx=-1)
                affected_orders: list[str] = [o for o, ass in order_assignments.items() if ass.equipment == swp.PlantFrom or ass.equipment == swp.PlantTo]

                plant_status: dict[int, EquipmentStatus] = dict(self.planning.equipment_status)  # shallow copy
                # reset plant solutions for swap
                new_assigned_lots: dict[int, list[Lot]] = self.tabu_search.assign_lots(
                    {o: order_assignments[o].equipment for o in affected_orders if order_assignments[o].equipment >= 0})
                if swp.PlantFrom >= 0:
                    plant_status[swp.PlantFrom] = None
                    assigned_lots: list[Lot] = new_assigned_lots.get(swp.PlantFrom, [])
                    orders_affected: list[str] = [order_id for order_id in affected_orders if order_assignments[order_id].equipment == swp.PlantFrom]
                    for lot in assigned_lots:
                        for idx, order in enumerate(lot.orders):
                            order_assignments[order] = OrderAssignment(equipment=swp.PlantFrom, order=order, lot=lot.id, lot_idx=idx+1)
                            orders_affected.remove(order)
                    for order in orders_affected:
                        del order_assignments[order]
                    new_status: EquipmentStatus = self.costs.evaluate_equipment_assignments(swp.PlantFrom, self.planning.process,
                                                                                            order_assignments, self.snapshot, self.targets.period, self.targets.target_weight.get(swp.PlantFrom, EquipmentProduction(equipment=swp.PlantFrom, total_weight=0.0)).total_weight)
                    plant_status[swp.PlantFrom] = new_status
                if swp.PlantTo >= 0:
                    plant_status[swp.PlantTo] = None
                    assigned_lots: list[Lot] = new_assigned_lots[swp.PlantTo]
                    orders_affected: list[str] = [order_id for order_id in affected_orders if order_assignments[order_id].equipment == swp.PlantTo]
                    for lot in assigned_lots:
                        for idx, order in enumerate(lot.orders):
                            order_assignments[order] = OrderAssignment(equipment=swp.PlantTo, order=order, lot=lot.id, lot_idx=idx + 1)
                            orders_affected.remove(order)
                    for order in orders_affected:
                        del order_assignments[order]
                    new_status: EquipmentStatus = self.costs.evaluate_equipment_assignments(swp.PlantTo, self.planning.process, order_assignments, self.snapshot,
                                                                                            self.targets.period, self.targets.target_weight.get(swp.PlantTo, EquipmentProduction(equipment=swp.PlantTo, total_weight=0.0)).total_weight)
                    plant_status[swp.PlantTo] = new_status
                total_objectives = CostProvider.sum_objectives([self.costs.objective_function(status) for status in plant_status.values()])
                objective_fct = total_objectives.total_value
                if objective_fct < objective_value:
                    objective_value = objective_fct
                    best_objective = total_objectives
                    best_swap = swp
                    best_solution = ProductionPlanning(process=self.planning.process, order_assignments=order_assignments, equipment_status=plant_status)
        if best_objective is None:
            best_objective = ObjectiveFunction(total_value=objective_value)
        return best_swap, best_solution, best_objective


# must be defined in global scope for being useable with pool.imap
def BestN(tw):
    return tw.BestN()

