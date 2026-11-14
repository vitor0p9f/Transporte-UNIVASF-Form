"""Measuring a stop sequence against the instance matrices.

Every heuristic walks a route as a sequence of node ids and asks the same two
questions about it: how far it drives and how long it takes. Both matrices are
indexed directly by node id (see `utils.matrices`), so one pass over the
consecutive legs answers them; a route that drives a node twice (dobradinha)
counts the leg every time it is driven.

An open route can also leave from a node that is not one of its stops -- the
depot -- and `start` charges that leg too without making the depot a stop.
"""

from collections.abc import Sequence
from itertools import pairwise

import numpy as np


def path_distance(
    distance: np.ndarray, stops: Sequence[int], *, start: int | None = None
) -> float:
    """Distance driven along `stops`, in km.

    A sequence shorter than two nodes drives nothing, so it costs 0.0.
    """
    if not stops:
        return 0.0
    total = float(distance[start, stops[0]]) if start is not None else 0.0
    for a, b in pairwise(stops):
        total += float(distance[a, b])
    return total


def path_time_minutes(
    time: np.ndarray, stops: Sequence[int], *, start: int | None = None
) -> int:
    """Travel time along `stops`, in minutes.

    A sequence shorter than two nodes takes no time.
    """
    if not stops:
        return 0
    total = int(time[start, stops[0]]) if start is not None else 0
    for a, b in pairwise(stops):
        total += int(time[a, b])
    return total
