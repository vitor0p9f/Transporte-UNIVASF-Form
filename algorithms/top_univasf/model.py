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
    """Resultado de um ônibus: rota final + o que ela atendeu.

    `origin`/`destination` são o par OD travado do ônibus: a rota nasce na
    origem do par, então os dois estão sempre definidos.
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
    """O que aconteceu na frota: rodadas, vitórias por ônibus e sobra."""

    rounds: int
    wins_per_bus: tuple[tuple[int, int], ...]  # (bus_id, commits)
    unserved_passengers: int
    unserved_pairs: tuple[ServedPair, ...]  # (o, d, q) por qtd desc


def fleet_summary(
    remaining: np.ndarray,
    wins: dict[int, int],
    rounds: int,
) -> FleetSummary:
    """Resumo final: rodadas, commits por ônibus e o que sobrou de demanda."""
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

    `passengers` counts only the demand boarded now; `claimed` demand the
    bus already holds occupies seats but is never counted again.
    """

    passengers: int
    travel_minutes: int
    peak_load: int
    pairs: tuple[ServedPair, ...]


@dataclass
class WorkState:
    """Estado interno: par OD travado + rota em crescimento."""

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

    `stops` is already the scored stretch: [o, d] or [o, P, d]. The bus is
    born at `origin`, so there is no deadhead.
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
        return (
            [("point", node) for node in self.new_points]
            + [("od", origin, destination) for origin, destination, _ in self.claim]
        )

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
