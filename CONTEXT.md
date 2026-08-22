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

### Rate Configuration
- `rate_km`: Cost per kilometer (R$/km)
- `rate_minute`: Cost per minute of travel (R$/min)

### Edge (`edge`)
- **Description**: Directed connection between two Node entities.
- **Properties**: `source`, `destination`, `distance_km`, `travel_time_min`, `demand`, `cost_r$` (computed)
- **Direction**: Directed — traversable only from `source` to `destination`. Reverse direction requires separate Edge with potentially different distance/time values.

### Node (`node`)
- **Description**: Geographic stop/location in the transport network.
- **Properties**: `label`, `connections: list[Edge]`

## Design Decisions

- **Separate but unified**: Distance and travel time are conceptually distinct metrics, but both contribute to the unified `cost` metric for economic decisions.
- **Directed edges**: Network edges can be traversed from `source` to `destination`. Reverse direction requires separate Edge with potentially different distance/time values.
- **6-period demand**: Passenger demand modeled across 6 shift periods for revenue/forecasting purposes.
- **Cost-driven routing**: Path selection and optimization use the `cost` metric rather than distance or time alone.