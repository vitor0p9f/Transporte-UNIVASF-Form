from dataclasses import dataclass, field

from domain.entities.edge import Edge
from domain.entities.node import Node


@dataclass(frozen=True)
class Graph:
    nodes: frozenset[Node] = field(default_factory=frozenset)
    edges: frozenset[Edge] = field(default_factory=frozenset)
