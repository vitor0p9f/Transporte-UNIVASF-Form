"""The round loop: every bus proposes, conflicts resolve, winners commit."""

import numpy as np

from algorithms.top_univasf.conflict import conflict_groups
from algorithms.top_univasf.cost import CostModel
from algorithms.top_univasf.draft import best_pair_for_bus
from algorithms.top_univasf.expansion import best_demand_driven_insertion
from algorithms.top_univasf.model import (
    BusPlan,
    DraftProposal,
    ExpansionProposal,
    FleetSummary,
    Proposal,
    ServedPair,
    WorkState,
    fleet_summary,
    with_depot,
)
from algorithms.top_univasf.scoring import (
    passengers_per_minute,
    passengers_per_real,
)
from algorithms.top_univasf.simulation import simulate_stops
from entities.bus import Bus
from utils.instances import InstanceData


def run_fleet(
    data: InstanceData,
    buses: list[Bus],
    time_limit_minutes: int,
    *,
    cost_model: CostModel | None = None,
    max_rounds: int | None = None,
    destinations: tuple[int, ...] | None = None,
    draft_origins: tuple[int, ...] | None = None,
    depot: int | None = None,
) -> tuple[list[BusPlan], FleetSummary]:
    """Single loop: every bus proposes its best step; without a conflict they
    commit together, in a conflict only the highest score acts.

    A bus without a locked pair proposes the pair's base route (score =
    boardings of the route [o, P, d] / route time or / route cost -- see
    `best_pair_for_bus`), restricted to the informed origins (`draft_origins`,
    None = free) and destinations (`destinations`, None = free); with a locked
    pair it proposes the demand-driven step (`best_demand_driven_insertion`).
    With `cost_model`, every score is passengers per real and each bus pays
    with its own km per liter; without it, the original passengers-per-minute
    objective is used.
    Everything is charged against the global demand. By default the route is
    born at the pair origin (no deadhead). When `depot` is set, every route is
    simulated with that fixed departure point as a prefix: the deadhead enters
    the time limit and the score, but the depot stays out of the demand route
    so it does not become a conflict point shared by every bus.
    """
    if not buses:
        return [], fleet_summary(data.demand.copy(), {}, 0)
    ids = [bus.id for bus in buses]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate bus ids in fleet: {sorted(ids)}")
    remaining = data.demand.copy()
    wins: dict[int, int] = {}
    rounds = 0
    state_by_id: dict[int, WorkState] = {}

    while int(remaining.sum()) > 0:
        if max_rounds is not None and rounds >= max_rounds:
            break
        proposals = collect_proposals(
            data,
            buses,
            state_by_id,
            remaining,
            time_limit_minutes,
            cost_model=cost_model,
            destinations=destinations,
            draft_origins=draft_origins,
            depot=depot,
        )
        if not proposals:
            break

        committed = 0
        for index in resolve_conflicts(proposals):
            proposal = proposals[index]
            if isinstance(proposal, DraftProposal):
                commit_draft(
                    proposal, data, remaining, state_by_id, wins, depot=depot
                )
            else:
                commit_expansion(proposal, remaining, wins)
            rounds += 1
            committed += 1
        if committed == 0:
            break

    return build_plans(buses, state_by_id, cost_model=cost_model), fleet_summary(
        remaining, wins, rounds
    )


def collect_proposals(
    data: InstanceData,
    buses: list[Bus],
    state_by_id: dict[int, WorkState],
    remaining: np.ndarray,
    time_limit_minutes: int,
    *,
    cost_model: CostModel | None = None,
    destinations: tuple[int, ...] | None = None,
    draft_origins: tuple[int, ...] | None = None,
    depot: int | None = None,
) -> list[Proposal]:
    """Every bus proposes one step over the SAME snapshot of `remaining`.

    A bus without a locked pair proposes the pair's base route; with a locked
    pair it proposes the demand-driven insertion. Nobody charges demand here.
    `cost_model` switches the scores to passengers per real; `depot` is
    forwarded to the draft so the deadhead enters its time and cost.
    """
    proposals: list[Proposal] = []
    draft_cache: dict[tuple, int] = {}
    for bus in buses:
        state = state_by_id.get(bus.id)
        if state is None:
            draft = best_pair_for_bus(
                data,
                bus,
                remaining,
                time_limit_minutes,
                cost_model=cost_model,
                destinations=destinations,
                draft_origins=draft_origins,
                cache=draft_cache,
                depot=depot,
            )
            if draft is not None:
                proposals.append(draft)
        elif state.travel_time_minutes < time_limit_minutes:
            expansion = best_demand_driven_insertion(
                data,
                state,
                remaining,
                time_limit_minutes,
                cost_model=cost_model,
            )
            if expansion is not None:
                proposals.append(expansion)
    return proposals


