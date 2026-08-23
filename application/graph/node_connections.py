from domain.entities.edge import Edge
from domain.entities.graph import Graph
from domain.entities.node import Node


def outbound_connections(
    graph: Graph,
    node: Node,
) -> frozenset[Edge]:
    return frozenset(
        edge
        for edge in graph.edges
        if edge.source == node
    )


def inbound_connections(
    graph: Graph,
    node: Node,
) -> frozenset[Edge]:
    return frozenset(
        edge
        for edge in graph.edges
        if edge.destination == node
    )
