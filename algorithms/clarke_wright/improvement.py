"""CW-3 with service-first acceptance and locked, already anchored endpoints."""

import random
from dataclasses import replace
from .constants import ITER_POSTIMPROVE
from .construction import _best_direction
from .context import route_load
from .metrics import _update_route
from .model import Context, Route
from .objective import exact_key


def _copy_route(route: Route) -> Route:
    return replace(route, stops=list(route.stops))


def _trial(route: Route, stops, ctx: Context) -> Route | None:
    result = _copy_route(route)
    if not route.anchored:
        stops = _best_direction(stops, ctx)
    _update_route(result, list(stops), route_load(stops, ctx), ctx)
    return result if ctx.fits(result.load, result.time_minutes) else None


def _try_move(routes, a, b, new_a, new_b, load_a, load_b, ctx):
    """Accept only a strict improvement of global exact (-served, cost)."""
    ra, rb = _trial(routes[a], new_a, ctx), _trial(routes[b], new_b, ctx)
    if ra is None or rb is None:
        return False
    candidate = list(routes)
    candidate[a], candidate[b] = ra, rb
    if exact_key(candidate, ctx) >= exact_key(routes, ctx):
        return False
    routes[a], routes[b] = ra, rb
    return True


def _two_opt_route(route: Route, ctx: Context) -> Route:
    route = _copy_route(route)
    while True:
        best = route
        best_key = exact_key([route], ctx)
        for i in range(len(route.stops) - 1):
            for j in range(i + 2, len(route.stops) + 1):
                stops = route.stops[:i] + route.stops[i:j][::-1] + route.stops[j:]
                candidate = _trial(route, stops, ctx)
                if candidate is not None:
                    key = exact_key([candidate], ctx)
                    if key < best_key:
                        best, best_key = candidate, key
        if best is route:
            return route
        route = best


def _shift_10(routes: list[Route], ctx: Context) -> list[Route]:
    while True:
        changed = False
        for a in range(len(routes)):
            for i in range(len(routes[a].stops)):
                for b in range(len(routes)):
                    if a == b:
                        continue
                    for j in range(len(routes[b].stops) + 1):
                        new_a = routes[a].stops[:i] + routes[a].stops[i + 1:]
                        if not new_a and not routes[a].anchored:
                            continue
                        new_b = routes[b].stops[:j] + [routes[a].stops[i]] + routes[b].stops[j:]
                        if _try_move(routes, a, b, new_a, new_b, 0, 0, ctx):
                            changed = True
                            break
                    if changed: break
                if changed: break
            if changed: break
        if not changed:
            return routes


def _swap_11(routes: list[Route], ctx: Context) -> list[Route]:
    while True:
        changed = False
        for a in range(len(routes)):
            for b in range(a + 1, len(routes)):
                for i in range(len(routes[a].stops)):
                    for j in range(len(routes[b].stops)):
                        new_a, new_b = list(routes[a].stops), list(routes[b].stops)
                        new_a[i], new_b[j] = new_b[j], new_a[i]
                        if _try_move(routes, a, b, new_a, new_b, 0, 0, ctx):
                            changed = True
                            break
                    if changed: break
                if changed: break
            if changed: break
        if not changed:
            return routes


def post_improvement(routes, ctx, max_iterations_without_improvement=ITER_POSTIMPROVE):
    """Reject service regressions and never mutate the incumbent on rejection.

    Stop early if all exhaustive neighborhoods are exhausted for this incumbent;
    repeating them 500 times cannot find a new move.
    """
    routes = [_copy_route(r) for r in routes]
    best_key = exact_key(routes, ctx)
    operators = [lambda rs: [_two_opt_route(r, ctx) for r in rs],
                 lambda rs: _shift_10(rs, ctx), lambda rs: _swap_11(rs, ctx)]
    exhausted, failures = set(), 0
    while failures < max_iterations_without_improvement and len(exhausted) < len(operators):
        index = random.choice([i for i in range(len(operators)) if i not in exhausted])
        candidates = operators[index]([_copy_route(r) for r in routes])
        key = exact_key(candidates, ctx)
        if key < best_key:
            routes, best_key = candidates, key
            exhausted.clear()
            failures = 0
        else:
            exhausted.add(index)
            failures += 1
    return routes
