from __future__ import annotations

from domain.entities.bus import Bus
from domain.entities.edge import Edge
from Environment import Environment


def calculate_edge_cost(edge: Edge, environment: Environment, bus: Bus) -> float:
    """cost = distance_km × rate_km + travel_time_min × rate_minute"""
    rate_km = environment.diesel_price_per_liter / bus.km_autonomy_per_liter
    rate_minute = environment.driver_hourly_rate / 60

    return round(
        edge.distance_km * rate_km + edge.travel_time_minutes * rate_minute,
        2,
    )
