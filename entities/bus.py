from dataclasses import dataclass, field


@dataclass(frozen=True)
class Bus:
    """Immutable spec, one row of fleet.csv."""

    id: int
    passenger_capacity: int
    fuel_capacity: float
    km_autonomy_per_liter: float


@dataclass
class BusState:
    """Mutable occupancy of one bus along a route.

    to_alight[node_id] = how many passengers aboard will
    disembark at node_id. Invariant: aboard == sum(to_alight.values()).
    """

    spec: Bus
    aboard: int = 0
    to_alight: dict[int, int] = field(default_factory=dict)

    @property
    def free_seats(self) -> int:
        """Free seats available for boarding."""
        return self.spec.passenger_capacity - self.aboard

    def board(self, dest_id: int, quantity: int) -> int:
        """Board passengers bound for dest_id. Raises if over capacity."""
        if quantity > self.free_seats:
            raise ValueError(
                f"not enough free seats: need {quantity}, have {self.free_seats}"
            )
        self.to_alight[dest_id] = self.to_alight.get(dest_id, 0) + quantity
        self.aboard += quantity
        return quantity

    def arrive(self, node_id: int) -> int:
        """Alight everyone bound for node_id. Returns how many left."""
        quantity = self.to_alight.pop(node_id, 0)
        self.aboard -= quantity
        return quantity
