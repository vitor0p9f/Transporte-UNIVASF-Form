"""Stage 2: one demand-driven insertion for a bus with a locked OD pair."""

import numpy as np

from algorithms.top_univasf.cost import CostModel, route_distance_km
from algorithms.top_univasf.model import (
    ExpansionProposal,
    ServedPair,
    WorkState,
    with_depot,
)
from algorithms.top_univasf.scoring import (
    marginal_passengers_per_minute,
    marginal_passengers_per_real,
)
from algorithms.top_univasf.simulation import candidate_nodes, simulate_stops
from utils.instances import InstanceData


def _claim_delta(
    current_qty: dict[tuple[int, int], int],
    trial_pairs: tuple[ServedPair, ...],
) -> tuple[ServedPair, ...]:
    """Pairs the trial boards beyond what the current route already boards."""
    claim: list[ServedPair] = []
    for origin, destination, quantity in trial_pairs:
        before = current_qty.get((origin, destination), 0)
        if quantity > before:
            claim.append((origin, destination, quantity - before))
    return tuple(sorted(claim))


def best_demand_driven_insertion(
    data: InstanceData,
    state: WorkState,
    remaining: np.ndarray,
    time_limit_minutes: int,
    *,
    cost_model: CostModel | None = None,
) -> ExpansionProposal | None:
    """Demand-driven step: the new point's position comes from the pair.

    For every point off the route: if demand `A->B` arrives with `A` on the
    route, it tries `B` right after `A` (if `A` is the final destination it
    makes the crossing [..., d, B, d]); if demand `B->Y` leaves with `Y` on the
    route, it tries `B` right before `Y` -- and, when `Y` is the start `o` (a
    fixed position), it tries the dobradinha `[o, B, o, ...]`, unless `o == d`
    (then the route already ends at `o`, and the final-destination case covers
    it). Every trial is simulated in full (capacity per leg, whoever alights
    frees a seat) and the marginal score (passengers gained / extra time or /
    extra real) decides. When the state has a fixed `depot`, the simulation
    prefixes it (the deadhead); the depot is never inserted as a demand point
    because it is already the fixed start. Returns the best proposal, or None.
    """
    capacity = state.bus.passenger_capacity
    stops = state.stops
    depot = state.depot
    km_per_liter = state.bus.km_autonomy_per_liter
    last = len(stops) - 1
    if cost_model is not None:
        current_stops = with_depot(stops, depot)
        current = simulate_stops(
            data, current_stops, capacity, remaining, state.claimed
        )
        current_distance = route_distance_km(data.distance, current_stops)
        current_cost = cost_model.route_cost(
            current_distance, current.travel_minutes, km_per_liter
        )
    else:
        current = simulate_stops(
            data, with_depot(stops, depot), capacity, remaining, state.claimed
        )
    current_qty = {
        (origin, destination): quantity
        for origin, destination, quantity in current.pairs
    }
    known = set(stops)
    best: ExpansionProposal | None = None
    best_key: tuple | None = None

    def consider(candidate: int, trial: list[int]) -> None:
        nonlocal best, best_key
        trial_stops = with_depot(trial, depot)
        outcome = simulate_stops(
            data, trial_stops, capacity, remaining, state.claimed
        )
        if outcome.travel_minutes > time_limit_minutes or outcome.peak_load > capacity:
            return
        if cost_model is not None:
            trial_distance = route_distance_km(data.distance, trial_stops)
            trial_cost = cost_model.route_cost(
                trial_distance, outcome.travel_minutes, km_per_liter
            )
            score = marginal_passengers_per_real(
                outcome.passengers - current.passengers,
                trial_cost - current_cost,
            )
        else:
            trial_cost = 0.0
            score = marginal_passengers_per_minute(
                outcome.passengers - current.passengers,
                outcome.travel_minutes - current.travel_minutes,
            )
        if score <= 0:
            return
        claim = _claim_delta(current_qty, outcome.pairs)
        if not claim:
            return
        if cost_model is not None:
            key = (
                score,
                outcome.passengers,
                -trial_cost,
                -candidate,
                tuple(trial),
            )
        else:
            key = (
                score,
                outcome.passengers,
                -outcome.travel_minutes,
                -candidate,
                tuple(trial),
            )
        if best_key is None or key > best_key:
            best_key = key
            best = ExpansionProposal(
                state=state,
                stops=tuple(trial),
                claim=claim,
                new_points=tuple(
                    dict.fromkeys(node for node in trial if node not in known)
                ),
                travel_time_minutes=outcome.travel_minutes,
                peak_load=outcome.peak_load,
                score=score,
                cost=trial_cost,
            )

    for candidate in candidate_nodes(remaining, stops):
        if depot is not None and candidate == depot:
            continue  # the depot is already the fixed start
        # A->candidate arrives: place candidate right after A.
        for index, stop in enumerate(stops):
            if int(remaining[stop, candidate]) <= 0:
                continue
            if index == last:  # A is the final destination: [..., d, B, d]
                consider(candidate, stops + [candidate, stops[-1]])
            else:
                consider(
                    candidate,
                    stops[: index + 1] + [candidate] + stops[index + 1 :],
                )
        # candidate->Y leaves: place candidate right before Y.
        for index, stop in enumerate(stops):
            if int(remaining[candidate, stop]) <= 0:
                continue
            if index == 0:  # Y is the start: dobradinha [o, B, o, ...]
                if stops[0] == stops[-1]:  # o == d: the route already ends at o
                    continue
                consider(
                    candidate,
                    stops[:1] + [candidate] + stops[:1] + stops[1:],
                )
            else:
                consider(candidate, stops[:index] + [candidate] + stops[index:])
    return best
