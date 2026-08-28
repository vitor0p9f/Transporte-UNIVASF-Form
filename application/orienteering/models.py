from __future__ import annotations

from dataclasses import dataclass, field

from domain.entities.bus import Bus
from domain.entities.edge import Edge
from domain.entities.graph import Graph


@dataclass(frozen=True)
class DemandState:
    boardings_by_label: dict[str, int]
    alightings_by_label: dict[str, int]
    edge_demand: dict[tuple[str, str], int]


@dataclass(frozen=True)
class OrienteeringProblem:
    graph: Graph
    demand_state: DemandState


@dataclass(frozen=True)
class RouteSimulation:
    stops: tuple[str, ...]
    edges: tuple[Edge, ...]
    total_distance_km: float
    travel_time_minutes: int
    served_passengers: int
    peak_load: int
    route_valid: bool
    leftover_onboard_passengers: int = 0
    fuel_cost: float = 0.0
    driver_cost: float = 0.0
    total_cost: float = 0.0
    served_pairs: tuple[tuple[str, str, int], ...] = field(default_factory=tuple)
    missing_edges: tuple[tuple[str, str], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class CandidateEvaluation:
    bus_index: int
    candidate_label: str
    route_stops: tuple[str, ...]
    prize: float
    feasible: bool
    simulation: RouteSimulation


@dataclass(frozen=True)
class BusPlan:
    bus_index: int
    bus: Bus
    destination_label: str | None
    route_stops: tuple[str, ...]
    prize: float
    simulation: RouteSimulation


@dataclass(frozen=True)
class GreedyTopStep:
    iteration: int
    route_stops_before: tuple[str, ...]
    route_stops_after: tuple[str, ...]
    ranking: tuple[CandidateEvaluation, ...]
    chosen: CandidateEvaluation


@dataclass(frozen=True)
class GreedyTopResult:
    route_stops: tuple[str, ...]
    demand_state: DemandState
    steps: tuple[GreedyTopStep, ...]
    simulation: RouteSimulation | None


@dataclass(frozen=True)
class FleetMove:
    bus_index: int
    destination_label: str | None
    route_stops: tuple[str, ...]
    prize: float
    simulation: RouteSimulation
    locks_destination: bool


@dataclass(frozen=True)
class FleetStep:
    iteration: int
    bus_index: int
    route_stops_before: tuple[str, ...]
    route_stops_after: tuple[str, ...]
    options: tuple[FleetMove, ...]
    chosen: FleetMove


@dataclass(frozen=True)
class FleetResult:
    plans: tuple[BusPlan, ...]
    demand_state: DemandState
    steps: tuple[FleetStep, ...]
    simulation: RouteSimulation | None
