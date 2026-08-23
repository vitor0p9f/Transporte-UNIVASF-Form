# ADR 005: Greedy TOP Prize Calculation

## Status
Accepted

## Context
The project will implement a greedy Team Orienteering Problem (TOP) heuristic where each bus evaluates candidate nodes by simulating the effect of visiting that node before the final destination. The open questions were how to define `prize`, how to account for time, and how to mutate the working graph between iterations.

## Decision
The heuristic computes a **composite prize** for each candidate node using a **retroactive simulation** of the entire route segment that would result from inserting that node.

The score is:

```text
prize = gain_passengers - time_cost
```

with `alpha = 1`.

### Gain term
- Positive contribution comes from passengers that can be served by the simulated route.
- This includes passengers who board and alight on the same bus route, and passengers whose service is completed via transfer when the simulation allows that flow.

### Time term
- Negative contribution is the extra travel time caused by the simulated insertion.
- The simulation must consider the path from the current position through the candidate node and up to the final destination.

### Feasibility and removal
- Feasibility is validated inside the route simulation.
- A node may be removed from the working graph copy only when **all demand for that node has been fully satisfied** for the evaluated turn.
- For this project, “demand satisfied” means passenger boarding and alighting have both been accepted, whether within the same route or through transfer.

### Function shape
- The prize function must be pure.
- It must return a copy of the graph, the ranking of candidate nodes, and the chosen best candidate.
- Each iteration works on a copied graph so the next iteration sees the updated residual demand.

## Alternatives Considered
- **Static prize per node**: Simpler, but ignores route context and time constraints.
- **Distance-only score**: Easier to compute, but does not capture passenger benefit.
- **Incremental-only score**: Faster, but fails to account for the full simulated route impact.

## Consequences
- **Pros**: The heuristic is route-aware, auditable, and compatible with the existing demand/route simulation model.
- **Cons**: The score is more expensive to compute because it requires full simulation per candidate.

## Related
- `CONTEXT.md` line 23: unified cost model
- `CONTEXT.md` line 32: edge properties include demand
- `CONTEXT.md` line 37: nodes are transport stops
- `application/graph/calculate_node_prize.py`: target implementation
- `algorithms/constraints/capacity_evaluation.py`: route feasibility by simulation
- `algorithms/constraints/service_audit.py`: residual demand accounting

## References
- Team Orienteering Problem heuristic design discussed in the current session
- Existing transport demand and route simulation code in `domain/entities/` and `algorithms/constraints/`
