import json
from pathlib import Path

from domain.entities.edge import Edge
from domain.entities.node import Node
from Environment import Environment
from Graph import Graph


def load_graph_from_file(file_path: Path, environment: Environment) -> Graph:
    with file_path.open(encoding="utf-8") as file:
        data = json.load(file)

    graph = Graph(environment=environment)

    for node_data in data["nodes"]:
        node = Node(
            label=node_data["label"],
        )

        graph.nodes[node.label] = node

    for node_data in data["nodes"]:
        source = graph.nodes[node_data["label"]]

        for edge_data in node_data.get("edges", []):
            destination = graph.nodes[edge_data["destination"]]

            edge = Edge(
                source=source,
                destination=destination,
                distance_km=edge_data.get("distance", 0.0),
                travel_time_minutes=edge_data.get("estimated_travel_time", 0),
            )

            graph.edges[f"{source.label}→{destination.label}"] = edge

    return graph
