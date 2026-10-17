"""Data the heuristic passes around: plans, proposals and work state."""

from dataclasses import dataclass, field

import numpy as np

from entities.bus import Bus

#: One served OD pair: (origin, destination, passengers).
ServedPair = tuple[int, int, int]
#: A route as node ids in visit order; nodes may repeat (dobradinha).
StopSequence = tuple[int, ...]
#: What two proposals fight over: ("point", node) or ("od", origin, destination).
ConflictKey = tuple[str, int] | tuple[str, int, int]


@dataclass(frozen=True)
class BusPlan:
    """One bus result: the final route plus what it served.

    `origin`/`destination` are the bus's locked OD pair: the route is born at
    the pair origin, so both are always set.
    """

    bus_id: int
    origin: int
    destination: int
    stops: StopSequence
    served_passengers: int
    travel_time_minutes: int
    peak_load: int
    score: float
    served_pairs: tuple[ServedPair, ...] = ()


@dataclass(frozen=True)
class FleetSummary:
    """What the fleet did: rounds, commits per bus and the demand left over."""

    rounds: int
    wins_per_bus: tuple[tuple[int, int], ...]  # (bus_id, commits won)
    unserved_passengers: int
    unserved_pairs: tuple[ServedPair, ...]  # (o, d, q), highest demand first


def fleet_summary(
    remaining: np.ndarray,
    wins: dict[int, int],
    rounds: int,
) -> FleetSummary:
    """Final summary: rounds, commits per bus and the demand left behind."""
    pairs = sorted(
        (
            (int(origin), int(destination), int(qty))
            for (origin, destination), qty in np.ndenumerate(remaining)
            if qty > 0
        ),
        key=lambda item: (-item[2], item[0], item[1]),
    )
    return FleetSummary(
        rounds=rounds,
        wins_per_bus=tuple(sorted(wins.items())),
        unserved_passengers=int(remaining.sum()),
        unserved_pairs=tuple(pairs),
    )


@dataclass(frozen=True, slots=True)
class BoardingOutcome:
    """What a candidate route would actually carry.

    `passengers` counts only the demand boarded now; demand the bus already
    holds (`claimed`) occupies seats but is never counted again.
    """

    passengers: int
    travel_minutes: int
    peak_load: int
    pairs: tuple[ServedPair, ...]


@dataclass
class WorkState:
    """Internal state: the locked OD pair plus the route as it grows."""

    bus: Bus
    origin: int
    destination: int
    stops: list[int]
    claimed: dict[tuple[int, int], int] = field(default_factory=dict)
    travel_time_minutes: int = 0
    peak_load: int = 0

    @property
    def served_passengers(self) -> int:
        return sum(self.claimed.values())


@dataclass(frozen=True)
class DraftProposal:
    """A bus without a locked OD pair proposes the base route of one pair.

    `stops` is already the scored route: [o, d] or [o, P, d]. The bus is born
    at `origin`, so there is no deadhead.
    """

    bus: Bus
    origin: int
    destination: int
    stops: StopSequence
    served_passengers: int
    travel_time_minutes: int
    score: float

    def conflict_keys(self) -> list[ConflictKey]:
        """Every point and every OD sub-pair of the base route."""
        return (
            [("point", node) for node in self.stops]
            + [
                ("od", self.stops[i], self.stops[j])
                for i in range(len(self.stops))
                for j in range(i + 1, len(self.stops))
            ]
        )

    def tie_break_key(self) -> tuple:
        """Highest score wins; then more passengers, less time, lower bus id."""
        return (
            self.score,
            self.served_passengers,
            -self.travel_time_minutes,
            -self.bus.id,
        )


@dataclass(frozen=True)
class ExpansionProposal:
    """A bus with a locked OD pair inserts one demand-driven point.

    `new_points` lists the nodes the insertion actually adds: in the
    dobradinha the repeated origin was already on the route.
    """

    state: WorkState
    stops: StopSequence
    claim: tuple[ServedPair, ...]
    new_points: tuple[int, ...]
    travel_time_minutes: int
    peak_load: int
    score: float

    def conflict_keys(self) -> list[ConflictKey]:
        """The inserted points plus every OD pair the insertion claims."""
        return [("point", node) for node in self.new_points] + [
            ("od", origin, destination) for origin, destination, _ in self.claim
        ]

    def tie_break_key(self) -> tuple:
        """Highest score wins; then more passengers, less time, lower bus id."""
        return (
            self.score,
            sum(quantity for _, _, quantity in self.claim),
            -self.travel_time_minutes,
            -self.state.bus.id,
        )


#: A step a bus asks to commit in one round.
Proposal = DraftProposal | ExpansionProposal
