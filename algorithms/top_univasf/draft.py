"""Stage 1: the best OD pair for one bus, with its scored base route."""

from typing import NamedTuple

import numpy as np

from algorithms.top_univasf.cost import CostModel
from algorithms.top_univasf.model import (
    DraftProposal,
    StopSequence,
    with_depot,
)
from algorithms.top_univasf.scoring import od_pair_score_real
from algorithms.top_univasf.simulation import segment_passengers
from entities.bus import Bus
from utils.instances import InstanceData

#: Cache of segment boardings keyed by (capacity, simulated stops).
DraftCache = dict[tuple[int, StopSequence], int]


class _DraftOption(NamedTuple):
    """One candidate base route before it is scored."""

    margin: int
    stops: StopSequence
    minutes: int
    distance_km: float


def _demand_neighbors(
    remaining: np.ndarray, nodes: list[int]
) -> tuple[dict[int, list[int]], dict[int, list[int]]]:
    """Outgoing and incoming demand neighbours for every node."""
    out_demand: dict[int, list[int]] = {}
    in_demand: dict[int, list[int]] = {}
    for node in nodes:
        out_demand[node] = [
            other
            for other in nodes
            if other != node and int(remaining[node, other]) > 0
        ]
        in_demand[node] = [
            other
            for other in nodes
            if other != node and int(remaining[other, node]) > 0
        ]
    return out_demand, in_demand


def best_pair_for_bus(
    data: InstanceData,
    bus: Bus,
    remaining: np.ndarray,
    time_limit_minutes: int,
    *,
    cost_model: CostModel,
    destinations: tuple[int, ...] | None = None,
    draft_origins: tuple[int, ...] | None = None,
    cache: DraftCache | None = None,
    depot: int | None = None,
) -> DraftProposal | None:
    """Best OD pair for one bus, already as a base-route proposal.

    For every candidate pair (o, d) -- `draft_origins`/`destinations` filter the
    selections available -- it looks in the demand graph for the points P with
    demand `o->P` or `P->d` and scores the route [o, P, d] plus the direct
    option [o, d]. Boarding respects capacity in route order (whoever alights at
    P frees a seat) and the score is `servable passengers / route cost`; the P
    with the highest score wins. The pair does NOT need direct demand `o->d`.
    When `depot` is set, the route is prefixed with the deadhead (time and
    distance), which enters both the time limit and the score; the depot is not
    a candidate P (it is already the fixed start). None when nothing is viable.
    """
    capacity = bus.passenger_capacity
    time = data.time
    distance = data.distance
    nodes = data.nodes
    if cache is None:
        cache = {}
    dest_set = set(destinations) if destinations else None
    draft_set = set(draft_origins) if draft_origins else None
    out_demand, in_demand = _demand_neighbors(remaining, nodes)

    best: DraftProposal | None = None
    best_key: tuple | None = None
    for o in nodes:
        if draft_set is not None and o not in draft_set:
            continue
        out_list = out_demand[o]
        deadhead_time = 0
        deadhead_distance = 0.0
        if depot is not None and depot != o:
            deadhead_time = int(time[depot, o])
            if deadhead_time < 0:
                continue
            deadhead_distance = float(distance[depot, o])
        for d in nodes:
            if dest_set is not None and d not in dest_set:
                continue
            if o == d and (depot is not None or int(remaining[o, d]) > 0):
                # A self-loop never boards. With a depot prefix it would also
                # repeat the depot node and break the draft fast path.
                continue
            direct_time = int(time[o, d])
            if direct_time < 0:
                continue
            direct_distance = float(distance[o, d])
            points = set(out_list)
            points.update(in_demand[d])
            points.discard(o)
            points.discard(d)
            # Candidate routes: the direct pair first (margin -1), then every
            # demand point P, in node order. Each carries its time and distance.
            options: list[_DraftOption] = [
                _DraftOption(
                    margin=-1,
                    stops=(o, d),
                    minutes=deadhead_time + direct_time,
                    distance_km=deadhead_distance + direct_distance,
                )
            ]
            for p in sorted(points):
                if depot is not None and p == depot:
                    continue  # the depot is already the fixed start
                first_leg, second_leg = int(time[o, p]), int(time[p, d])
                if first_leg < 0 or second_leg < 0:
                    continue
                leg_distance = float(distance[o, p]) + float(distance[p, d])
                options.append(
                    _DraftOption(
                        margin=p,
                        stops=(o, p, d),
                        minutes=deadhead_time + first_leg + second_leg,
                        distance_km=deadhead_distance + leg_distance,
                    )
                )
            for option in options:
                if option.minutes < 0 or option.minutes > time_limit_minutes:
                    continue
                full_stops = with_depot(option.stops, depot)
                key_cache = (capacity, full_stops)
                served = cache.get(key_cache)
                if served is None:
                    served = segment_passengers(full_stops, capacity, remaining)
                    cache[key_cache] = served
                if option.minutes == 0 and served > 0:
                    continue  # no time to serve it
                pair_cost = cost_model.route_cost(
                    option.distance_km,
                    option.minutes,
                    bus.km_autonomy_per_liter,
                )
                score = od_pair_score_real(served, pair_cost)
                # Score tie: more passengers, lower cost, shorter route, lower
                # (o, d) and, last, the direct route: its margin -1 beats any
                # P >= 1.
                key = (
                    score,
                    served,
                    -pair_cost,
                    -option.minutes,
                    -o,
                    -d,
                    -option.margin,
                )
                if best_key is None or key > best_key:
                    best_key = key
                    best = DraftProposal(
                        bus=bus,
                        origin=o,
                        destination=d,
                        stops=option.stops,
                        served_passengers=served,
                        travel_time_minutes=option.minutes,
                        score=score,
                        cost=pair_cost,
                        depot=depot,
                    )
    return best
