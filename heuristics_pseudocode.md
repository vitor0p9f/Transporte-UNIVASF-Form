# UNIVASF TOP heuristic — pseudocode

Greedy OD with a locked pair. Mirrors `algorithms/top_univasf/` (the round is
`fleet.py: run_fleet`); the diagram overview is in `heuristics.md`.
Identifiers match the code, so a name here can be searched for directly.

```text
GREEDY OD HEURISTIC WITH LOCKED PAIR (TOP UNIVASF)
==================================================

OBJECTIVE
---------
Serve as many passengers as possible with the fleet, respecting the
capacity and the time limit per bus.

INPUTS
------
- Matrices: time[o,d], demand[o,d], nodes
  (distance.csv is loaded but not used by the heuristic)
- Fleet: list of buses (id, capacity)
- Time limit per bus
- Allowed destinations (None = free)
- Allowed origins for the draft (None = free)
- max_rounds (None = no cap)

SCORES
------
od_pair_score (draft) = boardings of the route / route time
  route = [o, d] (direct) or [o, P, d] (with one demand point P)
  boardings = capacity lock in route order
              (whoever alights at P frees a seat)
  if boardings <= 0 or route time <= 0: score = 0

marginal_passengers_per_minute (expansion) = passengers gained / extra time
  gain = passengers_after - passengers_before
  if gain <= 0: score = 0
  if extra time <= 0: score = infinity

final plan score = passengers_per_minute(total passengers, total time)

INITIALIZATION
--------------
remaining[o,d] = original demand
state_by_id[bus] = empty (bus still without a locked pair)
wins[bus] = 0

MAIN LOOP
---------
WHILE sum(remaining) > 0:
  proposals = []

  FOR each bus:
    IF the bus has no state yet:
      // 1) PROPOSE THE DRAFT OF THE OD PAIR
      best = none
      FOR each o in nodes (filtered by the allowed origins):
        out(o) = {p: remaining[o,p] > 0}
        FOR each d in nodes (filtered by the allowed destinations):
          in(d) = {p: remaining[p,d] > 0}
          skip if o == d and remaining[o,d] > 0  // a self-loop never boards
          skip if time[o,d] < 0
          P = (out(o) + in(d)) - {o, d}
          // note: with o == d and no direct demand, [o, P, o] still counts
          options = [(direct, [o, d], time[o,d])]
            + [(p, [o, p, d], time[o,p] + time[p,d]) for each p in P]
          FOR each (p, stops, route_time) in options:
            skip if route_time < 0 or route_time > time_limit
            served = segment_passengers(stops, capacity, remaining)
            skip if route_time == 0 and served > 0
            score = od_pair_score(served, route_time)
            skip if score < 0          // note: score 0 PASSES
            tie-break (keep the largest):
              (score, served, -route_time, -o, -d, -p)
              // direct enters as p = -1 (loses to any P)
      IF found:
        base = route of the best        // the route is BORN here
        keys = points of the base
             + every OD sub-pair of the base (i < j)
        proposals.append(DraftProposal)

    ELSE:
      // 2) PROPOSE THE DEMAND-DRIVEN EXPANSION
      skip if state.travel_time_minutes >= time_limit
      (cur_passengers, cur_time, _, cur_pairs) =
        simulate_stops(state.stops, capacity, remaining, state.claimed)
      best = none
      FOR each candidate cand with remaining demand off the route:
        RULE A (A->cand arrives, A on the route):
          IF A is the final destination: trial = stops + [cand, d]
          ELSE: trial = stops with cand right after A
        RULE B (cand->Y leaves, Y on the route):
          IF Y is the start (index 0):
            skip if stops[0] == stops[-1]  // o == d: the route already ends at o
            trial = [o, cand, o, ... rest of the route]   // DOBRADINHA
          ELSE: trial = stops with cand right before Y
        FOR each trial:
          (passengers, time, peak_load, pairs) =
            simulate_stops(trial, capacity, remaining, state.claimed)
          skip if time > time_limit or peak_load > capacity
          score = marginal(passengers - cur_passengers, time - cur_time)
          skip if score <= 0
          claim = pairs that gained passengers (new - before)
          skip if claim is empty
          tie-break (keep the largest):
            (score, passengers, -time, -cand, trial)
      IF found:
        keys = nodes the insertion REALLY ADDS
                 (in trial and off the current route; in the dobradinha
                  the repeated `o` does not count)
             + OD pairs of the claim
        proposals.append(ExpansionProposal)
      ELSE:
        the bus proposes nothing (zero gain)

  IF proposals is empty: STOP

  // 3) CONFLICT RESOLUTION
  conflict_groups: group proposals that share any key
  (union by transitivity):
    group of 1 = no conflict, commits alone
    group with > 1 = in conflict, only 1 commits
  winners = highest score of each group
    tie-break: largest (score,
                       passengers (DraftProposal: served; ExpansionProposal:
                                   sum of the claim),
                       -time (DraftProposal: route time; ExpansionProposal: total),
                       -bus.id)
    // holds with score 0 too (draft): 1 wins per group,
    // the others wait for the next round

  // 4) COMMIT (charge the global demand)
  FOR each winner (in index order):
    IF DraftProposal:
      re-simulate the base route over `remaining`  // hitchhikers count
      for each boarded pair (fo, fd, q):
        state.claimed += q;  remaining[fo, fd] -= q
      create state_by_id[bus] = (locked pair o,d; base route; claimed;
                                 route time; peak_load)
    IF ExpansionProposal:
      state.stops = trial; state.time = time; state.peak_load = peak_load
      for each (o, d, q) of the claim:
        state.claimed += q;  remaining[o, d] -= q
    rounds += 1;  wins[bus] += 1

  IF nobody committed: STOP

LOOP ENDS WHEN
--------------
- remaining reached zero, or
- max_rounds was exceeded, or
- no bus proposed anything, or
- nobody committed.

OUTPUT
------
- One plan per bus with sum(claimed) > 0:
  (bus, stops, passengers, time, peak_load, passengers/min, pairs, locked pair o/d)
- States with 0 passengers are dropped
  (a score-0 draft that never picked up a hitchhiker).
- Summary: rounds (= commits), wins per bus,
  pairs and passengers not served.

IMPORTANT NOTES
---------------
1. The draft accepts score 0; the expansion requires score > 0.
2. With score 0 for every viable pair, all buses propose the same
   nearest pair and only the lowest bus.id commits per round,
   charging no demand.
3. Draft and expansion compete in the same round under the same
   max-score rule inside the conflict group; the whole round plans
   over the SAME snapshot of `remaining`.
4. There is no deadhead: the route is born at the locked pair origin
   ([o, d] or [o, P, d]); the scenario origin only filters the
   origins the draft may use.
5. DOBRADINHA (new expansion position): demand cand->o is left over
   (leaving for the start) -> the candidate enters as [o, cand, o, ...]
   and the route revisits the start. It does not apply when o == d.
6. The conflict key of ExpansionProposal declares the node(s) really
   inserted + the pairs of the claim (it used to be the route's
   second-to-last node, which caused spurious conflicts).
```
