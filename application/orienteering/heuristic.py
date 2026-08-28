from __future__ import annotations

from collections.abc import Sequence

from application.orienteering.commit import commit_served_demand
from application.orienteering.judge import judge_competing_candidates
from application.orienteering.models import CandidateEvaluation, DemandState, GreedyTopResult, GreedyTopStep
from application.orienteering.planner import rank_candidates
from application.orienteering.prize import DENSITY
from domain.entities.bus import Bus
from domain.entities.graph import Graph


def build_initial_route(
    origin_label: str,
    destination_label: str,
) -> tuple[str, ...]:
    if not origin_label or not destination_label:
        raise ValueError("origin_label and destination_label are required")

    return (origin_label, destination_label)


def _served_pairs_map(evaluation: CandidateEvaluation) -> dict[tuple[str, str], int]:
    return {
        (origin, destination): quantity
        for origin, destination, quantity in evaluation.simulation.served_pairs
    }


def run_greedy_top(
    graph: Graph,
    demand_state: DemandState,
    bus: Bus,
    origin_label: str,
    destination_label: str | None,
    time_limit_minutes: int,
    *,
    alpha: float = 1.0,
    score_metric: str = DENSITY,
    candidate_labels: Sequence[str] | None = None,
    bus_index: int = 0,
    max_iterations: int | None = None,
) -> GreedyTopResult:
    allow_terminal_position = destination_label is None
    if destination_label is None:
        route_stops = (origin_label,)
    else:
        route_stops = build_initial_route(origin_label, destination_label)
    current_state = demand_state
    steps: list[GreedyTopStep] = []
    last_simulation = None
    iteration = 0

    while True:
        if max_iterations is not None and iteration >= max_iterations:
            break

        ranking = tuple(
            rank_candidates(
                graph,
                current_state,
                bus,
                route_stops,
                time_limit_minutes,
                candidate_labels=candidate_labels,
                alpha=alpha,
                score_metric=score_metric,
                bus_index=bus_index,
                full_demand_state=demand_state,
                allow_terminal_position=allow_terminal_position,
            )
        )
        chosen = judge_competing_candidates(ranking, require_feasible=True)
        if chosen is None:
            break

        steps.append(
            GreedyTopStep(
                iteration=iteration + 1,
                route_stops_before=route_stops,
                route_stops_after=chosen.route_stops,
                ranking=ranking,
                chosen=chosen,
            )
        )

        last_simulation = chosen.simulation
        current_state = commit_served_demand(current_state, _served_pairs_map(chosen))
        route_stops = chosen.route_stops
        iteration += 1

        if not current_state.edge_demand:
            break

    return GreedyTopResult(
        route_stops=route_stops,
        demand_state=current_state,
        steps=tuple(steps),
        simulation=last_simulation,
    )
