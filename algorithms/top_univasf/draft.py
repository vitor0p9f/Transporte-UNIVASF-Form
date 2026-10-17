"""Stage 1: the best OD pair for one bus, with its scored base route."""

import numpy as np

from algorithms.top_univasf.model import (
    DraftProposal,
    StopSequence,
)
from algorithms.top_univasf.scoring import od_pair_score
from algorithms.top_univasf.simulation import segment_passengers
from entities.bus import Bus
from utils.instances import InstanceData


def best_pair_for_bus(
    data: InstanceData,
    bus: Bus,
    remaining: np.ndarray,
    time_limit_minutes: int,
    destinations: tuple[int, ...] | None = None,
    draft_origins: tuple[int, ...] | None = None,
    cache: dict[tuple, int] | None = None,
) -> DraftProposal | None:
    """Best OD pair for one bus, already as a base-route proposal.

    For every candidate pair (o, d) -- `draft_origins`/`destinations` filter the
    selections available -- it looks in the demand graph for the points P with
    demand `o->P` or `P->d` and scores the route [o, P, d] plus the direct
    option [o, d]. Boarding respects capacity in route order (whoever alights at
    P frees a seat) and the score is `servable / (time[o, P] + time[P, d])`; the
    P with the highest score wins. The pair does NOT need direct demand `o->d`.
    The proposal already carries the scored route: the bus is born at the pair
    origin, so there is no deadhead. None when nothing is viable.
    """
    capacity = bus.passenger_capacity
    time = data.time
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
        for d in nodes:
            if dest_set is not None and d not in dest_set:
                continue
            if o == d and int(remaining[o, d]) > 0:
                continue  # a self-loop never boards
            direct_time = int(time[o, d])
            if direct_time < 0:
                continue
            points = set(out_list)
            points.update(in_demand[d])
            points.discard(o)
            points.discard(d)
            # Candidate routes: the direct pair first (margin -1), then every
            # demand point P, in node order.
            options: list[tuple[int, StopSequence, int]] = [(-1, (o, d), direct_time)]
            for p in sorted(points):
                first_leg, second_leg = int(time[o, p]), int(time[p, d])
                if first_leg < 0 or second_leg < 0:
                    continue
                options.append((p, (o, p, d), first_leg + second_leg))
            for margin, stops, pair_time in options:
                if pair_time < 0 or pair_time > time_limit_minutes:
                    continue
                key_cache = (capacity, stops)
                served = cache.get(key_cache)
                if served is None:
                    served = segment_passengers(stops, capacity, remaining)
                    cache[key_cache] = served
                if pair_time == 0 and served > 0:
                    continue  # no time to serve it
                score = od_pair_score(served, pair_time)
                if score < 0:
                    continue
                # Score tie: more passengers, shorter route, lower (o, d) and,
                # last, the P evaluated first (the direct option loses).
                key = (score, served, -pair_time, -o, -d, -margin)
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
                    )
    return best
