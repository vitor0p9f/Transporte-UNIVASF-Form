# Domain Glossary

## Concepts

### Distance (`distance`)
- **Unit**: kilometers (km)
- **Description**: Spatial metric representing the physical distance between two nodes/stops.
- **Cost relation**: Each kilometer traversed generates a monetary cost (rate per km).

### Travel Time (`travel_time`)
- **Unit**: minutes (min)
- **Description**: Temporal metric representing the estimated time required to traverse an edge.
- **Cost relation**: Each minute of travel/driver time generates a monetary cost (rate per minute).

### Demand (`demand`)
- **Unit**: passenger count array (6 time periods)
- **Description**: Passenger flow demand for each of 6 shift periods (morning 1/2, noon 1/2, night 1/2).
- **Indexing**: `[manha_1, manha_2, tarde_1, tarde_2, noite_1, noite_2]`

### Cost (`cost`)
- **Unit**: Brazilian Reais (R$)
- **Description**: Unified metric combining distance and travel time costs.
- **Formula**: `cost = distance_km × rate_km + travel_time_min × rate_minute`
- **Purpose**: Single metric for routing optimization and economic analysis.

### Prize (`prize`)
- **Unit**: passengers per minute (pax/min)
- **Description**: Route-contextual score used to rank candidate nodes in the greedy TOP heuristic; a single rate with no scale knob.
- **Formula**: `prize = passengers_served / travel_time_minutes` (metric `density`, the default); alternative `pax_minus_time`: `prize = passengers_served - alpha * travel_time_minutes`.
- **Guards**: `density` returns `0.0` when no passengers are served or travel time is `<= 0`.
- **Purpose**: Compare candidate insertions (and destination/terminal routes) before committing demand to the working graph copy.

### Rate Configuration
- `rate_km`: Cost per kilometer (R$/km)
- `rate_minute`: Cost per minute of travel (R$/min)

### Edge (`edge`)
- **Description**: Directed connection between two Node entities.
- **Properties**: `source`, `destination`, `distance_km`, `travel_time_min`, `cost_r$` (computed)
- **Direction**: Directed — traversable only from `source` to `destination`. Reverse direction requires separate Edge with potentially different distance/time values.

### Node (`node`)
- **Description**: Geographic stop/location in the transport network.
- **Properties**: `label`

### Demand State (`demand_state`)
- **Description**: Residual passenger demand for one shift.
- **Properties**: `boardings_by_label`, `alightings_by_label`, `edge_demand`
- **Purpose**: Tracks what is still pending independently from the physical graph.

### Fleet Coordination (`fleet_coordination`)
- **Description**: Round-based assignment layer where all buses compete for the same residual demand; the highest-prize bus executes exactly one move (destination lock or single-stop insertion) per round.
- **Properties**: `run_parallel_fleet_top` (used by CLI); legacy `run_balanced_fleet_top` moved to `fleet_legacy.py`, deprecated
- **Round mechanics**: every bus scores against identical `DemandState`; winner = `max(move_sort_key)` → `(prize, served_passengers, -travel_time_minutes, -bus_index, destination_label)`.
- **Destination lock**: a destination-less bus is scored by a full greedy route per allowed destination; on winning it locks destination and commits the full greedy route it scored, so the residual demand drops accordingly and later destinations re-score on the true remaining pool. **Free mode** (no `destination_labels`): the bus scores a single full greedy route from the origin and the heuristic's last stop becomes the terminal.
- **2-opt at commit**: the winning lock route is reordered (`improve_route_with_two_opt`) before commit — 2-opt segment swaps with endpoints fixed, accepted when `(served_passengers, -travel_time_minutes)` improves lexicographically (time may grow to serve more); the demand deducted is re-simulated from the optimized route.
- **Locked phase**: a bus with a locked destination proposes its best single insertion via `rank_candidates` (residual demand for served passengers, full demand for peak).
- **Honest accounting**: the final report re-simulates each bus only over the demand it actually committed (`served_per_bus`), so totals never double-count passengers across buses.
- **Termination**: stops when residual `edge_demand` empties; buses that never lock a destination, or whose locked route serves zero passengers, are excluded from the result.
- **Legacy (balanced)**: `run_balanced_fleet_top` (em `fleet_legacy.py`, deprecado) seleciona por destino menos usado com RNG-seeded tie-breaking; também omite do resultado ônibus cujo plano não atende nenhum passageiro.
- **Origin as destination**: The origin label may also be included in the allowed destination set.

### Graph (`graph`)
- **Description**: Immutable physical transport network.
- **Properties**: `nodes: frozenset[Node]`, `edges: frozenset[Edge]`
- **Purpose**: Stores connectivity and geometry only; all mutable service demand lives in `DemandState`.

### Demand State (`demand_state`)
- **Description**: Residual passenger demand for one shift.
- **Properties**: `boardings_by_label`, `alightings_by_label`, `edge_demand`
- **Purpose**: Tracks what is still pending independently from the physical graph.

## Design Decisions

- **Separate but unified**: Distance and travel time are conceptually distinct metrics, but both contribute to the unified `cost` metric for economic decisions.
- **Directed edges**: Network edges can be traversed from `source` to `destination`. Reverse direction requires separate Edge with potentially different distance/time values.
- **6-period demand**: Passenger demand modeled across 6 shift periods for revenue/forecasting purposes.
- **Cost-driven routing**: Path selection and optimization use the `cost` metric rather than distance or time alone.
- **Immutable network, mutable demand**: The physical graph is read-only during heuristics; residual service demand is carried in `DemandState` and updated independently.
