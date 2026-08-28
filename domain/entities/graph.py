from dataclasses import dataclass, field
from functools import cached_property

from domain.entities.edge import Edge
from domain.entities.node import Node


@dataclass(frozen=True)
class Graph:
    nodes: frozenset[Node] = field(default_factory=frozenset)
    edges: frozenset[Edge] = field(default_factory=frozenset)

    @cached_property
    def edges_by_label(self) -> dict[tuple[str, str], Edge]:
        return {
            (edge.source.label, edge.destination.label): edge
            for edge in self.edges
        }
