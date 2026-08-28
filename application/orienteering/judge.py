from __future__ import annotations

from collections.abc import Sequence

from application.orienteering.models import CandidateEvaluation, RouteSimulation
from application.orienteering.ranking import evaluation_sort_key
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

    return max(pool, key=evaluation_sort_key)
