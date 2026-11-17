"""Attendance evaluation and the cut by the available fleet."""

import numpy as np

from algorithms.top_univasf.simulation import simulate_stops
from utils.instances import InstanceData

from .metrics import _route_path
from .model import Attendance, Context, Route


def _instance_from_context(ctx: Context) -> InstanceData:
    """Minimal `InstanceData` for the simulation (it only reads time and demand)."""
    return InstanceData(
        nodes=[], distance=ctx.distance, time=ctx.time, demand=ctx.demand
    )


def _simulated_sequence(ctx: Context, route: Route) -> tuple[int, ...]:
    """Use the same complete path as construction and the time checks."""
    return _route_path(route.stops, ctx, route.origin, route.destination)


def limit_fleet(routes: list[Route], ctx: Context) -> list[Route]:
    """Drop routes until the solution fits the scenario fleet.

    CW does not know the number of vehicles: it opens one route per stop and
    merges while the constraints allow, so it can end up with more routes than
    buses. A route without a vehicle does not operate; this step picks, by
    boarding simulation against the remaining demand, the `ctx.max_routes`
    that serve the most and drops the rest (their demand stays unserved, the
    same way TOP leaves whatever did not board).

    Without a cap (`max_routes is None`), or when the solution already fits,
    it is a no-op.
    """
    if ctx.max_routes is None or len(routes) <= ctx.max_routes:
        return routes

    instance = _instance_from_context(ctx)
    remaining = np.array(ctx.demand, copy=True)
    candidates = list(routes)
    chosen: list[Route] = []

    def simulate(route: Route):
        return simulate_stops(
            instance,
            _simulated_sequence(ctx, route),
            ctx.capacity,
            remaining,
        )

    while candidates and len(chosen) < ctx.max_routes:
        # One simulation per candidate: the winner comes with its outcome.
        outcome, best = max(
            ((simulate(route), route) for route in candidates),
            key=lambda pair: pair[0].passengers,
        )
        for origin, destination, quantity in outcome.pairs:
            remaining[origin, destination] -= quantity
        chosen.append(best)
        candidates = [route for route in candidates if route is not best]

    return chosen


def served_by(routes: list[Route], ctx: Context) -> int:
    """The passengers a set of routes would carry, charging the demand in order.

    The same boarding simulation the report uses, without touching the
    routes: the demand a route picks up leaves the pool for the next one. It
    is the measure the selection steps compare -- the local search asks how
    many passengers a candidate carries before keeping it.
    """
    remaining = np.array(ctx.demand, copy=True)
    instance = _instance_from_context(ctx)
    served = 0
    for route in routes:
        outcome = simulate_stops(
            instance,
            _simulated_sequence(ctx, route),
            ctx.capacity,
            remaining,
        )
        for origin, destination, quantity in outcome.pairs:
            remaining[origin, destination] -= quantity
        served += outcome.passengers
    return served


def evaluate_attendance(routes: list[Route], ctx: Context) -> Attendance:
    """Measure each route's real attendance with the TOP UNIVASF simulation.

    The simulated sequence includes the selected origin, customer stops and
    permitted destination, matching construction and all time checks. Demand
    is charged in order: a pair boarded by one route leaves `remaining` and is
    never counted again by the next one.

    This is NOT a decision criterion: it fills `Route.passengers/peak_load/
    pairs` after the solution is closed.
    """
    remaining = np.array(ctx.demand, copy=True)
    instance = _instance_from_context(ctx)
    all_pairs: list[tuple[int, int, int]] = []

    for route in routes:
        outcome = simulate_stops(
            instance,
            _simulated_sequence(ctx, route),
            ctx.capacity,
            remaining,
        )
        route.passengers = outcome.passengers
        route.peak_load = outcome.peak_load
        route.pairs = tuple(outcome.pairs)
        for origin, destination, quantity in outcome.pairs:
            remaining[origin, destination] -= quantity
        all_pairs.extend(outcome.pairs)

    total = int(ctx.demand.sum())
    served = sum(r.passengers for r in routes)
    unserved = tuple(
        sorted(
            (
                (origin, destination, int(quantity))
                for (origin, destination), quantity in np.ndenumerate(remaining)
                if quantity > 0
            ),
            key=lambda pair: (-pair[2], pair[0], pair[1]),
        )
    )
    return Attendance(
        total_demand=total,
        allocated=sum(r.load for r in routes),
        served=served,
        unserved=total - served,
        peak_load=max((r.peak_load for r in routes), default=0),
        served_pairs=tuple(all_pairs),
        unserved_pairs=unserved,
    )
