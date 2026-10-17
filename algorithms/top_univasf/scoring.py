"""The three scores the heuristic orders its decisions by."""


def passengers_per_minute(served_passengers: int, travel_time_minutes: int) -> float:
    """Passengers per minute. No passengers or no time -> 0.0."""
    if served_passengers <= 0 or travel_time_minutes <= 0:
        return 0.0
    return served_passengers / travel_time_minutes


def od_pair_score(servable_passengers: int, pair_time_minutes: int) -> float:
    """OD pair score: servable / route time. No passengers or no time -> 0.0.

    `servable_passengers` is what the route [o, P, d] would board under the
    capacity lock; `pair_time_minutes` is time[o, P] + time[P, d] (or time[o, d]
    for the direct option).
    """
    if servable_passengers <= 0 or pair_time_minutes <= 0:
        return 0.0
    return servable_passengers / pair_time_minutes


def marginal_passengers_per_minute(
    delta_passengers: int, delta_time_minutes: int
) -> float:
    """Passengers per minute GAINED by inserting a stop (orders stage 2)."""
    if delta_passengers <= 0:
        return 0.0
    if delta_time_minutes <= 0:
        return float("inf")
    return delta_passengers / delta_time_minutes
