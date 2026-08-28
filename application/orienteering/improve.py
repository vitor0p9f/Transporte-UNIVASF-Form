from __future__ import annotations

from collections.abc import Sequence

from application.orienteering.judge import judge_route
from application.orienteering.models import DemandState, RouteSimulation
from application.orienteering.simulation import simulate_route
from domain.entities.bus import Bus
from domain.entities.graph import Graph


def _two_opt_candidates(route_stops: Sequence[str]) -> tuple[tuple[str, ...], ...]:
    route = tuple(route_stops)
    return tuple(
        (*route[:i], *reversed(route[i:j]), *route[j:])
        for i in range(1, len(route) - 1)
        for j in range(i + 1, len(route))
    )


def _is_better(candidate: RouteSimulation, current: RouteSimulation) -> bool:
    return (candidate.served_passengers, -candidate.travel_time_minutes) > (
        current.served_passengers,
        -current.travel_time_minutes,
    )


def improve_route_with_two_opt(
    graph: Graph,
    demand_state: DemandState,
    route_stops: Sequence[str],
    bus: Bus,
    time_limit_minutes: int,
) -> tuple[str, ...]:
    route = tuple(route_stops)
    simulation = simulate_route(graph, demand_state, route)

    while True:
        best_route = route
        best_simulation = simulation
        accepted = False

        for candidate in _two_opt_candidates(route):
            candidate_simulation = simulate_route(graph, demand_state, candidate)
            if not judge_route(candidate_simulation, bus, time_limit_minutes):
                continue
            if _is_better(candidate_simulation, best_simulation):
                best_route = candidate
                best_simulation = candidate_simulation
                accepted = True

        if not accepted:
            return route
        route = best_route
        simulation = best_simulation