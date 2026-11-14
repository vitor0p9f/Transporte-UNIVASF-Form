"""OVRP construction: route merging, direction choice and two-phase selection."""

import random

from .constants import ITER_TWO_PHASE
from .metrics import _route_distance, _route_time, _update_cost
from .model import Context, Route, Saving
from .objective import _obj_total


def _best_direction(stops: list[int], ctx: Context) -> list[int]:
    """CW-2 procedure: try both directions of the open route.

    In the OVRP:
      forward : depot -> p1 -> p2 -> ... -> pn   (distance D_f)
      reverse : depot -> pn -> p(n-1) -> ... -> p1 (distance D_r)

    With the time constraint active the direction is not indifferent (the first
    leg leaves the depot), so directions that already break the limit are
    dropped before picking the shortest one. If none fits, the shortest one is
    returned and the caller rejects the route through `Context.fits`.
    """
    directions = [list(stops), list(reversed(stops))]
    if ctx.restrictions.time:
        feasible = [d for d in directions if _route_time(d, ctx) <= ctx.max_time]
        if feasible:
            directions = feasible
    return min(directions, key=lambda d: _route_distance(d, ctx))


def _merge(
    savings: list[Saving],
    active_stops: set[int],
    ctx: Context,
) -> list[Route]:
    """Merging procedure of the parallel Clarke-Wright.

    For every saving s(i,j) in descending order:
      - if i and j sit in different routes
      - if the merge does not break the active constraint(s) (capacity/time)
      - if i is an endpoint (start or end) of its route
      - if j is an endpoint of its route
      -> merge the routes

    A stop whose demand alone already breaks the limit still becomes its own
    route (the algorithm never drops demand); the report flags that case.
    """
    # Initial solution: one route per stop
    routes: list[Route] = []
    endpoint: dict[int, Route] = {}  # endpoint -> the route holding it

    for p in sorted(active_stops):  # fixed order -> reproducible result
        r = Route(stops=[p], load=ctx.stop_loads.get(p, 0))
        _update_cost(r, ctx)
        routes.append(r)
        endpoint[p] = r

    for s in savings:
        ri = endpoint.get(s.i)
        rj = endpoint.get(s.j)

        if ri is None or rj is None or ri is rj:
            continue

        load = ri.load + rj.load
        if ctx.restrictions.capacity and load > ctx.capacity:
            continue

        new_order = None

        if ri.last() == s.i and rj.first() == s.j:
            new_order = ri.stops + rj.stops
        elif rj.last() == s.j and ri.first() == s.i:
            new_order = rj.stops + ri.stops
        elif ri.last() == s.i and rj.last() == s.j:
            new_order = ri.stops + list(reversed(rj.stops))
        elif ri.first() == s.i and rj.first() == s.j:
            new_order = list(reversed(ri.stops)) + rj.stops

        if new_order is None:
            continue

        # Apply CW-2: pick the best direction of the open route
        new_order = _best_direction(new_order, ctx)
        if not ctx.fits(load, _route_time(new_order, ctx)):
            continue

        new_route = Route(stops=new_order, load=load)
        _update_cost(new_route, ctx)

        # Drop the merged routes (by identity: `Route` compares by value)
        routes = [r for r in routes if r is not ri and r is not rj]
        for p in ri.stops + rj.stops:
            endpoint.pop(p, None)

        # Register the new route
        routes.append(new_route)
        endpoint[new_route.first()] = new_route
        endpoint[new_route.last()] = new_route

    return routes


def _roulette_wheel(savings: list[Saving], size: int) -> list[Saving]:
    """Roulette-wheel selection over the `size` best savings (section 2.3).

    Rebuilds the savings list by probabilistically shuffling the best ones on
    every iteration -- that explores different merging orders.

    Probability (paper equation): p_n = s_n / sum(s_i), favouring LARGER
    savings. Since in the OVRP s(i,j) = c(depot,j) - lambda*c(i,j) can be
    negative, the window is shifted by the lowest value instead of using abs(),
    which would wrongly favour very negative savings.
    """
    if len(savings) <= 1:
        return list(savings)

    ordered = []
    remaining = list(savings)

    while remaining:
        window = min(size, len(remaining))
        candidates = remaining[:window]

        lowest = min(s.value for s in candidates)
        weights = [s.value - lowest + 1e-9 for s in candidates]
        total = sum(weights)

        r = random.random() * total
        cumulative = 0.0
        idx = window - 1
        for k, w in enumerate(weights):
            cumulative += w
            if r <= cumulative:
                idx = k
                break

        ordered.append(remaining.pop(idx))

    return ordered


def two_phase_selection(
    savings: list[Saving],
    active_stops: set[int],
    ctx: Context,
    iterations: int = ITER_TWO_PHASE,
) -> list[Route]:
    """CW-2 procedure: reorder the savings through the roulette, keep the best."""
    best_routes = _merge(savings, active_stops, ctx)
    best_cost = _obj_total(best_routes)

    current_savings = list(savings)

    for _ in range(iterations):
        # Tournament size T in [3, 6] as in the paper (section 2.3).
        tournament_size = random.randint(
            3, min(6, max(3, len(current_savings)))
        )
        new_order = _roulette_wheel(current_savings, tournament_size)
        new_routes = _merge(new_order, active_stops, ctx)
        new_cost = _obj_total(new_routes)

        if new_cost < best_cost:
            best_cost = new_cost
            best_routes = new_routes
            current_savings = new_order

    return best_routes
