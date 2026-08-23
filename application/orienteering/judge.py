from __future__ import annotations

from collections.abc import Sequence

from application.orienteering.models import CandidateEvaluation, RouteSimulation
from domain.entities.bus import Bus


def judge_route(
    simulation: RouteSimulation,
    bus: Bus,
    time_limit_minutes: int,
) -> bool:
    return (
        simulation.route_valid
        and simulation.travel_time_minutes <= time_limit_minutes
        and simulation.peak_load <= bus.passenger_capacity
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


def judge_competing_candidates(
    evaluations: Sequence[CandidateEvaluation],
    *,
    require_feasible: bool = True,
) -> CandidateEvaluation | None:
    if not evaluations:
        return None

    pool = [evaluation for evaluation in evaluations if evaluation.feasible] if require_feasible else list(evaluations)
    if not pool:
        return None

    return max(pool, key=_evaluation_key)
