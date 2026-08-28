from __future__ import annotations

from application.orienteering.models import CandidateEvaluation, FleetMove


def _rank_fields(
    *,
    prize: float,
    served_passengers: int,
    travel_time_minutes: int,
    bus_index: int,
    label: str,
) -> tuple:
    return (prize, served_passengers, -travel_time_minutes, -bus_index, label)


def evaluation_sort_key(evaluation: CandidateEvaluation) -> tuple:
    return (
        int(evaluation.feasible),
        *_rank_fields(
            prize=evaluation.prize,
            served_passengers=evaluation.simulation.served_passengers,
            travel_time_minutes=evaluation.simulation.travel_time_minutes,
            bus_index=evaluation.bus_index,
            label=evaluation.candidate_label,
        ),
    )


def move_sort_key(move: FleetMove) -> tuple:
    return _rank_fields(
        prize=move.prize,
        served_passengers=move.simulation.served_passengers,
        travel_time_minutes=move.simulation.travel_time_minutes,
        bus_index=move.bus_index,
        label=move.destination_label or "",
    )