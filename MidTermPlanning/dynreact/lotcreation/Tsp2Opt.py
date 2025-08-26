# based on https://en.wikipedia.org/wiki/2-opt
from typing import Any, Callable
import numpy as np


def euclidean_path_distance(route: np.ndarray, cities: np.ndarray) -> float:
    return np.sum([np.linalg.norm(cities[route[p]] - cities[route[p - 1]]) for p in range(len(route))])


def _2_opt_swap(route: np.ndarray, v1: int, v2: int) -> np.ndarray:
    l: int = len(route)
    return np.concatenate((route[0:v1], route[v2:-l + v1 - 1:-1], route[v2 + 1:l]))


def find_shortest_distance_2_opt(cities: np.ndarray | list[Any],
             distance_function: Callable[[np.ndarray, np.ndarray], float]=euclidean_path_distance,
             improvement_threshold: float = 0.001) -> np.ndarray[tuple[int], np.dtype[np.integer]]:
    """
    Parameters:
        cities: array of (city coordinates), or list of objects if an appropriate distance function is provided
        distance_function: optional distance function(route, cities), which may include global costs
        improvement_threshold:

    Returns:
        array with indices
    """
    route = np.arange(cities.shape[0] if isinstance(cities, np.ndarray) else len(cities))
    improvement_factor = 1
    best_distance = distance_function(route, cities)
    while improvement_factor > improvement_threshold:
        distance_to_beat = best_distance
        for swap_first in range(0, len(route)-2):
            for swap_last in range(swap_first+1, len(route)):
                new_route = _2_opt_swap(route, swap_first, swap_last)
                new_distance = distance_function(new_route, cities)
                if new_distance < best_distance:
                    route = new_route
                    best_distance = new_distance
        improvement_factor = 1 - best_distance/distance_to_beat
    return route


def plot_route(cities: np.ndarray, route: np.ndarray[tuple[int], np.dtype[np.integer]]):
    import matplotlib.pyplot as plt
    new_cities_order = np.concatenate((np.array([cities[route[i]] for i in range(len(route))]), np.array([cities[0]])))
    plt.scatter(cities[:, 0], cities[:, 1])
    plt.plot(new_cities_order[:, 0], new_cities_order[:, 1])
    plt.show()
    print("Route: " + str(route) + "\n\nDistance: " + str(euclidean_path_distance(route, cities)))


"""
# Usage: (tends to freeze in PyCharm console)

import numpy as np
from MidTermPlanning.dynreact.lotcreation.Tsp2Opt import two_opt, plot_route

cities = np.random.RandomState(42).rand(25, 2)
route = find_shortest_distance_2_opt(cities, 0.001)
plot_route(cities, route)
"""

