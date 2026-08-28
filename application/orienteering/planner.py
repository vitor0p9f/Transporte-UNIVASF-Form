from __future__ import annotations

from collections.abc import Sequence

from application.orienteering.commit import commit_served_demand
from application.orienteering.judge import judge_competing_candidates, judge_route
from application.orienteering.models import CandidateEvaluation, DemandState
from application.orienteering.prize import DENSITY, prize_for
from application.orienteering.ranking import evaluation_sort_key
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
    *,
    allow_terminal_position: bool = False,
) -> tuple[tuple[str, ...], ...]:
    if len(route_stops) < 1:
        raise ValueError("route_stops must contain at least an origin")

    if candidate_label in route_stops:
        raise ValueError("candidate_label cannot already be part of route_stops")

    base = tuple(route_stops)
    end = len(base) + 1 if allow_terminal_position else len(base)
    return tuple(
        (*base[:index], candidate_label, *base[index:])
        for index in range(1, end)
    )


def evaluate_candidate(
    graph: Graph,
    demand_state: DemandState,
    bus: Bus,
    route_stops: Sequence[str],
    candidate_label: str,
    time_limit_minutes: int,
    *,
    score_metric: str = DENSITY,
    alpha: float = 1.0,
    bus_index: int = 0,
    full_demand_state: DemandState | None = None,
    allow_terminal_position: bool = False,
) -> CandidateEvaluation:
    evaluations: list[CandidateEvaluation] = []

    for inserted_route in _insertion_routes(
        route_stops,
        candidate_label,
        allow_terminal_position=allow_terminal_position,
    ):
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
                prize=prize_for(simulation, score_metric, alpha),
                feasible=feasible,
                simulation=simulation,
            )
        )

    if not evaluations:
        raise ValueError("No insertion positions available for the candidate")

    return max(evaluations, key=evaluation_sort_key)


def rank_candidates(
    graph: Graph,
    demand_state: DemandState,
    bus: Bus,
    route_stops: Sequence[str],
    time_limit_minutes: int,
    *,
    candidate_labels: Sequence[str] | None = None,
    score_metric: str = DENSITY,
    alpha: float = 1.0,
    bus_index: int = 0,
    full_demand_state: DemandState | None = None,
    allow_terminal_position: bool = False,
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
            score_metric=score_metric,
            alpha=alpha,
            bus_index=bus_index,
            full_demand_state=full_demand_state,
            allow_terminal_position=allow_terminal_position,
        )
        for candidate_label in labels
    ]

    return sorted(ranked, key=evaluation_sort_key, reverse=True)


def calculate_candidate_prizes(
    graph: Graph,
    demand_state: DemandState,
    bus: Bus,
    route_stops: Sequence[str],
    time_limit_minutes: int,
    *,
    candidate_labels: Sequence[str] | None = None,
    score_metric: str = DENSITY,
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
        score_metric=score_metric,
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
