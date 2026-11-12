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
#: Proposal ordering: score, passengers, -cost, -time, -bus id.
TieBreakKey = tuple[float, int, float, int, int]


def with_depot(stops: StopSequence, depot: int | None) -> StopSequence:
    """Prepend the fixed depot to a demand route, when it is not already first.

    The depot is a departure point, not a demand stop: it stays out of the
    demand route (the sequence used for conflict keys and ``new_points``) and
    enters only the sequence simulated for time and boarding. When the route
    already starts at the depot, the sequence is returned unchanged.
    """
    stops = tuple(stops)
    if depot is None or not stops or stops[0] == depot:
        return stops
    return (depot, *stops)


@dataclass(frozen=True)
class BusPlan:
    """One bus result: the final route plus what it served.

    `origin`/`destination` are the bus's locked OD pair. `stops` is the
    sequence actually driven; when the fleet runs with a fixed depot, it
    starts with that depot (the deadhead), so the pair origin may appear later.
    `score` is passengers per minute or per real, depending on the objective;
    `cost` is the fuel + driver cost of the route (0.0 for the time objective).
    """

    bus_id: int
    origin: int
    destination: int
    stops: StopSequence
    served_passengers: int
    travel_time_minutes: int
    peak_load: int
    score: float
    cost: float = 0.0
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
    """Internal state: the locked OD pair plus the route as it grows.

    `stops` is the demand route (without the depot). `depot` is the fixed
    departure point, if any: it is simulated as a prefix and is not part of
    the demand route. `cost` is the fuel + driver cost of the route so far.
    """

    bus: Bus
    origin: int
    destination: int
    stops: list[int]
    claimed: dict[tuple[int, int], int] = field(default_factory=dict)
    travel_time_minutes: int = 0
    peak_load: int = 0
    cost: float = 0.0
    depot: int | None = None

    @property
    def served_passengers(self) -> int:
        return sum(self.claimed.values())


@dataclass(frozen=True)
class DraftProposal:
    """A bus without a locked OD pair proposes the base route of one pair.

    `stops` is the demand route [o, d] or [o, P, d]. `depot` (when set) is the
    fixed departure point: it is simulated as a prefix and included in
    `travel_time_minutes`, but kept out of `stops` so every draft does not
    conflict on the same depot point. `score` is servable passengers per
    minute or per real, depending on the objective; `cost` is that route's
    fuel + driver cost (0.0 for the time objective).
    """

    bus: Bus
    origin: int
    destination: int
    stops: StopSequence
    served_passengers: int
    travel_time_minutes: int
    score: float
    cost: float = 0.0
    depot: int | None = None

    def conflict_keys(self) -> list[ConflictKey]:
        """Demand-route points plus the full-route OD sub-pairs.

        The depot prefix is not a point key (every draft would otherwise share
        it), but OD pairs boarded on the deadhead still conflict. When the pair
        origin is the depot, it remains a demand-route point.
        """
        full = with_depot(self.stops, self.depot)
        return (
            [("point", node) for node in self.stops]
            + [
                ("od", full[i], full[j])
                for i in range(len(full))
                for j in range(i + 1, len(full))
            ]
        )

    def tie_break_key(self) -> TieBreakKey:
        """Highest score wins; then more passengers, lower cost, less time, lower id."""
        return (
            self.score,
            self.served_passengers,
            -self.cost,
            -self.travel_time_minutes,
            -self.bus.id,
        )


@dataclass(frozen=True)
class ExpansionProposal:
    """A bus with a locked OD pair inserts one demand-driven point.

    `new_points` lists the nodes the insertion actually adds: in the
    dobradinha the repeated origin was already on the route. `score` is the
    marginal passengers per minute or per real; `cost` is the route's total
    fuel + driver cost (0.0 for the time objective).
    """

    state: WorkState
    stops: StopSequence
    claim: tuple[ServedPair, ...]
    new_points: tuple[int, ...]
    travel_time_minutes: int
    peak_load: int
    score: float
    cost: float = 0.0

    def conflict_keys(self) -> list[ConflictKey]:
        """The inserted points plus every OD pair the insertion claims."""
        return [("point", node) for node in self.new_points] + [
            ("od", origin, destination) for origin, destination, _ in self.claim
        ]

    def tie_break_key(self) -> TieBreakKey:
        """Highest score wins; then more passengers, lower cost, less time, lower id."""
        return (
            self.score,
            sum(quantity for _, _, quantity in self.claim),
            -self.cost,
            -self.travel_time_minutes,
            -self.state.bus.id,
        )


#: A step a bus asks to commit in one round.
Proposal = DraftProposal | ExpansionProposal
