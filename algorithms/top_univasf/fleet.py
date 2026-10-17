"""The round loop: every bus proposes, conflicts resolve, winners commit."""

import numpy as np

from algorithms.top_univasf.conflict import conflict_groups
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
)
from algorithms.top_univasf.scoring import pax_per_min
from algorithms.top_univasf.simulation import simulate_stops
from entities.bus import Bus
from utils.instances import InstanceData


def run_fleet(
    data: InstanceData,
    buses: list[Bus],
    time_limit_minutes: int,
    *,
    max_rounds: int | None = None,
    destinations: tuple[int, ...] | None = None,
    draft_origins: tuple[int, ...] | None = None,
) -> tuple[list[BusPlan], FleetSummary]:
    """Loop único: todo ônibus propõe o melhor passo; sem conflito comitam
    juntos, em conflito só o maior score age.

    Sem par travado propõe a rota base do par (score = embarques do trecho
    `[o, P, d]` / tempo do trecho — ver `best_pair_for_bus`), só entre
    origens informadas (`draft_origins`, None = livre) e destinos informados
    (`destinations`, None = livre); com par propõe o passo guiado pela
    demanda (`best_demand_driven_insertion`).
    Tudo abate da demanda global. A rota nasce na origem do par: não há
    deslocamento vazio e a origem do cenário não é usada como posição fixa.
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
            destinations=destinations,
            draft_origins=draft_origins,
        )
        if not proposals:
            break

        committed = 0
        for index in resolve_conflicts(proposals):
            proposal = proposals[index]
            if isinstance(proposal, DraftProposal):
                commit_draft(proposal, data, remaining, state_by_id, wins)
            else:
                commit_expansion(proposal, remaining, wins)
            rounds += 1
            committed += 1
        if committed == 0:
            break

    return build_plans(buses, state_by_id), fleet_summary(remaining, wins, rounds)


def collect_proposals(
    data: InstanceData,
    buses: list[Bus],
    state_by_id: dict[int, WorkState],
    remaining: np.ndarray,
    time_limit_minutes: int,
    *,
    destinations: tuple[int, ...] | None = None,
    draft_origins: tuple[int, ...] | None = None,
) -> list[Proposal]:
    """Todo ônibus propõe um passo sobre a MESMA foto de `remaining`.

    Ônibus sem par travado propõe a rota base do par; com par travado,
    propõe a inserção guiada pela demanda. Ninguém abate demanda aqui.
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
                destinations=destinations,
                draft_origins=draft_origins,
                cache=draft_cache,
            )
            if draft is not None:
                proposals.append(draft)
        elif state.travel_time_minutes < time_limit_minutes:
            expansion = best_demand_driven_insertion(
                data, state, remaining, time_limit_minutes
            )
            if expansion is not None:
                proposals.append(expansion)
    return proposals


def resolve_conflicts(proposals: list[Proposal]) -> list[int]:
    """Índices que comitam nesta rodada, em ordem crescente.

    Propostas que compartilham ponto ou par OD caem no mesmo grupo (direto
    ou por transitividade) e só a de maior score age.
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
    """Abate da demanda global o que foi embarcado e acumula no estado."""
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
) -> None:
    """Trava o par do ônibus e cria o estado com a rota base.

    A rota base já é [o, P, d]: re-simula sobre a demanda atual para abater
    exatamente o que ela embarca com trava de capacidade (caronas
    incluídas).
    """
    outcome = simulate_stops(
        data, proposal.stops, proposal.bus.passenger_capacity, remaining
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
    )
    wins[proposal.bus.id] = wins.get(proposal.bus.id, 0) + 1


def commit_expansion(
    proposal: ExpansionProposal,
    remaining: np.ndarray,
    wins: dict[int, int],
) -> None:
    """Aceita a inserção no estado do ônibus e abate o que ela pegou."""
    state = proposal.state
    state.stops = list(proposal.stops)
    state.travel_time_minutes = proposal.travel_time_minutes
    state.peak_load = proposal.peak_load
    _claim_demand(remaining, state.claimed, proposal.claim)
    wins[state.bus.id] = wins.get(state.bus.id, 0) + 1


def build_plans(buses: list[Bus], state_by_id: dict[int, WorkState]) -> list[BusPlan]:
    """Um plano por ônibus que atendeu alguém, em ordem de id.

    O draft de score 0 que nunca pegou carona vira estado com pax 0 e é
    descartado: plano é o que de fato atendeu passageiro.
    """
    plans = [
        BusPlan(
            bus_id=state.bus.id,
            stops=tuple(state.stops),
            served_passengers=state.served_passengers,
            travel_time_minutes=state.travel_time_minutes,
            peak_load=state.peak_load,
            score=pax_per_min(state.served_passengers, state.travel_time_minutes),
            served_pairs=tuple(
                (origin, destination, quantity)
                for (origin, destination), quantity in sorted(state.claimed.items())
                if quantity > 0
            ),
            destination=state.destination,
            origin=state.origin,
        )
        for state in (state_by_id[bus.id] for bus in buses if bus.id in state_by_id)
        if state.served_passengers > 0
    ]
    plans.sort(key=lambda plan: plan.bus_id)
    return plans
