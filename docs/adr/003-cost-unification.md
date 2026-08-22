# ADR 003: Cost Metric Unification

## Status
Accepted

## Context
The project maintains separate metrics for distance (km) and travel time (minutes), but routing optimization and economic analysis require a single unified metric. The question is whether to use distance/time separately throughout the codebase or unify them into a single `cost` metric in Reais (R$).

## Decision
**Unified cost metric** in Brazilian Reais (R$), calculated as:
```
cost = distance_km × rate_km + travel_time_min × rate_minute
```

Both distance and travel time contribute to the unified cost, but routing optimization, path selection, and economic analysis all use the `cost` metric as the single source of truth.

## Alternatives Considered
- **Separate metrics throughout**: Use distance for km-based costs, time for time-based costs, never combine. Cons: Context switching confusion; duplicated logic for cost aggregation; harder to compare routes across different cost structures.
- **Distance-only metric**: Optimize routes by shortest km only. Cons: Ignores driver time cost; economically suboptimal; doesn't reflect real transport operating costs.
- **Time-only metric**: Optimize by shortest time only. Cons: Ignores distance-based costs (fuel, wear); economically suboptimal.

## Consequences
- **Pros**: Single metric simplifies routing algorithms; enables straightforward comparison across different routes; aligns with business objective (economic efficiency); `Environment.py` centralizes rate configuration.
- **Cons**: Masks separate analysis of distance vs time trade-offs; requires rate configuration (`rate_km`, `rate_minute`); if rates change frequently, recalculation affects all routes.

## Related
- `CONTEXT.md` lines 20-24: Cost formula
- `CONTEXT.md` lines 26-28: Rate configuration
- `Environment.py`: Computes `rate_km` and `rate_minute` from diesel price, autonomy, hourly rate
- `Edge.py`: Cost computed via `environment.rate_km * distance_km + environment.rate_minute * travel_time_minutes`

## References
- Domain glossary: `CONTEXT.md` — Cost section
- Environment dataclass: `Environment.py`
- Edge dataclass: `domain/entities/Edge.py`
- Application layer: `application/routing/route_planner.py` (to be created)