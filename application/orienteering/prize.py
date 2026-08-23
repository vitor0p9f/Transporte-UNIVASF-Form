from __future__ import annotations

from application.orienteering.models import RouteSimulation


def calculate_node_prize(
    simulation: RouteSimulation,
    alpha: float = 1.0,
) -> float:
    return simulation.served_passengers - alpha * simulation.travel_time_minutes
