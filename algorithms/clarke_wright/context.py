"""Trip sense, load per stop and context assembly."""

import numpy as np

from utils.instances import InstanceData

from .constants import DEFAULT_CAPACITY, DEFAULT_DIESEL_PRICE, DEFAULT_KM_PER_LITER, INF
from .model import BusModel, Context, Restrictions


def detect_sense(
    demand: np.ndarray, depot: int, origins: tuple[int, ...] | None = None
) -> str:
    """Tell whether the trip is "outbound" or "inbound" from the depot.

    - "volta": the depot is the campus people LEAVE from (they board there).
      Each stop's load is its number of ALIGHTINGS, since that is how many
      people get off at that point.
    - "ida": the depot is the origin and people board at the stops on their way
      to the campus. The load is the number of BOARDINGS.
    """
    allowed = list(origins or (depot,))
    boardings = int(demand[allowed, :].sum())
    alightings = int(demand[:, allowed].sum())
    return "volta" if boardings > alightings else "ida"


def build_stop_loads(
    demand: np.ndarray,
    depot: int,
    sense: str = "auto",
    *,
    origins: tuple[int, ...] | None = None,
) -> tuple[dict[int, int], str]:
    """Incident OD demand per node, including both pickups and drop-offs.

    Sense is retained as descriptive metadata; it no longer removes the
    opposite endpoint of a request. Merge load uses route_load rather than
    adding these per-node quantities, to avoid counting a pair twice.
    """
    if sense not in ("auto", "ida", "volta"):
        raise ValueError(f"sentido '{sense}' desconhecido (use: auto, ida, volta)")
    if sense == "auto":
        sense = detect_sense(demand, depot, origins)

    per_node = demand.sum(axis=0) + demand.sum(axis=1) - np.diag(demand)
    stop_loads = {
        node: int(per_node[node])
        for node in range(1, len(per_node))
        if per_node[node] > 0
    }
    return stop_loads, sense


def build_active_nodes(demand: np.ndarray) -> set[int]:
    """Every positive-demand pickup AND drop-off, including campus nodes."""
    return {int(n) for n in np.flatnonzero((demand > 0).any(axis=0) | (demand > 0).any(axis=1)) if n > 0}


def route_load(stops, ctx: Context) -> int:
    """Static CW load: OD demand touching any customer stop, each pair once.

    Chosen origin/destination anchors are not customer stops, just as a depot
    is not a CVRP customer. They are still visited and simulated for boarding.
    """
    if not ctx.od_quantities:
        return sum(ctx.stop_loads.get(n, 0) for n in set(stops))
    mask = 0
    for n in stops:
        mask |= ctx.touch_masks[n]
    cache = ctx._cache.setdefault('loads', {})
    if mask not in cache:
        total, remaining = 0, mask
        while remaining:
            bit = remaining & -remaining
            total += ctx.od_quantities[bit.bit_length() - 1]
            remaining ^= bit
        cache[mask] = total
    return cache[mask]


def build_context(
    data: InstanceData,
    depot: int,
    *,
    capacity: int | None = None,
    max_time: float | None = None,
    bus_model: BusModel | None = None,
    restrictions: Restrictions | str = "ambas",
    sense: str = "auto",
    max_routes: int | None = None,
    origins: tuple[int, ...] | None = None,
    destinations: tuple[int, ...] | None = None,
) -> Context:
    """Resolve the limits, the restriction key and the load per stop.

    `capacity` and `max_time` are independent of the model and of the scenario:
    when omitted, they come from them. Without a time limit the "tempo"
    constraint has no effect; without a given capacity, the model's one is
    used. `max_routes` is the scenario vehicle cap (None = no cap).
    """
    if isinstance(restrictions, str):
        restrictions = Restrictions.from_key(restrictions)

    if bus_model is None:
        model_capacity = (
            capacity if capacity is not None else DEFAULT_CAPACITY
        )
        bus_model = BusModel(
            name="genérico",
            capacity=model_capacity,
            km_per_liter=DEFAULT_KM_PER_LITER,
            diesel_price=DEFAULT_DIESEL_PRICE,
        )
    if capacity is None:
        capacity = bus_model.capacity
    if max_time is None:
        max_time = INF

    def endpoints(labels, name):
        if labels is None:
            return None
        result = tuple(sorted(set(labels)))
        if not result or any(node not in data.nodes for node in result):
            raise ValueError(f"{name} must contain valid instance node labels")
        return result

    origins = endpoints(origins, "origins")
    destinations = endpoints(destinations, "destinations")
    if depot not in data.nodes:
        raise ValueError("depot must be a valid instance node label")
    stop_loads, used_sense = build_stop_loads(
        data.demand, depot, sense, origins=origins
    )
    return Context(
        # float avoids surprises when the instance ships integer distances
        distance=data.distance.astype(float, copy=False),
        time=data.time,
        depot=depot,
        capacity=capacity,
        max_time=max_time,
        bus_model=bus_model,
        stop_loads=stop_loads,
        demand=data.demand,
        restrictions=restrictions,
        sense=used_sense,
        max_routes=max_routes,
        origins=origins,
        destinations=destinations,
    )