def resolve_conflicts(proposals: list[Proposal]) -> list[int]:
    """Indices that commit this round, in increasing order.

    Proposals sharing a point or an OD pair fall into the same group (directly
    or by transitivity) and only the highest score acts.
    """
    return sorted(
        max(group, key=lambda index: proposals[index].tie_break_key())
        for group in conflict_groups([proposal.conflict_keys() for proposal in proposals])
    )


def _claim_demand(
    remaining: np.ndarray,
    claimed: dict[tuple[int, int], int],
    pairs: tuple[ServedPair, ...],
) -> None:
    """Charge the global demand for what was boarded and accumulate it."""
    for origin, destination, quantity in pairs:
        claimed[(origin, destination)] = claimed.get((origin, destination), 0) + quantity
        remaining[origin, destination] = max(
            0, int(remaining[origin, destination]) - quantity
        )


def commit_draft(
    proposal: DraftProposal,
    data: InstanceData,
    remaining: np.ndarray,
    state_by_id: dict[int, WorkState],
    wins: dict[int, int],
    depot: int | None = None,
) -> None:
    """Lock the bus's pair and create its state with the base route.

    The base route already is [o, P, d]: re-simulating it over the current
    demand charges exactly what it boards under the capacity lock (hitchhikers
    included). When `depot` is set, the simulation includes the deadhead; the
    demand route stored in the state stays depot-free.
    """
    outcome = simulate_stops(
        data,
        with_depot(proposal.stops, depot),
        proposal.bus.passenger_capacity,
        remaining,
    )
    claimed: dict[tuple[int, int], int] = {}
    _claim_demand(remaining, claimed, outcome.pairs)
    state_by_id[proposal.bus.id] = WorkState(
        bus=proposal.bus,
        origin=proposal.origin,
        destination=proposal.destination,
        stops=list(proposal.stops),
        claimed=claimed,
        travel_time_minutes=proposal.travel_time_minutes,
        peak_load=outcome.peak_load,
        cost=proposal.cost,
        depot=depot,
    )
    wins[proposal.bus.id] = wins.get(proposal.bus.id, 0) + 1


def commit_expansion(
    proposal: ExpansionProposal,
    remaining: np.ndarray,
    wins: dict[int, int],
) -> None:
    """Accept the insertion into the bus state and charge what it picked up."""
    state = proposal.state
    state.stops = list(proposal.stops)
    state.travel_time_minutes = proposal.travel_time_minutes
    state.peak_load = proposal.peak_load
    state.cost = proposal.cost
    _claim_demand(remaining, state.claimed, proposal.claim)
    wins[state.bus.id] = wins.get(state.bus.id, 0) + 1


def build_plans(
    buses: list[Bus],
    state_by_id: dict[int, WorkState],
    *,
    cost_model: CostModel | None = None,
) -> list[BusPlan]:
    """One plan per bus that served somebody, ordered by bus id.

    A zero-score draft that never picked up a hitchhiker becomes a state with 0
    passengers and is dropped: a plan is what actually served a passenger.
    `cost_model` selects the passengers-per-real score; without it the score is
    passengers per minute.
    """
    plans = [
        BusPlan(
            bus_id=state.bus.id,
            origin=state.origin,
            destination=state.destination,
            stops=with_depot(tuple(state.stops), state.depot),
            served_passengers=state.served_passengers,
            travel_time_minutes=state.travel_time_minutes,
            peak_load=state.peak_load,
            score=(
                passengers_per_real(state.served_passengers, state.cost)
                if cost_model is not None
                else passengers_per_minute(
                    state.served_passengers, state.travel_time_minutes
                )
            ),
            cost=state.cost,
            served_pairs=tuple(
                (origin, destination, quantity)
                for (origin, destination), quantity in sorted(state.claimed.items())
                if quantity > 0
            ),
        )
        for state in (state_by_id[bus.id] for bus in buses if bus.id in state_by_id)
        if state.served_passengers > 0
    ]
    plans.sort(key=lambda plan: plan.bus_id)
    return plans
