from __future__ import annotations

from collections.abc import Sequence

from application.orienteering.models import DemandState, RouteSimulation
from domain.entities.edge import Edge
from domain.entities.graph import Graph


def _edge_by_labels(
    graph: Graph,
    source_label: str,
    destination_label: str,
) -> Edge | None:
    return graph.edges_by_label.get((source_label, destination_label))


def _demand_by_origin(demand_state: DemandState) -> dict[str, dict[str, int]]:
    demand_by_origin: dict[str, dict[str, int]] = {}

    for (origin, destination), quantity in demand_state.edge_demand.items():
        if quantity <= 0:
            continue

        demand_by_origin.setdefault(origin, {})[destination] = quantity

    return demand_by_origin


def simulate_route(
    graph: Graph,
    demand_state: DemandState,
    route_stops: Sequence[str],
    *,
    full_demand_state: DemandState | None = None,
    diesel_price_per_liter: float = 0.0,
    driver_hourly_rate: float = 0.0,
    km_autonomy_per_liter: float = 1.0,
) -> RouteSimulation:
    stops = tuple(route_stops)
    if len(stops) < 2:
        raise ValueError("route_stops must contain at least an origin and a destination")

    if len(stops) == 2 and stops[0] == stops[1]:
        return RouteSimulation(
            stops=stops,
            edges=(),
            total_distance_km=0.0,
            travel_time_minutes=0,
            served_passengers=0,
            peak_load=0,
            route_valid=True,
            leftover_onboard_passengers=0,
            served_pairs=(),
            missing_edges=(),
        )

    edges: list[Edge] = []
    missing_edges: list[tuple[str, str]] = []

    for source_label, destination_label in zip(stops, stops[1:]):
        edge = _edge_by_labels(graph, source_label, destination_label)
        if edge is None:
            missing_edges.append((source_label, destination_label))
            continue

        edges.append(edge)

    position = {label: index for index, label in enumerate(stops)}
    peak_demand_state = full_demand_state if full_demand_state is not None else demand_state
    demand_by_origin = _demand_by_origin(peak_demand_state)

    served_pairs: list[tuple[str, str, int]] = []
    served_passengers = 0

    for (origin, destination), quantity in sorted(demand_state.edge_demand.items()):
        if quantity <= 0:
            continue

        if origin not in position or destination not in position:
            continue

        if origin != destination and position[origin] < position[destination]:
            served_pairs.append((origin, destination, quantity))
            served_passengers += quantity

    onboard: dict[str, int] = {}
    peak_load = 0

    for index, stop in enumerate(stops):
        onboard.pop(stop, None)

        for destination_label, quantity in sorted(demand_by_origin.get(stop, {}).items()):
            if quantity <= 0:
                continue

            if destination_label == stop:
                continue

            if position.get(destination_label, -1) > index:
                onboard[destination_label] = onboard.get(destination_label, 0) + quantity

        if index < len(stops) - 1:
            peak_load = max(peak_load, sum(onboard.values()))

    leftover_onboard_passengers = sum(onboard.values())

    total_distance_km = sum(edge.distance_km for edge in edges)
    travel_time_minutes = sum(edge.travel_time_minutes for edge in edges)
    rate_km = diesel_price_per_liter / km_autonomy_per_liter
    rate_minute = driver_hourly_rate / 60.0
    fuel_cost = total_distance_km * rate_km
    driver_cost = travel_time_minutes * rate_minute

    return RouteSimulation(
        stops=stops,
        edges=tuple(edges),
        total_distance_km=total_distance_km,
        travel_time_minutes=travel_time_minutes,
        served_passengers=served_passengers,
        peak_load=peak_load,
        route_valid=not missing_edges,
        leftover_onboard_passengers=leftover_onboard_passengers,
        fuel_cost=fuel_cost,
        driver_cost=driver_cost,
        total_cost=fuel_cost + driver_cost,
        served_pairs=tuple(served_pairs),
        missing_edges=tuple(missing_edges),
    )
