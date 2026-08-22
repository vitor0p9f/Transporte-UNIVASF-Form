# ADR 001: Directed Edges

## Status
Accepted

## Context
The transport network model uses edges to connect nodes (stops). Initially the edge directionality was ambiguous — whether the graph was undirected (symmetric distances) or directed (asymmetric).

## Decision
**Edges are DIRECTED**. Each Edge has a `source` Node and a `destination` Node. The edge is traversable only from `source` to `destination`. Reverse direction requires a separate Edge with potentially different `distance_km` and `travel_time_min` values.

## Alternatives Considered
- **Undirected edges**: Simpler model but loses directionality information — in real transport, distances/time often differ between origin→destination vs destination→origin.
- **Bidirectional flag**: Add `is_bidirectional: bool` to Edge, but this couples the model to a specific traversal pattern and doesn't scale to multi-segment routes.

## Consequences
- **Pros**: Accurate cost calculation per direction; supports asymmetric networks (one-way streets, different return routes); clearer domain model.
- **Cons**: More edges to model (each directional pair requires separate entries); graph traversal algorithms must respect edge direction.

## Related
- `CONTEXT.md` line 33: Directed edge semantics
- `CONTEXT.md` line 42: Directed edges design decision
- `Edge.py` `domain/entities/Edge.py`: source/destination fields
- `1.json`: All edges are directional by destination field

## References
- Domain glossary: `CONCEPT.md` — Edge section
- Edge dataclass: `domain/entities/Edge.py`