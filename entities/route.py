from dataclasses import dataclass, field

from entities.bus import BusState


@dataclass
class Route:
    """One bus trip: stop sequence plus occupancy.

    Movement (add_stop) accumulates distance/time. Occupancy
    (alight_at/board_to) delegates to BusState and tracks peak_load.
    Costs (calc_cost) are derived on demand, never stored.
    """

    bus_state: BusState
    stops: list[int] = field(default_factory=list)
    total_distance_km: float = 0.0
    travel_time_minutes: int = 0
    peak_load: int = 0

    def add_stop(
        self,
        node_id: int,
        distance_from_prev_km: float = 0.0,
        time_from_prev_min: int = 0,
    ) -> None:
        """Append a stop and accumulate the leg distance/time."""
        self.stops.append(node_id)
        self.total_distance_km += distance_from_prev_km
        self.travel_time_minutes += time_from_prev_min

    def alight_at(self, node_id: int) -> int:
        """Drop off passengers bound for node_id."""
        return self.bus_state.arrive(node_id)

    def board_to(self, dest_id: int, quantity: int) -> int:
        """Pick up passengers bound for dest_id and update peak load."""
        boarded = self.bus_state.board(dest_id, quantity)
        if self.bus_state.aboard > self.peak_load:
            self.peak_load = self.bus_state.aboard
        return boarded

    def calc_cost(
        self, diesel_price_per_liter: float, driver_hourly_rate: float
    ) -> tuple[float, float, float, float]:
        """Return (fuel_liters, fuel_cost, driver_cost, operational_cost)."""
        fuel_liters = (
            self.total_distance_km / self.bus_state.spec.km_autonomy_per_liter
        )
        fuel_cost = fuel_liters * diesel_price_per_liter
        driver_cost = (self.travel_time_minutes / 60.0) * driver_hourly_rate
        return fuel_liters, fuel_cost, driver_cost, fuel_cost + driver_cost
