"""Trip sense, load per stop and context assembly."""

import numpy as np

from utils.instances import InstanceData

from .constants import (
    DEFAULT_CAPACITY,
    DEFAULT_DIESEL_PRICE,
    DEFAULT_DRIVER_HOURLY_RATE,
    DEFAULT_KM_PER_LITER,
    INF,
)
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
    capacity: int | None = None,
) -> tuple[dict[int, int], str]:
    """Compute the load (passengers the bus carries) of every stop.

    A node is a stop when someone boards there OR gets off there: a stop that
    only receives passengers still has to be visited, otherwise the demand that
    ends there can never be served. The depot is not a stop -- it is where the
    route starts and ends.

    The load of a stop is the demand that boards there: outbound, the
    boardings (matrix row); inbound, the alightings (column) -- inbound almost
    everyone boards at the campus, so the seats are released at the stops and
    each stop's projection is how many people get OFF there. Counting the
    boarding side only is what keeps the projection from taking a pair twice
    (once at its origin, once at its destination): the destination releases
    the seat, it does not occupy another one.

    `capacity`, when given, caps the projection: demand larger than one bus is
    served by more than one vehicle, so it cannot be allocated to a single
    route.

    The trip sense is still detected and returned: it describes the trip, not
    the set of stops. Returns `(stop_loads, used_sense)`.
    """
    if sense not in ("auto", "ida", "volta"):
        raise ValueError(f"sentido '{sense}' desconhecido (use: auto, ida, volta)")
    if sense == "auto":
        sense = detect_sense(demand, depot, origins)

    boardings = demand.sum(axis=1)
    alightings = demand.sum(axis=0)
    per_node = alightings if sense == "volta" else boardings
    stop_loads = {}
    for node in range(1, len(boardings)):
        # With multiple origins the reference depot can itself be visited by
        # a route starting elsewhere, so it must not lose its customer load.
        if node == depot and not (origins and len(origins) > 1):
            continue
        # Every node with demand belongs to the set, even when the boarding
        # side is zero: a stop that only receives passengers still has to be
        # visited.
        if boardings[node] <= 0 and alightings[node] <= 0:
            continue
        load = int(per_node[node])
        stop_loads[node] = min(load, capacity) if capacity else load
    return stop_loads, sense


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
            driver_hourly_rate=DEFAULT_DRIVER_HOURLY_RATE,
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
        data.demand, depot, sense, origins=origins, capacity=capacity
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
