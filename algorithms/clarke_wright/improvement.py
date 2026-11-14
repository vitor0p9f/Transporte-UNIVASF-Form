"""Post-improvement local search (CW-3)."""

import random

from .constants import ITER_POSTIMPROVE
from .construction import _best_direction
from .metrics import _route_distance, _route_time, _update_cost, _update_route
from .model import Context, Route
from .objective import _obj_total


def _try_move(
    routes: list[Route],
    a: int,
    b: int,
    new_a: list[int],
    new_b: list[int],
    load_a: int,
    load_b: int,
    ctx: Context,
) -> bool:
    """Commit a move of the pair (a, b) when it is legal and cheaper.

    Both inter-route operators end the same way: take the best direction of each
    new route, keep the pair only if the active constraints accept it, and
    commit only if the pair's fuel cost drops. The comparison is against the
    routes' current cost, so the caller does not have to read it beforehand.
    """
    new_a = _best_direction(new_a, ctx)
    new_b = _best_direction(new_b, ctx)
    if not (
        ctx.fits(load_a, _route_time(new_a, ctx))
        and ctx.fits(load_b, _route_time(new_b, ctx))
    ):
        return False

    cost_before = routes[a].cost_brl + routes[b].cost_brl
    cost_after = ctx.bus_model.route_cost(
        _route_distance(new_a, ctx)
    ) + ctx.bus_model.route_cost(_route_distance(new_b, ctx))
    if cost_after >= cost_before - 1e-6:
        return False

    _update_route(routes[a], new_a, load_a, ctx)
    _update_route(routes[b], new_b, load_b, ctx)
    return True


def _two_opt_route(route: Route, ctx: Context) -> Route:
    """Intra-route 2-opt: reverse inner segments and keep the best.

    Applies CW-2 (best direction) after every improvement.

    The load does not change, but the time can: with the constraint active, a
    candidate that breaks the limit is dropped (a shorter distance does not
    guarantee a shorter time).
    """
    stops = list(route.stops)

    improved = True
    while improved:
        improved = False
        current_distance = _route_distance(stops, ctx)
        for i in range(len(stops) - 1):
            for j in range(i + 2, len(stops)):
                new_stops = (
                    stops[: i + 1]
                    + list(reversed(stops[i + 1 : j + 1]))
                    + stops[j + 1 :]
                )
                new_stops = _best_direction(new_stops, ctx)
                if not ctx.fits(route.load, _route_time(new_stops, ctx)):
                    continue
                new_distance = _route_distance(new_stops, ctx)
                if new_distance < current_distance - 1e-6:
                    stops = new_stops
                    current_distance = new_distance
                    improved = True

    route.stops = stops
    return _update_cost(route, ctx)


def _shift_10(
    routes: list[Route],
    ctx: Context,
) -> list[Route]:
    """Shift 1-0: move one stop from one route to another.

    Accepted when it does not break the active constraint(s) and it lowers the
    objective (fuel cost). Updates the route loads.
    """
    improved = True
    while improved:
        improved = False
        for a in range(len(routes)):
            for pos_i in range(len(routes[a].stops)):
                stop = routes[a].stops[pos_i]
                delta = ctx.stop_loads.get(stop, 0)

                for b in range(len(routes)):
                    if a == b:
                        continue

                    load_a = routes[a].load - delta
                    load_b = routes[b].load + delta
                    if ctx.restrictions.capacity and load_b > ctx.capacity:
                        continue

                    # Try inserting at the start and at the end of route b
                    for pos_j in (0, len(routes[b].stops)):
                        new_a = list(routes[a].stops)
                        new_a.pop(pos_i)
                        if not new_a:
                            continue  # never leave a route empty
                        new_b = list(routes[b].stops)
                        new_b.insert(pos_j, stop)

                        if _try_move(
                            routes, a, b, new_a, new_b, load_a, load_b, ctx
                        ):
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break

    return routes


def _swap_11(
    routes: list[Route],
    ctx: Context,
) -> list[Route]:
    """Swap 1-1: exchange one stop between two routes.

    Accepted when it does not break the active constraint(s) and it lowers the
    objective (fuel cost). Updates the route loads.
    """
    improved = True
    while improved:
        improved = False
        for a in range(len(routes)):
            for b in range(a + 1, len(routes)):
                for pos_i in range(len(routes[a].stops)):
                    for pos_j in range(len(routes[b].stops)):
                        stop_i = routes[a].stops[pos_i]
                        stop_j = routes[b].stops[pos_j]
                        stop_load_i = ctx.stop_loads.get(stop_i, 0)
                        stop_load_j = ctx.stop_loads.get(stop_j, 0)

                        load_a = routes[a].load - stop_load_i + stop_load_j
                        load_b = routes[b].load - stop_load_j + stop_load_i
                        if ctx.restrictions.capacity and (
                            load_a > ctx.capacity
                            or load_b > ctx.capacity
                        ):
                            continue

                        new_a = list(routes[a].stops)
                        new_b = list(routes[b].stops)
                        new_a[pos_i] = stop_j
                        new_b[pos_j] = stop_i

                        if _try_move(
                            routes, a, b, new_a, new_b, load_a, load_b, ctx
                        ):
                            improved = True
                            break
                    if improved:
                        break
                if improved:
                    break
            if improved:
                break

    return routes


def post_improvement(
    routes: list[Route],
    ctx: Context,
    max_iterations_without_improvement: int = ITER_POSTIMPROVE,
) -> list[Route]:
    """CW-3 procedure: run local search until it stops improving.

    Operators (with equal probability, following Table 1 of the paper):
      - intra-route 2-opt
      - inter-route shift 1-0
      - inter-route swap 1-1
    """
    routes = [_copy_route(r) for r in routes]
    best_cost = _obj_total(routes)
    iterations_without_improvement = 0

    operators = [
        lambda r: [_two_opt_route(x, ctx) for x in r],
        lambda r: _shift_10(r, ctx),
        lambda r: _swap_11(r, ctx),
    ]

    while iterations_without_improvement < max_iterations_without_improvement:
        operator = random.choice(operators)
        new_routes = operator(routes)
        new_cost = _obj_total(new_routes)

        if new_cost < best_cost - 1e-6:
            best_cost = new_cost
            routes = new_routes
            iterations_without_improvement = 0
        else:
            iterations_without_improvement += 1

    return routes


def _copy_route(route: Route) -> Route:
    """Copy of the route: the CW-3 operators mutate it in place."""
    return Route(
        stops=list(route.stops),
        load=route.load,
        distance_km=route.distance_km,
        time_minutes=route.time_minutes,
        cost_brl=route.cost_brl,
    )
