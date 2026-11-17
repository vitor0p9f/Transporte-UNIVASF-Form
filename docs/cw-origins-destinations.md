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
list with a single origin. It does not disable the destination filter. Neither
report runner supplies it: the controlled comparison and the standard report
(`main.py`, TOP only) both let any permitted origin start a route, while
`destination_labels` still constrains the terminal node. The API keeps that
multi-origin behaviour when no `depot` is given. With no destination filter,
the route may still end at its last customer.

Capacity is a single reference value for the whole run: 24 seats in the
controlled comparison (the smallest bus of `fleet.csv`) and, in general, the
smallest bus of the scenario fleet. It is checked both in construction and in
the boarding simulation. This does not implement a heterogeneous CW: the
individual bus capacities are not explored, and the projection is still the
static demand-per-stop rule described below.

## Attendance-first selection

The report compares both heuristics by the passengers they carry, so the CW
selection steps rank a solution by attendance: more passengers served first,
then less fuel cost (`objective.solution_key`, the same criterion everywhere).
It applies to the lambda sweep, to the two-phase selection and to the
post-improvement keep-best. The two-phase search and the post-improvement also
reject a move that would carry fewer passengers, so the criterion is never
traded for distance.

The selection ranks candidates with a cheap estimate (the demand each route
holds, capped by the bus capacity). The exact figure always comes from the same
TOP UNIVASF boarding simulation the report uses.

## Anchoring the allowed endpoints

The construction merges stops around the reference depot; it does not know
which endpoint pair carries more passengers. `anchoring` closes that gap without
touching the stops or their order: it tries every allowed
`(origin, destination)` pair for each route against the demand that is still
free, keeps the pair that carries the most, charges that demand, and moves on to
the next route. The fuel cost, the distance and the node labels are the
tie-breaks, so the choice is deterministic. The route then keeps that pair
through the local search (the cost update preserves endpoints already set).

This is an adaptation to the pickup-and-delivery demand, not a change to the
savings formula or to the merging procedure: the savings remain the complete
singleton and merged route costs with the lambda adjustment on the joining arc.

## Stop set and capacity projection

A node is a stop when someone boards there OR gets off there. The load of a stop
is the side that boards the bus (boardings outbound, alightings inbound), capped
by the bus capacity, so a pair is never counted twice (origin and destination).
The destination releases the seat; it does not occupy another one. The depot is
not a stop, except when multiple origins make it a customer node.

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
