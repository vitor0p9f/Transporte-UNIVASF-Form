from __future__ import annotations

from typing import Any

from application.orienteering.models import DemandState
from domain.entities.edge import Edge
from domain.entities.graph import Graph
from domain.entities.node import Node
from domain.entities.shift import Shift
from infraestructure.graph.graph_loader import GraphData


def graph_factory(
    graph_data: GraphData,
) -> Graph:
    nodes = _build_nodes(graph_data)
    edges = _build_edges(graph_data, nodes)

    return Graph(
        nodes=frozenset(nodes.values()),
        edges=frozenset(edges),
    )


def demand_state_factory(
    graph_data: GraphData,
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


def _build_nodes(
    graph_data: GraphData,
) -> dict[str, Node]:
    return {
        node_data["label"]: Node(
            label=node_data["label"],
        )
        for node_data in graph_data["nodes"]
    }


def _build_edges(
    graph_data: GraphData,
    nodes: dict[str, Node],
) -> frozenset[Edge]:
    edges = (
        _build_node_edges(node_data, nodes)
        for node_data in graph_data["nodes"]
    )

    return frozenset(
        edge
        for node_edges in edges
        for edge in node_edges
    )


def _build_node_edges(
    node_data: dict[str, Any],
    nodes: dict[str, Node],
) -> frozenset[Edge]:
    source = nodes[node_data["label"]]

    return frozenset(
        _build_edge(
            source=source,
            edge_data=edge_data,
            nodes=nodes,
        )
        for edge_data in node_data["edges"]
    )


def _build_edge(
    source: Node,
    edge_data: dict[str, Any],
    nodes: dict[str, Node],
) -> Edge:
    destination = nodes[edge_data["destination"]]

    return Edge(
        source=source,
        destination=destination,
        distance_km=edge_data["distance"],
        travel_time_minutes=edge_data["estimated_travel_time"],
    )
