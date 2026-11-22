"""OVRP construction: route merging, direction choice and two-phase selection."""

import random

from .constants import ITER_TWO_PHASE
from .metrics import (
    _route_operational_cost,
    _route_path,
    _route_time,
    _update_cost,
)
from .model import Context, Route, Saving
from .objective import (
    _obj_total,
    estimated_served,
    served_bound,
    solution_key,
)


def _projected_load(stops: list[int], ctx: Context) -> int:
    """The CVRP load of a route: the demand that boards at its stops.

    The per-node projection the context carries, summed over the route -- the
    constraint of the original algorithm, adapted to the pickup-and-delivery
    demand. It is compared with the capacity as it is: capping it would hide
    the routes that do not fit.
    """
    return sum(ctx.stop_loads.get(stop, 0) for stop in stops)


def _stored_load(stops: list[int], ctx: Context) -> int:
    """The load the model reports: the projection, capped by one bus.

    A single bus cannot allocate more than its own capacity, so the reported
    value stops there; the merge still compares the uncapped projection.
    """
    load = _projected_load(stops, ctx)
    return min(load, ctx.capacity) if ctx.restrictions.capacity else load


def _best_direction(
    stops: list[int],
    ctx: Context,
    origin: int | None = None,
    destination: int | None = None,
) -> list[int]:
    """CW-2 procedure: try both directions of the open route.

    Each order independently selects its permitted origin and destination:
      forward : origin -> p1 -> p2 -> ... -> pn -> destination
      reverse : origin -> pn -> p(n-1) -> ... -> p1 -> destination

    With the time constraint active both access and terminal legs count, so
    directions that already break the limit are
    dropped before picking the cheapest one. If none fits, the cheapest one is
    returned and the caller rejects the route through `Context.fits`.

    Adaptation to the pickup-and-delivery problem: a passenger only boards
    when the bus reaches the origin before the destination, so the direction
    that carries more passengers comes first. The operational cost
    (fuel + driver) is the tie-break.
    """
    directions = [list(stops), list(reversed(stops))]
    if ctx.restrictions.time:
        feasible = [
            d
            for d in directions
            if _route_time(d, ctx, origin, destination) <= ctx.max_time
        ]
        if feasible:
            directions = feasible
    return min(
        directions,
        key=lambda d: (
            -served_bound(_route_path(d, ctx, origin, destination), ctx.demand),
            _route_operational_cost(d, ctx, origin, destination),
            d,
        ),
    )


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

    With endpoint constraints, an infeasible complete singleton is left
    unserved. A singleton that already breaks the time limit is not a route
    either: it is dropped before the merges, whatever the endpoints.

    The capacity is the CVRP constraint of the original algorithm, projected on
    the OD demand: the route cannot hold more passengers than the seats it has,
    and the demand of its stops is what it would have to carry.
    """
    # Initial solution: one route per stop
    routes: list[Route] = []
    endpoint: dict[int, Route] = {}  # endpoint -> the route holding it

    for p in sorted(active_stops):  # fixed order -> reproducible result
        r = Route(stops=[p], load=_stored_load([p], ctx))
        _update_cost(r, ctx)
        if ctx.restrictions.time and r.time_minutes > ctx.max_time:
            continue
        routes.append(r)
        endpoint[p] = r

    for s in savings:
        ri = endpoint.get(s.i)
        rj = endpoint.get(s.j)

        if ri is None or rj is None or ri is rj:
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

        load = _projected_load(new_order, ctx)
        if ctx.restrictions.capacity and load > ctx.capacity:
            continue
        if not ctx.fits(load, _route_time(new_order, ctx)):
            continue

        new_route = Route(stops=new_order, load=_stored_load(new_order, ctx))
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
    """CW-2 procedure: reorder the savings through the roulette, keep the best.

    The best solution is the one that carries the most passengers (the
    boarding simulation is too slow to run on every iteration, so the search
    ranks the candidates by the demand each route holds), with the operational
    cost (fuel + driver) as the tie-break.
    """
    best_routes = _merge(savings, active_stops, ctx)
    best_key = solution_key(
        estimated_served(best_routes, ctx), _obj_total(best_routes)
    )

    current_savings = list(savings)

    for _ in range(iterations):
        # Tournament size T in [3, 6] as in the paper (section 2.3).
        tournament_size = random.randint(
            3, min(6, max(3, len(current_savings)))
        )
        new_order = _roulette_wheel(current_savings, tournament_size)
        new_routes = _merge(new_order, active_stops, ctx)
        new_key = solution_key(
            estimated_served(new_routes, ctx), _obj_total(new_routes)
        )

        if new_key < best_key:
            best_key = new_key
            best_routes = new_routes
            current_savings = new_order

    return best_routes
