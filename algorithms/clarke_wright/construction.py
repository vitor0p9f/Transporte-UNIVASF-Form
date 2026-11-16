"""OVRP construction: route merging, direction choice and two-phase selection."""

import random
import numpy as np
from dataclasses import replace

from .constants import ITER_TWO_PHASE
from .context import route_load
from .metrics import _route_distance, _route_time, _update_cost
from .model import Context, Route, Saving
from .objective import _obj_total, service_bound, solution_key, exact_key


def _best_direction(stops: list[int], ctx: Context) -> list[int]:
    """CW-2 procedure: try both directions of the open route.

    Each order independently selects its permitted origin and destination:
      forward : origin -> p1 -> p2 -> ... -> pn -> destination
      reverse : origin -> pn -> p(n-1) -> ... -> p1 -> destination

    With the time constraint active both access and terminal legs count, so
    directions that already break the limit are
    dropped before picking the shortest one. If none fits, the shortest one is
    returned and the caller rejects the route through `Context.fits`.
    """
    cache = ctx._cache.setdefault('directions', {})
    key = tuple(stops)
    if key in cache:
        return list(cache[key])
    directions = [list(stops), list(reversed(stops))]
    if ctx.restrictions.time:
        feasible = [d for d in directions if _route_time(d, ctx) <= ctx.max_time]
        if feasible:
            directions = feasible
    result = min(directions, key=lambda d: _route_distance(d, ctx))
    cache[key] = tuple(result)
    return result


def _merge(
    savings: list[Saving],
    active_stops: set[int],
    ctx: Context,
    *,
    _reuse: bool = False,
) -> list[Route]:
    """Merging procedure of the parallel Clarke-Wright.

    For every saving s(i,j) in descending order:
      - if i and j sit in different routes
      - if the merge does not break the active constraint(s) (capacity/time)
      - if i is an endpoint (start or end) of its route
      - if j is an endpoint of its route
      -> merge the routes

    With endpoint constraints, an infeasible complete singleton is left
    unserved. The legacy unrestricted-end API retains its singleton behavior.
    """
    # Initial solution: one route per stop
    cache = ctx._cache.setdefault('merge_routes', {})
    ordered_cache = ctx._cache.setdefault('merge_orders', {})
    load_cache = ctx._cache.setdefault('loads', {})
    initial_key = tuple(sorted(active_stops))
    initial_cache = ctx._cache.setdefault('initial_routes', {})
    if initial_key not in initial_cache:
        initial = {}
        for p in initial_key:
            r = _update_cost(Route(stops=[p], load=route_load([p], ctx), load_mask=ctx.touch_masks[p], node_mask=1 << p), ctx)
            if (ctx.origins or ctx.destinations) and not ctx.fits(r.load, r.time_minutes):
                continue
            initial[p] = r
        initial_cache[initial_key] = initial
    routes = dict(initial_cache[initial_key])
    endpoint = dict(routes)

    for s in savings:
        ri = endpoint.get(s.i)
        rj = endpoint.get(s.j)

        if ri is None or rj is None or ri is rj:
            continue

        mask = ri.load_mask | rj.load_mask
        if ctx.od_quantities and mask in load_cache:
            load = load_cache[mask]
        else:
            load = route_load((*ri.stops, *rj.stops), ctx)
        if ctx.restrictions.capacity and load > ctx.capacity:
            continue

        new_order = None

        ri_first, ri_last = ri.stops[0], ri.stops[-1]
        rj_first, rj_last = rj.stops[0], rj.stops[-1]
        if ri_last == s.i and rj_first == s.j:
            new_order = ri.stops + rj.stops
        elif rj_last == s.j and ri_first == s.i:
            new_order = rj.stops + ri.stops
        elif ri_last == s.i and rj_last == s.j:
            new_order = ri.stops + list(reversed(rj.stops))
        elif ri_first == s.i and rj_first == s.j:
            new_order = list(reversed(ri.stops)) + rj.stops

        if new_order is None:
            continue

        order_key = tuple(new_order)
        if order_key not in ordered_cache:
            new_order = _best_direction(new_order, ctx)
            key = tuple(new_order)
            if key not in cache:
                trial = _update_cost(Route(stops=new_order, load=load, load_mask=mask, node_mask=ri.node_mask | rj.node_mask), ctx)
                cache[key] = trial if ctx.fits(load, trial.time_minutes) else None
            ordered_cache[order_key] = cache[key]
        new_route = ordered_cache[order_key]
        if new_route is None:
            continue

        # Drop the merged routes (by identity: `Route` compares by value)
        routes.pop(ri_first)
        routes.pop(rj_first)
        for p in (ri_first, ri_last, rj_first, rj_last):
            endpoint.pop(p, None)

        # Register the new route
        routes[new_route.stops[0]] = new_route
        endpoint[new_route.stops[0]] = new_route
        endpoint[new_route.stops[-1]] = new_route

    result = list(routes.values())
    return result if _reuse else [replace(r, stops=list(r.stops)) for r in result]


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
    remaining = list(savings[:size])
    next_index = len(remaining)

    while remaining:
        window = len(remaining)
        candidates = remaining

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
        if next_index < len(savings):
            remaining.append(savings[next_index])
            next_index += 1

    return ordered


