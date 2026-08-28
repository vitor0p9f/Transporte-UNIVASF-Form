from __future__ import annotations

from application.orienteering.models import RouteSimulation

DENSITY = "density"
PAX_MINUS_TIME = "pax_minus_time"
SCORE_METRICS = (DENSITY, PAX_MINUS_TIME)


def calculate_node_prize(
    simulation: RouteSimulation,
    alpha: float = 1.0,
) -> float:
    return simulation.served_passengers - alpha * simulation.travel_time_minutes


def calculate_density_prize(
    simulation: RouteSimulation,
) -> float:
    if simulation.served_passengers <= 0 or simulation.travel_time_minutes <= 0:
        return 0.0
    return simulation.served_passengers / simulation.travel_time_minutes


def prize_for(
    simulation: RouteSimulation,
    score_metric: str = DENSITY,
    alpha: float = 1.0,
) -> float:
    if score_metric == DENSITY:
        return calculate_density_prize(simulation)
    if score_metric == PAX_MINUS_TIME:
        return calculate_node_prize(simulation, alpha)
    raise ValueError(f"Unknown score_metric: {score_metric!r}")