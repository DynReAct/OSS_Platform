import unittest

import numpy as np

from dynreact.lotcreation.global_tsp_bf import solve


class TestTsp(unittest.TestCase):
    """
    Tests for TSP solver with path-dependent costs
    """

    def test_setup(self):
        """
        A scenario without global costs
        """
        transition_costs = [[0, 1, 2], [1, 0, 1], [2, 1, 0]]
        start_costs = [0, 5, 5]  # ensure we start with item 0
        result, costs = solve(transition_costs, global_costs=lambda route, trans_costs: trans_costs, start_costs=start_costs)
        assert result is not None and len(result) == 3, f"Result should be a tuple with three entries, got {result}"
        assert result[0] == 0, f"Result was expected to start with position 0, got {result}"
        assert all(idx == entry for idx, entry in enumerate(result)), "Expected result [0, 1, 2], got {result}"

    def test_no_start_costs(self):
        """
        A scenario without global costs nor start costs
        """
        transition_costs = [[0, 1, 2], [1, 0, 2], [1, 1, 0]]
        result, costs = solve(transition_costs, global_costs=lambda route, trans_costs: trans_costs)
        assert result is not None and len(result) == 3, f"Result should be a tuple with three entries, got {result}"
        assert result[0] == 2, f"Result was expected to start with start with position 2, got {result}"

    def test_global_costs_1(self):
        """
        In this scenario, local costs would prefer a solution [0, 1, 2], but global constraints impose that item 0 must
        not precede item 1
        """
        transition_costs = [[0, 1, 2], [1, 0, 1], [2, 1, 0]]
        start_costs = [0, 2, 5]  # ensure we start with item 0
        global_costs = lambda route, trans_costs: trans_costs if 0 in route and 1 in route and route.index(1) < route.index(0) else trans_costs + 10
        result, costs = solve(transition_costs, global_costs=global_costs, start_costs=start_costs)
        assert result is not None and len(result) == 3, f"Result should be a tuple with three entries, got {result}"
        assert result[0] == 1, f"Result was expected to start with start with position 1, got {result}"

    def test_global_costs_2(self):
        """
        In this scenario, local costs would prefer a solution [0, 1, 2], but global constraints impose
        a particular other order [2, 0, 1]
        """
        transition_costs = [[0, 1, 2], [1, 0, 1], [2, 1, 0]]
        start_costs = [0, 2, 5]  # ensure we start with item 0
        global_costs = lambda route, trans_costs: trans_costs if len(route) == 3 and route[0] == 2 and route[1] == 0 and route[2] == 1 else trans_costs + 10
        result, costs = solve(transition_costs, global_costs=global_costs, start_costs=start_costs)
        assert result is not None and len(result) == 3, f"Result should be a tuple with three entries, got {result}"
        assert result[0] == 2 and result[1] == 0 and result[2] == 1, f"Expected result [2,0,1], got {result}"

    def test_global_costs_3(self):
        """
        In this scenario, local costs would prefer a solution [0, 1, 2, 3, 4], but global constraints impose
        that item 0 comes last
        """
        # Transition costs favor the order [0, 1, 2, 3, 4]
        transition_costs = [[0, 1, 2, 2, 2], [2, 0, 1, 2, 2], [2, 2, 0, 1, 2], [2, 2, 2, 0, 1], [2, 2, 2, 2, 0]]
        # Start costs favor starting with item 0
        start_costs = [0, 2, 2, 2, 2]
        # first validate that in the absence of global costs it works as expected
        local_costs_only = lambda route, trans_costs: trans_costs
        result_local, costs = solve(transition_costs, global_costs=local_costs_only, start_costs=start_costs)
        assert result_local is not None and len(result_local) == 5, f"Result should be a tuple with five entries, got {result_local}"
        assert all(entry == idx for idx, entry in enumerate(result_local)), f"Unexpected local result {result_local}"

        last_position = len(start_costs) - 1
        # global costs favor item 0 comes last
        global_costs = lambda route, trans_costs: trans_costs if 0 in route and route.index(0) == last_position else trans_costs + 50
        result, costs = solve(transition_costs, global_costs=global_costs, start_costs=start_costs)
        assert result is not None and len(result) == 5, f"Result should be a tuple with five entries, got {result}"
        assert result.index(0) == last_position, f"Result was expected to end with position 0, got {result}"
        assert all(entry == idx + 1 for idx, entry in enumerate(result) if idx < last_position), f"Unexpected result {result}"

    def test_early_stopping(self):
        num_items: int = 100  # this would not be feasible to solve without some early stopping mechanism
        transition_costs = 5 * np.ones((num_items, num_items))
        for idx in range(num_items):
            transition_costs[idx, idx] = 0
            if idx < num_items-1:
                transition_costs[idx+1, idx] = 1   # cheaper to go from pos. idx+1 to idx
        start_costs = 2 * np.ones(num_items)
        start_costs[-1] = 1  # cheapest to start at the end
        local_costs_only = lambda route, trans_costs: trans_costs
        # using the upcoming costs estimation should allow for efficient early stopping in this specific example
        # it is important here to start with the actual solution, which is guaranteed by init_nearest_neighbours
        result, costs = solve(transition_costs, global_costs=local_costs_only, start_costs=start_costs,
                              init_nearest_neighbours=True, bound_factor_upcoming_costs=0.5)
        assert all(entry == num_items - idx - 1 for idx, entry in enumerate(result)), f"Unexpected order in result {result}"


if __name__ == "__main__":
    unittest.main()
