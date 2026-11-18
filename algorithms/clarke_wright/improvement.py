"""Post-improvement local search (CW-3)."""

import random

from .constants import ITER_POSTIMPROVE
from .construction import _best_direction, _projected_load, _stored_load
from .evaluation import served_by
from .metrics import _route_cost, _route_time, _update_cost, _update_route
from .model import Context, Route
from .objective import _obj_total, solution_key


def _try_move(
    routes: list[Route],
    a: int,
    b: int,
    new_a: list[int],
    new_b: list[int],
    ctx: Context,
) -> bool:
    """Commit a move of the pair (a, b) when it is legal, cheaper and safe.

    Both inter-route operators end the same way: take the best direction of
    each new route, keep the pair only if the active constraints accept it,
    and commit only if the pair's operating cost (fuel + driver) drops. The
    comparison is against the routes' current cost, so the caller does not have
    to read it beforehand.

    A move that would carry fewer passengers is rejected: the selection
    criterion of the heuristic is the attendance, so the local search may
    never lose passengers to gain cost.
    """
    new_a = _best_direction(new_a, ctx, routes[a].origin, routes[a].destination)
    new_b = _best_direction(new_b, ctx, routes[b].origin, routes[b].destination)

    load_a = _projected_load(new_a, ctx)
    load_b = _projected_load(new_b, ctx)
    # The candidates keep the anchored endpoints: computing them again by
    # distance here would measure (and commit) a different route than the one
    # the report shows.
    candidate_a = _update_cost(
        Route(
            stops=list(new_a),
            load=_stored_load(new_a, ctx),
            origin=routes[a].origin,
            destination=routes[a].destination,
        ),
        ctx,
    )
    candidate_b = _update_cost(
        Route(
            stops=list(new_b),
            load=_stored_load(new_b, ctx),
            origin=routes[b].origin,
            destination=routes[b].destination,
        ),
        ctx,
    )
    if not (
        ctx.fits(load_a, candidate_a.time_minutes)
        and ctx.fits(load_b, candidate_b.time_minutes)
    ):
        return False

    cost_before = routes[a].cost_brl + routes[b].cost_brl
    cost_after = candidate_a.cost_brl + candidate_b.cost_brl
    if cost_after >= cost_before - 1e-6:
        return False

    if served_by([candidate_a, candidate_b], ctx) < served_by(
        [routes[a], routes[b]], ctx
    ):
        return False

    _update_route(routes[a], new_a, candidate_a.load, ctx)
    _update_route(routes[b], new_b, candidate_b.load, ctx)
    return True


def _two_opt_route(route: Route, ctx: Context) -> Route:
    """Intra-route 2-opt: reverse inner segments and keep the best.

    Applies CW-2 (best direction) after every improvement.

    The load does not change, but the cost can: a segment reversal changes both
    the fuel and the minutes the driver is paid for, so the candidates are
    compared by the operating cost (fuel + driver). With the time constraint
    active, a candidate that breaks the limit is dropped before the comparison.
    """
    stops = list(route.stops)
    origin = route.origin
    destination = route.destination

    improved = True
    while improved:
        improved = False
        current_cost = _route_cost(stops, ctx, origin, destination)
        for i in range(len(stops) - 1):
            for j in range(i + 2, len(stops)):
                new_stops = (
                    stops[: i + 1]
                    + list(reversed(stops[i + 1 : j + 1]))
                    + stops[j + 1 :]
                )
                new_stops = _best_direction(new_stops, ctx, origin, destination)
                if not ctx.fits(
                    route.load, _route_time(new_stops, ctx, origin, destination)
                ):
                    continue
                new_cost = _route_cost(new_stops, ctx, origin, destination)
                if new_cost < current_cost - 1e-6:
                    stops = new_stops
                    current_cost = new_cost
                    improved = True

    route.stops = stops
    return _update_cost(route, ctx)


def _shift_10(
    routes: list[Route],
    ctx: Context,
) -> list[Route]:
    """Shift 1-0: move one stop from one route to another.

    Accepted when it does not break the active constraint(s) and it lowers the
    objective (fuel + driver cost) without losing passengers.
    """
    improved = True
    while improved:
        improved = False
        for a in range(len(routes)):
            for pos_i in range(len(routes[a].stops)):
                stop = routes[a].stops[pos_i]

                for b in range(len(routes)):
                    if a == b:
                        continue

                    # Try inserting at the start and at the end of route b
                    for pos_j in (0, len(routes[b].stops)):
                        new_a = list(routes[a].stops)
                        new_a.pop(pos_i)
                        if not new_a:
                            continue  # never leave a route empty
                        new_b = list(routes[b].stops)
                        new_b.insert(pos_j, stop)

                        if _try_move(routes, a, b, new_a, new_b, ctx):
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
    objective (fuel + driver cost) without losing passengers.
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

                        new_a = list(routes[a].stops)
                        new_b = list(routes[b].stops)
                        new_a[pos_i] = stop_j
                        new_b[pos_j] = stop_i

                        if _try_move(routes, a, b, new_a, new_b, ctx):
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

    Every attempt runs on a copy, and the solution kept is the one that
    carries the most passengers, with the operating cost (fuel + driver) as the
    tie-break -- the same criterion the other selection steps use.
    """
    best_routes = [_copy_route(r) for r in routes]
    best_key = solution_key(served_by(best_routes, ctx), _obj_total(best_routes))
    iterations_without_improvement = 0

    operators = [
        lambda r: [_two_opt_route(x, ctx) for x in r],
        lambda r: _shift_10(r, ctx),
        lambda r: _swap_11(r, ctx),
    ]

    while iterations_without_improvement < max_iterations_without_improvement:
        operator = random.choice(operators)
        candidate = operator([_copy_route(r) for r in best_routes])
        key = solution_key(served_by(candidate, ctx), _obj_total(candidate))

        if key < best_key:
            best_key = key
            best_routes = candidate
            iterations_without_improvement = 0
        else:
            iterations_without_improvement += 1

    return best_routes


def _copy_route(route: Route) -> Route:
    """Copy of the route: the CW-3 operators mutate it in place."""
    return Route(
        stops=list(route.stops),
        load=route.load,
        distance_km=route.distance_km,
        time_minutes=route.time_minutes,
        cost_brl=route.cost_brl,
        origin=route.origin,
        destination=route.destination,
    )