def two_phase_selection(
    savings: list[Saving],
    active_stops: set[int],
    ctx: Context,
    iterations: int = ITER_TWO_PHASE,
    selection_ctx: Context | None = None,
    finalize=None,
) -> list[Route]:
    """CW-2 procedure: reorder the savings through the roulette, keep the best."""
    best_routes = _merge(savings, active_stops, ctx, _reuse=True)
    selection_ctx = selection_ctx or ctx
    best_key = solution_key(service_bound(best_routes, selection_ctx), _obj_total(best_routes))
    finalists = [best_routes]

    current_savings = list(savings)
    rng = np.random.default_rng(random.getrandbits(64))
    tables = {}

    for _ in range(iterations):
        # Bounded tournament size of this baseline adaptation.
        tournament_size = random.randint(
            3, min(6, max(3, len(current_savings)))
        )
        # Weighted sampling without replacement inside bounded tournaments.
        # Exponential races give the roulette probabilities, vectorized by
        # numpy. These are fixed groups, not the old sliding Python window;
        # this sampling adaptation is documented as part of the baseline.
        if tournament_size not in tables:
            n = len(current_savings)
            padded = ((n + tournament_size - 1) // tournament_size) * tournament_size
            values = np.full(padded, np.inf)
            values[:n] = [s.value for s in current_savings]
            values = values.reshape(-1, tournament_size)
            weights = values - values.min(axis=1, keepdims=True) + 1e-9
            weights[~np.isfinite(weights)] = 0.0
            tables[tournament_size] = (weights, np.arange(padded).reshape(weights.shape))
        weights, indices = tables[tournament_size]
        races = rng.exponential(size=weights.shape) / np.where(weights > 0, weights, np.inf)
        races[weights == 0] = np.inf
        permuted = np.take_along_axis(indices, races.argsort(axis=1, kind='stable'), axis=1).ravel()
        new_order = [current_savings[int(i)] for i in permuted if i < len(current_savings)]
        new_routes = _merge(new_order, active_stops, ctx, _reuse=True)
        new_key = solution_key(service_bound(new_routes, selection_ctx), _obj_total(new_routes))

        if new_key < best_key:
            best_key = new_key
            best_routes = new_routes
            current_savings = new_order
            tables.clear()
            finalists.append(best_routes)

    # The bound may overestimate service. Exact final selection keeps the
    # initial construction as a fallback, preventing a bound-only regression.
    finalize = finalize or (lambda routes: exact_key(routes, selection_ctx))
    best_routes = min(finalists, key=finalize)
    return [replace(r, stops=list(r.stops)) for r in best_routes]
