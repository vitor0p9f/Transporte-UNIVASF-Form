"""Operating cost used to build each bus's intention.

The cost-aware TOP scores proposals by passengers per real (R$) instead of
passengers per minute. A route's cost is the fuel it burns (route distance
divided by the bus's own km per liter, priced with the scenario's diesel) plus
the driver (route minutes priced with the scenario's hourly rate). Every
proposal is charged with the bus that would drive it, so a thirsty vehicle has
to earn the demand it takes.
"""

from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from algorithms.top_univasf.model import StopSequence


@dataclass(frozen=True)
class CostModel:
    """Scenario prices applied to every bus's own consumption."""

    diesel_price_per_liter: float
    driver_hourly_rate: float

    def route_cost(
        self, distance_km: float, minutes: float, km_per_liter: float
    ) -> float:
        """Fuel + driver cost of one route under this bus's consumption."""
        if km_per_liter <= 0:
            raise ValueError(f"km_per_liter must be positive, got {km_per_liter}")
        if distance_km < 0 or minutes < 0:
            raise ValueError(
                "distance and minutes must be non-negative, got "
                f"{distance_km} and {minutes}"
            )
        fuel = distance_km / km_per_liter * self.diesel_price_per_liter
        driver = minutes / 60.0 * self.driver_hourly_rate
        return fuel + driver


def route_distance_km(distance: np.ndarray, stops: StopSequence) -> float:
    """Distance driven by a route, counting repeated nodes every time."""
    if len(stops) < 2:
        return 0.0
    return float(sum(float(distance[a, b]) for a, b in pairwise(stops)))
