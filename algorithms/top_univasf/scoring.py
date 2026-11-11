"""The scores the heuristic orders its decisions by.

The TOP has two objectives:

* ``time`` -- passengers per minute (the original heuristic);
* ``cost`` -- passengers per real (R$). Each bus pays fuel with its own km per
  liter plus the driver, priced by the scenario. Maximising passengers per real
  is equivalent to minimising real per passenger; in the insertion stage the
  marginal score minimises real per extra passenger.
"""


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


def passengers_per_real(served_passengers: int, cost: float) -> float:
    """Passengers per real. No passengers or no cost -> 0.0."""
    if served_passengers <= 0 or cost <= 0:
        return 0.0
    return served_passengers / cost


def od_pair_score_real(servable_passengers: int, pair_cost: float) -> float:
    """OD pair score: servable / route cost. No passengers or no cost -> 0.0.

    `pair_cost` is the fuel + driver cost of the route [o, P, d] under the
    bus's own consumption. Maximising this is the same as minimising the cost
    per passenger.
    """
    if servable_passengers <= 0 or pair_cost <= 0:
        return 0.0
    return servable_passengers / pair_cost


def marginal_passengers_per_real(
    delta_passengers: int, delta_cost: float
) -> float:
    """Passengers per real GAINED by inserting a stop (orders stage 2).

    This is the reciprocal of the marginal cost per extra passenger: higher is
    better, so the insertion always seeks the lowest cost per extra passenger.
    """
    if delta_passengers <= 0:
        return 0.0
    if delta_cost <= 0:
        return float("inf")
    return delta_passengers / delta_cost
