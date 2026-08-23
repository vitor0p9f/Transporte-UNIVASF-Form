from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from application.orienteering.models import DemandState
from domain.entities.shift import Shift


def build_demand_state(
    graph_data: dict[str, Any],
    shift: Shift,
) -> DemandState:
    period = shift.value

    boardings_by_label: dict[str, int] = {}
    alightings_by_label: dict[str, int] = {}
    edge_demand: dict[tuple[str, str], int] = {}

    for node_data in graph_data["nodes"]:
        label = node_data["label"]
        boardings = node_data.get("boardings", [0] * 6)[period]
        alightings = node_data.get("alightings", [0] * 6)[period]

        if boardings > 0:
            boardings_by_label[label] = boardings
        if alightings > 0:
            alightings_by_label[label] = alightings

        for edge_data in node_data.get("edges", []):
            quantity = edge_data.get("demand", [0] * 6)[period]
            if quantity > 0:
                edge_demand[(label, edge_data["destination"])] = quantity

    return DemandState(
        boardings_by_label=boardings_by_label,
        alightings_by_label=alightings_by_label,
        edge_demand=edge_demand,
    )


def candidate_labels_for_demand(
    demand_state: DemandState,
    route_stops: tuple[str, ...] | list[str],
) -> tuple[str, ...]:
    blocked = set(route_stops)
    labels = set(demand_state.boardings_by_label) | set(demand_state.alightings_by_label)
    return tuple(sorted(label for label in labels if label not in blocked))


def prune_empty_demand(demand_state: DemandState) -> DemandState:
    return DemandState(
        boardings_by_label={label: qty for label, qty in demand_state.boardings_by_label.items() if qty > 0},
        alightings_by_label={label: qty for label, qty in demand_state.alightings_by_label.items() if qty > 0},
        edge_demand={key: qty for key, qty in demand_state.edge_demand.items() if qty > 0},
    )


def apply_demand_commit(
    demand_state: DemandState,
    served_pairs: Mapping[tuple[str, str], int],
) -> DemandState:
    boardings = dict(demand_state.boardings_by_label)
    alightings = dict(demand_state.alightings_by_label)
    edges = dict(demand_state.edge_demand)

    for (origin, destination), quantity in served_pairs.items():
        if quantity <= 0:
            continue

        boardings[origin] = max(0, boardings.get(origin, 0) - quantity)
        alightings[destination] = max(0, alightings.get(destination, 0) - quantity)
        edges[(origin, destination)] = max(0, edges.get((origin, destination), 0) - quantity)

    return prune_empty_demand(
        DemandState(
            boardings_by_label=boardings,
            alightings_by_label=alightings,
            edge_demand=edges,
        )
    )
