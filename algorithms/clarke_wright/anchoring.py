"""Anchoring the built routes on the scenario's origins and destinations.

The construction merges the stops around the reference depot and leaves each
route ending wherever the merge stopped. The scenario, on the other hand, says
which nodes a route may start at and which it may end at -- the same contract
TOP UNIVASF follows.

This module is the step that closes that gap: it does NOT change how the
routes were built (the stops and their order are untouched), it only picks the
endpoints each route drives from and to.
"""

import numpy as np

from algorithms.top_univasf.simulation import simulate_stops
from utils.paths import path_distance, path_time_minutes

from .construction import _projected_load
from .evaluation import _instance_from_context
from .metrics import _route_path, _update_cost
from .model import Context, Route
from .objective import solution_key


def _candidates(ctx: Context) -> list[tuple[int, int | None]]:
    """The (origin, destination) pairs a route may use.

    An empty origin set means the depot only; an empty destination set means
    the free end (the route stops at its last stop).
    """
    origins = ctx.origins or (ctx.depot,)
    destinations = ctx.destinations or (None,)
    return [(origin, destination) for origin in origins for destination in destinations]


def anchor_routes(routes: list[Route], ctx: Context) -> list[Route]:
    """Give every route the origin and the destination the scenario allows.

    Every candidate pair is simulated (the same boarding simulation that
    measures the attendance) against the demand that is still free, and the
    one that carries the most passengers wins; the operating cost (fuel +
    driver), the distance and the node labels are the tie-breaks, and they keep
    the choice deterministic.

    The demand served by an anchored route is charged before the next route is
    anchored, which is what spreads the origins across the solution instead of
    piling every route on the depot the construction used.

    The route keeps its stops and their order: only the endpoints and the
    measures that depend on them (distance, time and cost) are recomputed.
    """
    instance = _instance_from_context(ctx)
    remaining = np.array(ctx.demand, copy=True)
    anchored: list[Route | None] = [None] * len(routes)

    # The routes with more stops first: they carry more demand and deserve the
    # first pick of it. The order is stable, so the result is reproducible.
    order = sorted(
        range(len(routes)),
        key=lambda index: (-len(routes[index].stops), routes[index].stops),
    )

    for index in order:
        route = routes[index]
        load = _projected_load(route.stops, ctx)
        best: tuple[tuple, int, int | None, tuple[int, ...], object] | None = None

        for origin, destination in _candidates(ctx):
            path = _route_path(route.stops, ctx, origin, destination)
            minutes = path_time_minutes(ctx.time, path)
            if not ctx.fits(load, minutes):
                continue

            outcome = simulate_stops(instance, path, ctx.capacity, remaining)
            distance = path_distance(ctx.distance, path)
            cost = ctx.bus_model.route_cost(distance, minutes)
            key = solution_key(outcome.passengers, cost) + (
                cost,
                distance,
                origin,
                -1 if destination is None else destination,
            )
            if best is None or key < best[0]:
                best = (key, origin, destination, path, outcome)

        if best is None:
            # No candidate fits the time limit: the route keeps the endpoints
            # it was built with.
            anchored[index] = route
            continue

        _, origin, destination, path, outcome = best
        for pair_origin, pair_destination, quantity in outcome.pairs:
            remaining[pair_origin, pair_destination] -= quantity

        route.origin = origin
        route.destination = destination if destination is not None else path[-1]
        _update_cost(route, ctx)
        anchored[index] = route

    return [route for route in anchored if route is not None]
