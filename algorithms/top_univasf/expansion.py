"""Stage 2: one demand-driven insertion for a bus with a locked OD pair."""

import numpy as np

from algorithms.top_univasf.model import (
    ExpansionProposal,
    WorkState,
)
from algorithms.top_univasf.scoring import marginal_passengers_per_minute
from algorithms.top_univasf.simulation import candidate_nodes, simulate_stops
from utils.instances import InstanceData


def best_demand_driven_insertion(
    data: InstanceData,
    state: WorkState,
    remaining: np.ndarray,
    time_limit_minutes: int,
) -> ExpansionProposal | None:
    """Demand-driven step: the new point's position comes from the pair.

    For every point off the route: if demand `A->B` arrives with `A` on the
    route, it tries `B` right after `A` (if `A` is the final destination it
    makes the crossing [..., d, B, d]); if demand `B->Y` leaves with `Y` on the
    route, it tries `B` right before `Y` -- and, when `Y` is the start `o` (a
    fixed position), it tries the dobradinha `[o, B, o, ...]`, unless `o == d`
    (then the route already ends at `o`, and the final-destination case covers
    it). Every trial is simulated in full (capacity per leg, whoever alights
    frees a seat) and the marginal score (passengers gained / extra minutes)
    decides. Returns the best expansion proposal, or None.
    """
    capacity = state.bus.passenger_capacity
    stops = state.stops
    last = len(stops) - 1
    current = simulate_stops(data, stops, capacity, remaining, state.claimed)
    current_qty = {
        (origin, destination): qty for origin, destination, qty in current.pairs
    }
    best: ExpansionProposal | None = None
    best_key: tuple | None = None

    def consider(candidate: int, trial: list[int]) -> None:
        nonlocal best, best_key
        outcome = simulate_stops(data, trial, capacity, remaining, state.claimed)
        if outcome.travel_minutes > time_limit_minutes or outcome.peak_load > capacity:
            return
        score = marginal_passengers_per_minute(
            outcome.passengers - current.passengers,
            outcome.travel_minutes - current.travel_minutes,
        )
        if score <= 0:
            return
        claim = tuple(
            sorted(
                (origin, destination, qty - current_qty.get((origin, destination), 0))
                for origin, destination, qty in outcome.pairs
                if qty > current_qty.get((origin, destination), 0)
            )
        )
        if not claim:
            return
        key = (
            score,
            outcome.passengers,
            -outcome.travel_minutes,
            -candidate,
            tuple(trial),
        )
        if best_key is None or key > best_key:
            known = set(stops)
            best_key = key
            best = ExpansionProposal(
                state=state,
                stops=tuple(trial),
                claim=claim,
                new_points=tuple(dict.fromkeys(n for n in trial if n not in known)),
                travel_time_minutes=outcome.travel_minutes,
                peak_load=outcome.peak_load,
                score=score,
            )

    for candidate in candidate_nodes(remaining, stops):
        # A->candidate arrives: place candidate right after A.
        for index, stop in enumerate(stops):
            if int(remaining[stop, candidate]) <= 0:
                continue
            if index == last:  # A is the final destination: [..., d, B, d]
                consider(candidate, stops + [candidate, stops[-1]])
            else:
                consider(candidate, stops[:index + 1] + [candidate] + stops[index + 1:])
        # candidate->Y leaves: place candidate right before Y.
        for index, stop in enumerate(stops):
            if int(remaining[candidate, stop]) <= 0:
                continue
            if index == 0:  # Y is the start: dobradinha [o, B, o, ...]
                if stops[0] == stops[-1]:  # o == d: the route already ends at o
                    continue
                consider(candidate, stops[:1] + [candidate] + stops[:1] + stops[1:])
            else:
                consider(candidate, stops[:index] + [candidate] + stops[index:])
    return best
