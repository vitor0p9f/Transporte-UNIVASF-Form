"""Boarding simulation: capacity-locked, ordered by route position."""

import itertools

import numpy as np

from algorithms.top_univasf.model import (
    BoardingOutcome,
    ServedPair,
    StopSequence,
)
from utils.instances import InstanceData


def board_greedily(
    stops: StopSequence,
    capacity: int,
    remaining: np.ndarray,
    leg_loads: list[int],
    *,
    deduplicate_pairs: bool,
) -> tuple[list[ServedPair], int]:
    """Greedy boarding under the capacity lock, in route order.

    Evaluation order: increasing origin, then destination. For each pair
    (o, d) the bus boards `min(demand, free seats on the busiest leg between o
    and d)` and fills the legs it drives. `leg_loads` is the per-leg occupancy
    state and may already carry seats the bus occupies for demand it has
    claimed; it is updated in place.

    `deduplicate_pairs` subtracts from the pair whatever boarded during this
    same call -- so a route that visits a node twice never boards a pair twice
    beyond the demand that exists. Turning it off is the draft's fast path
    (see `segment_passengers`).

    Returns:
        (pairs, passengers) with the pairs boarded now, in boarding order.
    """
    boarded: dict[tuple[int, int], int] = {}
    pairs: list[ServedPair] = []
    served = 0
    for origin_index, origin in enumerate(stops):
        for destination_index in range(origin_index + 1, len(stops)):
            destination = stops[destination_index]
            quantity = int(remaining[origin, destination])
            if deduplicate_pairs:
                quantity -= boarded.get((origin, destination), 0)
            if quantity <= 0:
                continue
            peak_in_range = max(leg_loads[origin_index:destination_index], default=0)
            room = capacity - peak_in_range
            if room <= 0:
                continue
            taken = min(quantity, room)
            for leg in range(origin_index, destination_index):
                leg_loads[leg] += taken
            if deduplicate_pairs:
                boarded[(origin, destination)] = taken + boarded.get(
                    (origin, destination), 0
                )
            pairs.append((origin, destination, taken))
            served += taken
    return pairs, served


def simulate_stops(
    data: InstanceData,
    stops: StopSequence,
    capacity: int,
    remaining: np.ndarray,
    claimed: dict[tuple[int, int], int] | None = None,
) -> BoardingOutcome:
    """Simulate one stop sequence. Returns (passengers, time, peak, pairs).

    Boarding under the capacity lock, in route order. `claimed` (demand the
    bus has already internalised) occupies seats but is never counted again in
    the returned pairs. Each boarding is charged against a local copy of the
    demand, so a pair never boards twice (route with a repeated node) beyond
    the demand that exists -- `remaining` is never changed.
    """
    stops = tuple(stops)
    travel = sum(int(data.time[a, b]) for a, b in itertools.pairwise(stops))
    leg_loads = [0] * max(0, len(stops) - 1)

    if claimed:
        first_index: dict[int, int] = {}
        last_index: dict[int, int] = {}
        for index, node in enumerate(stops):
            first_index.setdefault(node, index)
            last_index[node] = index
        for (origin, destination), quantity in sorted(claimed.items()):
            if quantity <= 0 or origin == destination:
                continue
            start = first_index.get(origin, -1)
            end = last_index.get(destination, -1)
            if start < 0 or end < 0 or start >= end:
                continue
            for leg in range(start, end):
                leg_loads[leg] += quantity

    pairs, served = board_greedily(
        stops, capacity, remaining, leg_loads, deduplicate_pairs=True
    )
    return BoardingOutcome(
        passengers=served,
        travel_minutes=travel,
        peak_load=max(leg_loads, default=0),
        pairs=tuple(pairs),
    )


def candidate_nodes(demand: np.ndarray, stops: list[int]) -> list[int]:
    """Nodes with demand (pickup or drop-off) that are still off the route."""
    blocked = set(stops)
    candidates: set[int] = set()
    for origin, destination in zip(*np.nonzero(demand)):
        if int(origin) not in blocked:
            candidates.add(int(origin))
        if int(destination) not in blocked:
            candidates.add(int(destination))
    return sorted(candidates)


def segment_passengers(
    stops: StopSequence, capacity: int, remaining: np.ndarray
) -> int:
    """Boardings along a short route segment (the draft's fast path).

    Same `board_greedily` as `simulate_stops`, without deduplicating pairs and
    without copying the demand matrix: the draft evaluates thousands of tiny
    routes per round.

    Every shape the draft evaluates ([o, d], [o, P, d] and [o, P, o]) never
    repeats an OD pair, so this fast path and `simulate_stops` board exactly
    the same passengers (see tests/test_units.py). A route repeating nodes in
    disjoint positions only happens during expansion, which uses
    `simulate_stops`.
    """
    leg_loads = [0] * max(0, len(stops) - 1)
    _, served = board_greedily(
        stops, capacity, remaining, leg_loads, deduplicate_pairs=False
    )
    return served
