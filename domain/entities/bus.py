from dataclasses import dataclass, field
from typing import NotRequired, TypedDict


class InternalState(TypedDict):
    label: NotRequired[str]
    alighting_demand: NotRequired[int]

def _create_empty_state() -> InternalState:
    return {}

@dataclass(frozen=True)
class Bus:
    id: int
    passenger_capacity: int
    fuel_capacity: float
    km_autonomy_per_liter: float
    internal_state: InternalState = field(default_factory=_create_empty_state)
