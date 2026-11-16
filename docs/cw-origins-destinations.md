# Clarke-Wright scenario endpoints

The scenario columns `origin` and `destination_labels` contain **allowed** route
endpoints, separated by semicolons. A route selects one origin and one destination;
it does not have to visit every allowed endpoint. Different routes may choose
different pairs. Equal origin and destination labels permit a circuit.

Previously, CW took only the first origin and ignored the destination filter. It
could therefore end routes outside the scenario's permitted destinations. The
scenario loader now retains both complete lists, and route construction evaluates
all endpoint pairs for each candidate stop order. Feasible pairs take priority over
shorter pairs that exceed the time limit. Distance, fuel cost, duration, simulation,
local search and report conversion all use the same complete driven sequence.

The savings calculation includes the complete singleton and merged route costs,
including the selected access and terminal legs. It retains the lambda adjustment
on the joining arc. Without endpoint lists, the original single-depot/open-end
formula and API remain available.

An explicit `depot` argument (or CLI `--deposito`) deliberately overrides the origin
list with a single origin. It does not disable the destination filter. The
controlled-experiment runner still supplies this override to both heuristics by
design; the standard scenario runner uses every permitted origin. With no
destination filter, the route may still end at its last customer.

Capacity remains the existing static demand projection during construction and is
also checked by the boarding simulation. This change does not implement a fully
heterogeneous CW or replace that projection with TOP's decision rules.

## Tests

Run the full suite from this branch's checkout:

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

The endpoint regressions cover two origins and two destinations used by different
routes, mandatory terminal visits, the terminal leg exceeding the time limit,
circuits, endpoint ordering, explicit depot overrides, asymmetric travel times,
invalid labels, unrestricted ends, construction and local search on the five
report scenarios, and endpoint/time/capacity checks across every stored scenario.

The two-origin regression fails on the original `article` implementation because
only origin 1 is returned instead of the feasible origins 1 and 6. No document
artifacts or regenerated article reports are part of this fix.

## Verification on the fix branch

- Base: local `article`, commit `91dd6f3`.
- Full test suite: 277 passed, including 29 endpoint regressions.
- Fast construction checks: all 66 stored scenarios, with full-path endpoint,
  duration, occupancy and fleet-limit assertions on returned routes.
- Complete report pipeline: the five default scenarios with the default lambda
  sweep, 5,000 selection iterations and 500 post-improvement iterations. All
  endpoint, duration, occupancy and fleet-limit checks passed. Generated outputs
  were kept outside tracked article/report files.

The complete CW run returned:

| Scenario | Origins used | Destinations used | Requests served |
|---|---|---|---|
| 16 | 1 | 5, 7 | 12/59 |
| 19 | 5 | 3, 10, 24 | 15/66 |
| 32 | 18, 27 | 6, 31 | 9/54 |
| 65 | 44 | 43, 44, 45 | 8/198 |
| 69 | 43, 44, 45 | 44, 45 | 20/158 |

These figures describe corrected endpoint handling, not a claim that the heuristic
must improve coverage in every case. Every allowed pair is considered for a
candidate order; an allowed endpoint need not appear in the final selected routes.
