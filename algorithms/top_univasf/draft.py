"""Stage 1: the best OD pair for one bus, with its scored base route."""

import numpy as np

from algorithms.top_univasf.cost import CostModel
from algorithms.top_univasf.model import (
    DraftProposal,
    StopSequence,
    with_depot,
)
from algorithms.top_univasf.scoring import od_pair_score, od_pair_score_real
from algorithms.top_univasf.simulation import segment_passengers
from entities.bus import Bus
from utils.instances import InstanceData


def best_pair_for_bus(
    data: InstanceData,
    bus: Bus,
    remaining: np.ndarray,
    time_limit_minutes: int,
    *,
    cost_model: CostModel | None = None,
    destinations: tuple[int, ...] | None = None,
    draft_origins: tuple[int, ...] | None = None,
    cache: dict[tuple, int] | None = None,
    depot: int | None = None,
) -> DraftProposal | None:
    """Best OD pair for one bus, already as a base-route proposal.

    For every candidate pair (o, d) -- `draft_origins`/`destinations` filter the
    selections available -- it looks in the demand graph for the points P with
    demand `o->P` or `P->d` and scores the route [o, P, d] plus the direct
    option [o, d]. Boarding respects capacity in route order (whoever alights at
    P frees a seat) and the score is `servable / time` or `servable / cost`,
    depending on the objective; the P with the highest score wins. The pair
    does NOT need direct demand `o->d`. When `depot` is set, the route is
    prefixed with the deadhead (time and, under the cost objective, distance),
    which enters both the time limit and the score; the depot is not a
    candidate P (it is already the fixed start). None when nothing is viable.
    """
    capacity = bus.passenger_capacity
    time = data.time
    distance = data.distance if cost_model is not None else None
    nodes = data.nodes
    if cache is None:
        cache = {}
    dest_set = set(destinations) if destinations else None
    draft_set = set(draft_origins) if draft_origins else None
    out_demand = {
        o: [p for p in nodes if p != o and int(remaining[o, p]) > 0]
        for o in nodes
    }
    in_demand = {
        d: [p for p in nodes if p != d and int(remaining[p, d]) > 0]
        for d in nodes
    }

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
            if distance is not None:
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
            direct_distance = float(distance[o, d]) if distance is not None else 0.0
            points = set(out_list)
            points.update(in_demand[d])
            points.discard(o)
            points.discard(d)
            # Candidate routes: the direct pair first (margin -1), then every
            # demand point P, in node order. Each carries its time and,
            # under the cost objective, its distance.
            options: list[tuple[int, StopSequence, int, float]] = [
                (
                    -1,
                    (o, d),
                    deadhead_time + direct_time,
                    deadhead_distance + direct_distance,
                )
            ]
            for p in sorted(points):
                if depot is not None and p == depot:
                    continue  # the depot is already the fixed start
                first_leg, second_leg = int(time[o, p]), int(time[p, d])
                if first_leg < 0 or second_leg < 0:
                    continue
                leg_distance = 0.0
                if distance is not None:
                    leg_distance = float(distance[o, p]) + float(distance[p, d])
                options.append(
                    (
                        p,
                        (o, p, d),
                        deadhead_time + first_leg + second_leg,
                        deadhead_distance + leg_distance,
                    )
                )
            for margin, stops, pair_time, pair_distance in options:
                if pair_time < 0 or pair_time > time_limit_minutes:
                    continue
                full_stops = with_depot(stops, depot)
                key_cache = (capacity, full_stops)
                served = cache.get(key_cache)
                if served is None:
                    served = segment_passengers(full_stops, capacity, remaining)
                    cache[key_cache] = served
                if pair_time == 0 and served > 0:
                    continue  # no time to serve it
                if cost_model is not None:
                    pair_cost = cost_model.route_cost(
                        pair_distance, pair_time, bus.km_autonomy_per_liter
                    )
                    score = od_pair_score_real(served, pair_cost)
                else:
                    pair_cost = 0.0
                    score = od_pair_score(served, pair_time)
                if score < 0:
                    continue
                # Score tie: more passengers, lower cost (cost objective),
                # shorter route, lower (o, d) and, last, the direct route: its
                # margin -1 beats any P >= 1. Under the time objective cost is
                # always 0.0, so the cost component does not affect the order.
                key = (score, served, -pair_cost, -pair_time, -o, -d, -margin)
                if best_key is None or key > best_key:
                    best_key = key
                    best = DraftProposal(
                        bus=bus,
                        origin=o,
                        destination=d,
                        stops=stops,
                        served_passengers=served,
                        travel_time_minutes=pair_time,
                        score=score,
                        cost=pair_cost,
                        depot=depot,
                    )
    return best
