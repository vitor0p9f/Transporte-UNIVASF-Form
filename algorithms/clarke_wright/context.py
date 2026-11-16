"""Trip sense, load per stop and context assembly."""

import numpy as np

from utils.instances import InstanceData

from .constants import DEFAULT_CAPACITY, DEFAULT_DIESEL_PRICE, DEFAULT_KM_PER_LITER, INF
from .model import BusModel, Context, Restrictions


def detect_sense(demand: np.ndarray, depot: int) -> str:
    """Tell whether the trip is "outbound" or "inbound" from the depot.

    - "volta": the depot is the campus people LEAVE from (they board there).
      Each stop's load is its number of ALIGHTINGS, since that is how many
      people get off at that point.
    - "ida": the depot is the origin and people board at the stops on their way
      to the campus. The load is the number of BOARDINGS.
    """
    boardings = int(demand[depot].sum())  # who leaves the depot
    alightings = int(demand[:, depot].sum())  # who arrives at the depot
    return "volta" if boardings > alightings else "ida"


def build_stop_loads(
    demand: np.ndarray,
    depot: int,
    sense: str = "auto",
) -> tuple[dict[int, int], str]:
    """Compute the load (passengers the bus carries) of every stop.

    Outbound the load comes from the boardings (matrix row); inbound, from the
    alightings (column) -- inbound almost everyone boards at the campus
    (depot), so each stop's real demand is how many people get OFF there.
    Returns `(stop_loads, used_sense)`.
    """
    if sense not in ("auto", "ida", "volta"):
        raise ValueError(f"sentido '{sense}' desconhecido (use: auto, ida, volta)")
    if sense == "auto":
        sense = detect_sense(demand, depot)

    per_node = demand.sum(axis=0) if sense == "volta" else demand.sum(axis=1)
    stop_loads = {
        node: int(per_node[node])
        for node in range(1, len(per_node))
        if node != depot and per_node[node] > 0
    }
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

    stop_loads, used_sense = build_stop_loads(
        data.demand, depot, sense
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
    )
