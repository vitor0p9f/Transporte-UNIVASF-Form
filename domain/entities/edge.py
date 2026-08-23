from __future__ import annotations

from dataclasses import dataclass

from domain.entities.node import Node


@dataclass(frozen=True)
class Edge:
    source: Node
    destination: Node
    distance_km: float
    travel_time_minutes: int
