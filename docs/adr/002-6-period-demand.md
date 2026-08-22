# ADR 002: 6-Period Demand Indexing

## Status
Accepted

## Context
The demand model represents passenger flow across 6 shift periods. The indexing convention was ambiguous — whether it was 3 periods (morning/afternoon/night) or 6 periods with finer granularity.

## Decision
**6 distinct periods** with indexing `[manha_1, manha_2, tarde_1, tarde_2, noite_1, noite_2]`. Each period represents a 2-hour shift segment within the broader daypart (morning, afternoon, night). This granularity is necessary for:
- Revenue forecasting per shift segment
- Driver staffing optimization
- Demand-responsive scheduling

## Alternatives Considered
- **3 periods** (manha/tarde/noite): Simpler but loses intra-day variation — e.g., morning 1 (6-8am) vs morning 2 (8-10am) may have very different passenger patterns.
- **12+ periods**: Over-granular for the current use case; increases model complexity without proportional benefit; data availability becomes an issue.

## Consequences
- **Props**: Enables precise revenue forecasting; supports shift-based driver allocation; aligns with the `Shift` enum in `Client` (`MORNING_1`, `MORNING_2`, etc.).
- **Cons**: Demand data collection is more intensive; model parameters increase (6 coefficients vs 3); UI/UX must communicate 6 periods to domain experts.

## Related
- `CONTEXT.md` line 18: Demand indexing
- `1.json`: All edges have `demand: [0,0,0,0,0,0]`
- `Shift.py` `domain/entities/Shift.py`: 6-shift enum matching demand periods
- `Client.shift` field maps to demand period indexing

## References
- Domain glossary: `CONTEXT.md` — Demand section
- Shift enum: `domain/entities/Shift.py`
- Client dataclass: `domain/entities/Client.py`