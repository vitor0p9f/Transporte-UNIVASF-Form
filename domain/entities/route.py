from dataclasses import dataclass

from domain.entities.edge import Edge
from domain.entities.node import Node


@dataclass
class Route:
    edges: set[Edge]
    total_cost: float
    travel_time_minutes: int
    fuel_cost: float
    driver_cost: float
    fuel_liters: float
    total_distance_km: float
    peak_ridership: int | None = None
    average_ridership: int | None = None
    source_campus: Node | None = None
    destination_campus: Node | None = None
    total_ridership: int | None = None
