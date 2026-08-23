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
- **Unit**: heuristic score
- **Description**: Route-contextual score used to rank candidate nodes in the greedy TOP heuristic.
- **Formula**: `prize = passengers_served - time_minutes` when `alpha = 1`
- **Purpose**: Compare candidate insertions before committing demand to the working graph copy.

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
- **Description**: Pure assignment layer that distributes buses across allowed destination labels.
- **Properties**: balanced selection by least-used destination, deterministic tie-breaking via RNG seed
- **Purpose**: Avoid concentrating the fleet on a single end point when multiple final destinations are valid.
- **Route lock**: Once a bus selects its final destination, subsequent greedy expansions stay within that destination only.
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
