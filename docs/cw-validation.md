# CW service-first baseline validation

This update is confined to `fix/cw-origens-destinos`, based on its endpoint fix
`1804a5b`. The main branch remained at `f8cf6c1`; its solver and results file hashes
were checked before and after the work and remained unchanged.

## Automated checks

The complete suite passes: **296 tests**. Intentional CW expectation changes are
the pickup-plus-drop-off active set/static load and the inclusion of pure drop-off
nodes even without a terminal filter. TOP's golden regressions remain unchanged.
New coverage includes service/cost ranking, OD-order upper bounds, incident-load
deduplication, capacity rejection/acceptance, exact anchoring, lambda selection,
the complete pipeline order, exact finalist fallback, service-first CW-3,
incumbent isolation and deterministic report rendering.

The full acceptance script ran the five standard scenarios twice with seed 42,
the complete 0.1–2.0 lambda sweep, 5,000 two-phase iterations per lambda and the
500-iteration CW-3 cap. It also regenerated both controlled regimes twice. All
four Markdown reports were byte-identical between repetitions. Their SHA-256
hashes and the measured standard-run times are in [cw-validation.json](cw-validation.json).

## Standard comparison results

| Scenario | TOP served | CW served | CW time run 1 (s) | CW time run 2 (s) |
|---|---|---|---|---|
| 16 | 37/59 | 31/59 | 13.782 | 14.250 |
| 19 | 59/66 | 30/66 | 13.875 | 14.188 |
| 32 | 45/54 | 32/54 | 13.079 | 13.391 |
| 65 | 196/198 | 56/198 | 11.375 | 11.828 |
| 69 | 158/158 | 72/158 | 11.828 | 12.094 |

The standard-run service targets for scenarios 65 and 69 are met. All ten CW
measurements are below 15 seconds; this is an observation on this environment,
not a guarantee for every machine. Endpoints, actual path durations, peak
occupancies, available fleet size and served-plus-unserved accounting also passed.

## Interpretation and controlled regimes

The measured CW counts differ from the estimates in the implementation plan;
no expected result was hard-coded. CW remains below TOP in every standard case.
Distance savings do not model OD direction during construction, and static
touch-load capacity is conservative relative to reuse of seats after drop-offs.
Service-first final selection cannot turn that construction into an OD optimizer.

In the homogeneous controlled comparison, scenario 19 serves 38/66 with capacity
relaxed and 30/66 with capacity active. The regime changes the allowed merges and
search trajectory; both still rank exact service before cost. This difference is
not a regression caused by selecting the cheapest lambda. Heuristic outcomes need
not be monotone when the feasible merge set changes.

The fixed-origin controlled scenario 69 serves 30/158 with capacity active,
whereas the standard multi-origin scenario serves 72/158. The >=50 acceptance
targets above refer to the standard five-scenario run. These are distinct
experiments and must not be merged into a single outcome table without labels.

The controlled experiment shares its homogeneous fleet, fixed origin, boarding
simulation, time limits and fuel-plus-driver cost formula between methods. The
standard experiment has the same input fleet IDs but still uses a minimum-capacity
reference construction model for CW and individual vehicle characteristics for
TOP. Its interpretation explicitly retains that limitation.
