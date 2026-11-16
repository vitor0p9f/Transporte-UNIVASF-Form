from dataclasses import dataclass


@dataclass(frozen=True)
class Bus:
    """Immutable spec, one row of fleet.csv."""

    id: int
    passenger_capacity: int
    fuel_capacity: float
    km_autonomy_per_liter: float
