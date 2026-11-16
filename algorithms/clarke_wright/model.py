"""Data structures used by the Clarke-Wright OVRP heuristic."""

from dataclasses import dataclass, field

import numpy as np

from entities.bus import Bus

from .constants import RESTRICTIONS

#: One served origin->destination pair and its quantity.
Pair = tuple[int, int, int]
#: Immutable list of served pairs.
Pairs = tuple[Pair, ...]


@dataclass(frozen=True)
class Restrictions:
    """Which route constraints are active in this run.

    Build it from a key (`Restrictions.from_key("tempo")`) so the combination
    cannot be mistyped; the CLI and `build_context` only accept the keys of
    `RESTRICTIONS`.
    """

    capacity: bool = True
    time: bool = True

    @classmethod
    def from_key(cls, key: str) -> "Restrictions":
        try:
            capacity_on, time_on = RESTRICTIONS[key]
        except KeyError:
            valid_keys = ", ".join(RESTRICTIONS)
            raise ValueError(
                f"restrição '{key}' desconhecida (use: {valid_keys})"
            ) from None
        return cls(capacity=capacity_on, time=time_on)

    @property
    def key(self) -> str:
        """The key ("capacidade"/"tempo"/"ambas"/"nenhuma") of this combination."""
        for key, (capacity, time) in RESTRICTIONS.items():
            if (capacity, time) == (self.capacity, self.time):
                return key
        return "custom"


@dataclass(frozen=True)
class BusModel:
    """Operating cost model: fuel consumption/price and driver hourly rate.

    The data comes from one row of `fleet.csv` (capacity and autonomy) and from
    the scenario (diesel price).
    """

    name: str
    capacity: int
    km_per_liter: float
    diesel_price: float
    driver_hourly_rate: float = 0.0

    @property
    def cost_per_km(self) -> float:
        return self.diesel_price / self.km_per_liter

    def route_cost(self, distance_km: float, time_minutes: float = 0.0) -> float:
        return distance_km * self.cost_per_km + time_minutes / 60 * self.driver_hourly_rate


def bus_model(bus: Bus, diesel_price: float, driver_hourly_rate: float = 0.0) -> BusModel:
    """Turn one row of `fleet.csv` into the algorithm's cost model."""
    if bus.km_autonomy_per_liter <= 0:
        raise ValueError(f"bus {bus.id}: km_autonomy_per_liter deve ser > 0")
    return BusModel(
        name=f"ônibus {bus.id}",
        capacity=bus.passenger_capacity,
        km_per_liter=bus.km_autonomy_per_liter,
        diesel_price=diesel_price,
        driver_hourly_rate=driver_hourly_rate,
    )


@dataclass(frozen=True)
class Context:
    """Everything one route needs to be measured and validated.

    It carries both matrices, permitted endpoints, reference depot, limits and
    restriction key, so the internal functions share one context.

    `stop_loads` describes incident demand per node. Merge load is the union
    of touching OD pairs, not the sum of node loads. Raw OD demand also feeds
    the optimistic bound and exact selection/boarding evaluations.
    """

    distance: np.ndarray
    time: np.ndarray
    depot: int
    capacity: int
    max_time: float
    bus_model: BusModel
    stop_loads: dict[int, int]
    demand: np.ndarray
    restrictions: Restrictions = field(default_factory=Restrictions)
    sense: str = "ida"
    #: Vehicle cap of the scenario (None = no cap). CW does not know the
    #: fleet: it opens one route per stop and merges while the constraints
    #: allow. When the solution exceeds the cap, the extra routes would have no
    #: bus to operate them and are dropped by `limit_fleet`.
    max_routes: int | None = None
    #: Allowed route endpoints; None preserves the single-depot/open-end API.
    origins: tuple[int, ...] | None = None
    destinations: tuple[int, ...] | None = None
    _cache: dict = field(default_factory=dict, init=False, repr=False, compare=False)
    od_origins: np.ndarray = field(init=False, repr=False, compare=False)
    od_destinations: np.ndarray = field(init=False, repr=False, compare=False)
    od_quantities: tuple[int, ...] = field(init=False, repr=False, compare=False)
    touch_masks: tuple[int, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self):
        origins, destinations = np.nonzero(self.demand > 0)
        quantities = tuple(int(self.demand[o, d]) for o, d in zip(origins, destinations))
        masks = [0] * len(self.demand)
        for index, (o, d) in enumerate(zip(origins, destinations)):
            masks[o] |= 1 << index
            masks[d] |= 1 << index
        object.__setattr__(self, 'od_origins', origins)
        object.__setattr__(self, 'od_destinations', destinations)
        object.__setattr__(self, 'od_quantities', quantities)
        object.__setattr__(self, 'touch_masks', tuple(masks))

    def fits(self, load: int, minutes: float) -> bool:
        """Single check point: only the active constraint(s) are enforced."""
        if self.restrictions.capacity and load > self.capacity:
            return False
        return not self.restrictions.time or minutes <= self.max_time


@dataclass
class Saving:
    """Pair (i, j) with its computed saving."""

    i: int
    j: int
    value: float

    def __lt__(self, other: "Saving") -> bool:
        return self.value > other.value  # descending order


@dataclass
class Route:
    """Customer order plus selected endpoints and complete travel measures."""

    stops: list[int] = field(default_factory=list)
    load: int = 0  # static demand touching customer stops, OD pair counted once
    distance_km: float = 0.0  # total route distance (km)
    time_minutes: int = 0  # total route time (min)
    cost_brl: float = 0.0  # fuel cost (BRL)
    passengers: int = 0  # passengers served (simulation, after the solution)
    peak_load: int = 0  # highest simultaneous occupancy (simulation)
    pairs: Pairs = ()  # (origin, destination, quantity) boarded
    origin: int | None = None
    destination: int | None = None
    anchored: bool = False
    load_mask: int = 0
    node_mask: int = 0

    def first(self) -> int:
        return self.stops[0]

    def last(self) -> int:
        return self.stops[-1]


@dataclass(frozen=True)
class Attendance:
    """How much of the demand the routes actually deliver.

    `allocated` sums static per-route loads and may repeat a pair across
    different routes. It is a diagnostic, not transported passengers.
    `served` is deduplicated by shared boarding simulation and is the primary
    solution-selection criterion.
    """

    total_demand: int
    allocated: int
    served: int
    unserved: int
    peak_load: int
    served_pairs: Pairs = ()
    unserved_pairs: Pairs = ()

    @property
    def allocated_pct(self) -> float:
        return self.allocated / self.total_demand * 100 if self.total_demand else 0.0

    @property
    def served_pct(self) -> float:
        return self.served / self.total_demand * 100 if self.total_demand else 0.0
