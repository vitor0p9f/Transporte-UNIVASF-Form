"""How a solution is scored: the passengers it serves first, then its cost."""

import numpy as np

from .model import Context, Route


def _obj_total(routes: list[Route]) -> float:
    """Operating cost (fuel + driver, BRL) of a set of routes."""
    return sum(r.cost_brl for r in routes)


def solution_key(served: int, cost_brl: float) -> tuple[int, float]:
    """The ranking of a solution: more passengers served first, then less cost.

    Every selection step of the heuristic uses this key: the lambda sweep, the
    two-phase selection and the post-improvement keep the solution that serves
    the most. A smaller key is a better solution.

    The cost is the tie-break: among the solutions that carry the same
    passengers, the cheaper one wins -- the report's metric is the cost per
    passenger, and that cost is the same fuel + driver total the routes pay
    here, so the two criteria agree.
    """
    return (-served, cost_brl)


def _demand_pairs(
    demand: np.ndarray,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """The origin, the destination and the quantity of every demand pair.

    Computed once per demand matrix and cached: the selection steps call this
    thousands of times, and enumerating the whole matrix every time would cost
    more than the merge itself.
    """
    cached = _PAIR_CACHE.get(id(demand))
    if cached is not None and cached[0] is demand:
        return cached[1], cached[2], cached[3]

    origins, destinations = np.nonzero(demand)
    quantities = demand[origins, destinations]
    _PAIR_CACHE.clear()
    _PAIR_CACHE[id(demand)] = (demand, origins, destinations, quantities)
    return origins, destinations, quantities


#: One entry per demand matrix; the array is kept alive so `id` cannot be reused.
_PAIR_CACHE: dict[int, tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]] = {}


def served_bound(stops: list[int] | tuple[int, ...], demand: np.ndarray) -> int:
    """The passengers a stop sequence can carry, ignoring the capacity.

    Counts the pairs whose origin comes before their destination in the
    sequence -- the pairs the bus picks up and drops off in order. The
    capacity and the demand served by another route are ignored, so it is an
    upper bound: it tells which order of the stops serves more.
    """
    if len(stops) < 2:
        return 0

    position = np.full(demand.shape[0], -1, dtype=np.int64)
    position[list(stops)] = np.arange(len(stops))
    origins, destinations, quantities = _demand_pairs(demand)
    boarded = position[origins]
    dropped = position[destinations]
    in_order = (boarded >= 0) & (dropped >= 0) & (boarded < dropped)
    return int(quantities[in_order].sum())


def captured_demand(route: Route, demand: np.ndarray) -> int:
    """The demand a route can carry: the pairs whose ends share the route.

    A bus can only pick up a passenger and drop them off if both ends of the
    pair are in its route. This counts each pair once and ignores the boarding
    order and the capacity, so it is an upper bound on what the route can
    serve.
    """
    nodes = set(route.stops)
    if route.origin is not None:
        nodes.add(route.origin)
    if route.destination is not None:
        nodes.add(route.destination)
    if not nodes:
        return 0

    origins, destinations, quantities = _demand_pairs(demand)
    on_route = np.zeros(demand.shape[0], dtype=bool)
    on_route[list(nodes)] = True
    both_ends = on_route[origins] & on_route[destinations]
    return int(quantities[both_ends].sum())


def estimated_served(routes: list[Route], ctx: Context) -> int:
    """A cheap estimate of the passengers the routes would carry.

    The demand each route holds, capped by the vehicle capacity: a bus cannot
    carry more people than it has seats for. The estimate ignores the boarding
    order and the demand already served by another route, so it is only used
    to rank the solutions while the search runs -- the boarding simulation
    gives the exact number.
    """
    total = 0
    for route in routes:
        captured = captured_demand(route, ctx.demand)
        if ctx.restrictions.capacity:
            captured = min(captured, ctx.capacity)
        total += captured
    return total
