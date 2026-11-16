"""Reusable factories for the small model objects the unit tests need."""

from __future__ import annotations

import numpy as np

from algorithms.top_univasf import BusPlan, CostModel, FleetSummary, InstanceData
from entities.bus import Bus


def make_bus(
    bus_id: int = 1,
    capacity: int = 10,
    fuel_capacity: float = 100.0,
    km_per_liter: float = 4.0,
) -> Bus:
    """A bus with the usual test defaults; override only the relevant field."""
    return Bus(
        id=bus_id,
        passenger_capacity=capacity,
        fuel_capacity=fuel_capacity,
        km_autonomy_per_liter=km_per_liter,
    )


def make_data(
    demand: dict[tuple[int, int], int] | None = None,
    time: dict[tuple[int, int], int] | None = None,
    distance: dict[tuple[int, int], float] | None = None,
    size: int = 8,
) -> InstanceData:
    """Tiny instance indexed by node id, built from ``{(a, b): value}``."""
    demands = np.zeros((size + 1, size + 1), dtype=int)
    for (origin, destination), quantity in (demand or {}).items():
        demands[origin, destination] = quantity

    times = np.zeros((size + 1, size + 1), dtype=int)
    for (origin, destination), minutes in (time or {}).items():
        times[origin, destination] = minutes

    distances = np.zeros((size + 1, size + 1))
    for (origin, destination), km in (distance or {}).items():
        distances[origin, destination] = km

    return InstanceData(
        nodes=list(range(1, size + 1)),
        distance=distances,
        time=times,
        demand=demands,
    )


def make_plan(
    bus_id: int = 1,
    origin: int = 3,
    destination: int = 7,
    stops: tuple[int, ...] = (3, 5, 7),
    served_passengers: int = 4,
    travel_time_minutes: int = 20,
    peak_load: int = 2,
    score: float = 0.2,
    served_pairs: tuple[tuple[int, int, int], ...] = ((3, 7, 4),),
) -> BusPlan:
    """A plan with plausible defaults; override only what the test needs."""
    return BusPlan(
        bus_id=bus_id,
        origin=origin,
        destination=destination,
        stops=stops,
        served_passengers=served_passengers,
        travel_time_minutes=travel_time_minutes,
        peak_load=peak_load,
        score=score,
        served_pairs=served_pairs,
    )


def make_summary(
    unserved: int = 0,
    *,
    rounds: int = 3,
    wins_per_bus: tuple[tuple[int, int], ...] = ((1, 2),),
    unserved_pairs: tuple[tuple[int, int, int], ...] | None = None,
) -> FleetSummary:
    """A fleet summary whose unserved pair follows ``unserved`` by default."""
    if unserved_pairs is None:
        unserved_pairs = ((5, 6, unserved),) if unserved else ()
    return FleetSummary(
        rounds=rounds,
        wins_per_bus=wins_per_bus,
        unserved_passengers=unserved,
        unserved_pairs=unserved_pairs,
    )


def make_cost_model(
    diesel_price_per_liter: float = 10.0,
    driver_hourly_rate: float = 60.0,
) -> CostModel:
    """Diesel at R$ 10/L and driver at R$ 60/h: one minute costs R$ 1."""
    return CostModel(
        diesel_price_per_liter=diesel_price_per_liter,
        driver_hourly_rate=driver_hourly_rate,
    )
