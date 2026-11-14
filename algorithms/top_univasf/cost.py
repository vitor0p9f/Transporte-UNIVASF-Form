"""Operating cost used to build each bus's intention.

TOP scores proposals by passengers per real (R$). A route's cost is the fuel
it burns (route distance divided by the bus's own km per liter, priced with the
scenario's diesel) plus the driver (route minutes priced with the scenario's
hourly rate). Every proposal is charged with the bus that would drive it, so a
thirsty vehicle has to earn the demand it takes.
"""

from dataclasses import dataclass

import numpy as np

from algorithms.top_univasf.model import StopSequence
from utils.paths import path_distance


@dataclass(frozen=True)
class RouteCost:
    """What one route costs, split into the parts that justify its price."""

    distance_km: float
    liters: float
    fuel: float
    driver: float

    @property
    def total(self) -> float:
        return self.fuel + self.driver


@dataclass(frozen=True)
class CostModel:
    """Scenario prices applied to every bus's own consumption."""

    diesel_price_per_liter: float
    driver_hourly_rate: float

    def route_cost(
        self, distance_km: float, minutes: float, km_per_liter: float
    ) -> float:
        """Fuel + driver cost of one route under this bus's consumption."""
        return self.route_breakdown(distance_km, minutes, km_per_liter).total

    def route_breakdown(
        self, distance_km: float, minutes: float, km_per_liter: float
    ) -> RouteCost:
        """Fuel burned and driver hours paid for one route, priced.

        This is the only place the formula lives: the scoring asks for the
        total, the reports ask for the parts.
        """
        if km_per_liter <= 0:
            raise ValueError(f"km_per_liter must be positive, got {km_per_liter}")
        if distance_km < 0 or minutes < 0:
            raise ValueError(
                "distance and minutes must be non-negative, got "
                f"{distance_km} and {minutes}"
            )
        liters = distance_km / km_per_liter
        return RouteCost(
            distance_km=distance_km,
            liters=liters,
            fuel=liters * self.diesel_price_per_liter,
            driver=minutes / 60.0 * self.driver_hourly_rate,
        )


def route_distance_km(distance: np.ndarray, stops: StopSequence) -> float:
    """Distance driven by a route, counting repeated nodes every time."""
    return path_distance(distance, stops)
