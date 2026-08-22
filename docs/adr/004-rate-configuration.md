# ADR 004: Rate Configuration Centralization

## Status
Accepted

## Context
Cost rates (`rate_km` and `rate_minute`) need to be configured somewhere accessible to the cost calculation logic. The question is where to store these rates and how to make them available across layers.

## Decision
**Centralized configuration** in `Environment` dataclass (`infraestructure/services/environment.py`). The `Environment` holds `rate_km` (R$/km) and `rate_minute` (R$/min) as computed properties derived from:
- `driver_hourly_rate` — driver labor cost
- `diesel_price_per_liter` — fuel cost
- `bus.km_autonomy_per_liter` — vehicle fuel efficiency

The `rate_km` property: `diesel_price_per_liter / bus.km_autonomy_per_liter` (R$ per km)
The `rate_minute` property: `driver_hourly_rate / 60` (R$ per minute)

## Alternatives Considered
- **Hardcoded constants**: `RATE_KM = 2.50` everywhere. Cons: Not configurable; violates DDD principle of isolating technical detail; changing rates requires code changes and redeployment.
- **Environment as domain entity**: Make `Environment` a Domain entity. Cons: Environment is technical infrastructure (rates, time limits), not business concept; mixing infrastructure into domain dilutes the bounded context.
- **Repository-injected rates**: Retrieve rates from database/config repository per operation. Cons: Over-engineering for current scale; adds latency; complex for simple transport model.

## Consequences
- **Pros**: Single source of truth for rates; easy to configure without code changes (via `Environment` constructor); testable (inject different `Environment` instances in tests); separates business logic from rate values.
- **Cons**: Requires `Environment` instantiation before route cost calculation; adds a dependency layer; if rates need to change per-route, pattern becomes more complex.

## Related
- `CONTEXT.md` lines 26-28: Rate configuration section
- `Environment.py`: Central rate computation
- `Edge.py`: Uses `environment.rate_km` and `environment.rate_minute` for cost
- `1.json`: Edge data has `distance_km` and `travel_time_min`; cost computed via Environment rates

## References
- Domain glossary: `CONTEXT.md` — Rate Configuration section
- Environment dataclass: `Environment.py`
- Edge cost computation: `domain/entities/Edge.py`
- Infrastructure layer: `infraestructure/services/` (to be organized)