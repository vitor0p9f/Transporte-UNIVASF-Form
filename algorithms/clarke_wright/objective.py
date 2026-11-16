"""Service-first selection; CW savings construction remains distance-based."""

import numpy as np
from algorithms.top_univasf.simulation import simulate_stops
from utils.instances import InstanceData
from .model import Context, Route
from .metrics import route_path


def solution_key(served: int, cost_brl: float) -> tuple[int, float]:
    """Ranking of a solution: more passengers served first, then lower cost."""
    return (-served, cost_brl)


def _obj_total(routes: list[Route]) -> float:
    """Fuel plus driver cost of the complete routes (BRL)."""
    return sum(r.cost_brl for r in routes)


def mask_quantity(mask: int, ctx: Context) -> int:
    total = 0
    while mask:
        bit = mask & -mask
        total += ctx.od_quantities[bit.bit_length() - 1]
        mask ^= bit
    return total


def service_mask(path: tuple[int, ...], ctx: Context) -> int:
    """OD pairs with endpoints visited in the right order, counted once."""
    cache = ctx._cache.setdefault('service_masks', {})
    if path in cache:
        return cache[path]
    first = np.full(len(ctx.demand), -1, dtype=int)
    last = np.full(len(ctx.demand), -1, dtype=int)
    for pos, node in enumerate(path):
        if first[node] < 0:
            first[node] = pos
        last[node] = pos
    compatible = (first[ctx.od_origins] >= 0) & (
        last[ctx.od_destinations] > first[ctx.od_origins]
    )
    mask = sum(1 << int(i) for i in np.flatnonzero(compatible))
    if len(cache) >= 65536:
        cache.clear()
    cache[path] = mask
    return mask


def service_bound(routes: list[Route], ctx: Context) -> int:
    """Optimistic OD-order bound, NOT exact boarding; capacity is ignored.

    Numpy masks count each OD pair once across routes. For unanchored orders,
    the union over permitted endpoint pairs and directions is optimistic too.
    Exact simulation is reserved for anchored candidates and final decisions.
    """
    mask = 0
    for route in routes:
        if route.anchored or not (ctx.origins or ctx.destinations):
            mask |= service_mask(route_path(route, ctx), ctx)
        else:
            # The optimistic union over both directions depends on the set
            # of customer nodes, not their order. CW orders contain no repeats.
            key = route.node_mask or sum(1 << n for n in set(route.stops))
            cache = ctx._cache.setdefault('unanchored_bounds', {})
            if key not in cache:
                route_mask = 0
                nodes = tuple(sorted(set(route.stops)))
                for order in (nodes, nodes[::-1]):
                    for origin in ctx.origins or (ctx.depot,):
                        for destination in ctx.destinations or (order[-1] if order else origin,):
                            body = tuple(n for n in order if n != origin and n != destination)
                            path = (origin, *body)
                            if path[-1] != destination:
                                path += (destination,)
                            route_mask |= service_mask(path, ctx)
                if len(cache) >= 32768:
                    cache.clear()
                cache[key] = route_mask
            mask |= cache[key]
    return mask_quantity(mask, ctx)


def served_passengers(routes: list[Route], ctx: Context) -> int:
    """Exact shared boarding simulation, without mutating routes or demand."""
    paths = tuple(route_path(r, ctx) for r in routes)
    cache = ctx._cache.setdefault('exact_service', {})
    if paths in cache:
        return cache[paths]
    remaining = ctx.demand.copy()
    data = InstanceData([], ctx.distance, ctx.time, ctx.demand)
    served = 0
    for path in paths:
        outcome = simulate_stops(data, path, ctx.capacity, remaining)
        served += outcome.passengers
        for o, d, quantity in outcome.pairs:
            remaining[o, d] -= quantity
    if len(cache) >= 16384:
        cache.clear()
    cache[paths] = served
    return served


def exact_key(routes: list[Route], ctx: Context) -> tuple[int, float]:
    return solution_key(served_passengers(routes, ctx), _obj_total(routes))
