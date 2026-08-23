from __future__ import annotations

from collections.abc import Sequence

from application.orienteering.commit import commit_served_demand
from application.orienteering.judge import judge_competing_candidates, judge_route
from application.orienteering.models import CandidateEvaluation, DemandState
from application.orienteering.prize import calculate_node_prize
from application.orienteering.simulation import simulate_route
from application.orienteering.state import candidate_labels_for_demand
from domain.entities.bus import Bus
from domain.entities.graph import Graph


def candidate_labels_for_route(
    demand_state: DemandState,
    route_stops: Sequence[str],
) -> tuple[str, ...]:
    return candidate_labels_for_demand(demand_state, route_stops)


def _insertion_routes(
    route_stops: Sequence[str],
    candidate_label: str,
) -> tuple[tuple[str, ...], ...]:
    if len(route_stops) < 2:
        raise ValueError("route_stops must contain at least an origin and a destination")

    if candidate_label in route_stops:
        raise ValueError("candidate_label cannot already be part of route_stops")

    base = tuple(route_stops)
    return tuple(
        (*base[:index], candidate_label, *base[index:])
        for index in range(1, len(base))
    )


def _evaluation_key(evaluation: CandidateEvaluation) -> tuple:
    return (
        int(evaluation.feasible),
        evaluation.prize,
        evaluation.simulation.served_passengers,
        -evaluation.simulation.travel_time_minutes,
        -evaluation.bus_index,
        evaluation.candidate_label,
    )


def evaluate_candidate(
    graph: Graph,
    demand_state: DemandState,
    bus: Bus,
    route_stops: Sequence[str],
    candidate_label: str,
    time_limit_minutes: int,
    *,
    alpha: float = 1.0,
    bus_index: int = 0,
    full_demand_state: DemandState | None = None,
) -> CandidateEvaluation:
    evaluations: list[CandidateEvaluation] = []

    for inserted_route in _insertion_routes(route_stops, candidate_label):
        simulation = simulate_route(
            graph,
            demand_state,
            inserted_route,
            full_demand_state=full_demand_state,
        )
        feasible = judge_route(simulation, bus, time_limit_minutes)
        evaluations.append(
            CandidateEvaluation(
                bus_index=bus_index,
                candidate_label=candidate_label,
                route_stops=inserted_route,
                prize=calculate_node_prize(simulation, alpha),
                feasible=feasible,
                simulation=simulation,
            )
        )

    if not evaluations:
        raise ValueError("No insertion positions available for the candidate")

    return max(evaluations, key=_evaluation_key)


def rank_candidates(
    graph: Graph,
    demand_state: DemandState,
    bus: Bus,
    route_stops: Sequence[str],
    time_limit_minutes: int,
    *,
    candidate_labels: Sequence[str] | None = None,
    alpha: float = 1.0,
    bus_index: int = 0,
    full_demand_state: DemandState | None = None,
) -> list[CandidateEvaluation]:
    labels = (
        tuple(candidate_labels)
        if candidate_labels is not None
        else candidate_labels_for_route(demand_state, route_stops)
    )

    ranked = [
        evaluate_candidate(
            graph,
            demand_state,
            bus,
            route_stops,
            candidate_label,
            time_limit_minutes,
            alpha=alpha,
            bus_index=bus_index,
            full_demand_state=full_demand_state,
        )
        for candidate_label in labels
    ]

    return sorted(ranked, key=_evaluation_key, reverse=True)


def calculate_candidate_prizes(
    graph: Graph,
    demand_state: DemandState,
    bus: Bus,
    route_stops: Sequence[str],
    time_limit_minutes: int,
    *,
    candidate_labels: Sequence[str] | None = None,
    alpha: float = 1.0,
    bus_index: int = 0,
    full_demand_state: DemandState | None = None,
) -> tuple[DemandState, list[CandidateEvaluation], CandidateEvaluation | None]:
    ranking = rank_candidates(
        graph,
        demand_state,
        bus,
        route_stops,
        time_limit_minutes,
        candidate_labels=candidate_labels,
        alpha=alpha,
        bus_index=bus_index,
        full_demand_state=full_demand_state,
    )
    best = judge_competing_candidates(ranking, require_feasible=True)

    if best is None:
        return commit_served_demand(demand_state, {}), ranking, None

    served_pairs = {
        (origin, destination): quantity
        for origin, destination, quantity in best.simulation.served_pairs
    }
    return commit_served_demand(demand_state, served_pairs), ranking, best
