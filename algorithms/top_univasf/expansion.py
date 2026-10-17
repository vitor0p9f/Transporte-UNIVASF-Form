"""Stage 2: one demand-driven insertion for a bus with a locked OD pair."""

import numpy as np

from algorithms.top_univasf.model import (
    ExpansionProposal,
    WorkState,
)
from algorithms.top_univasf.scoring import marginal_pax_per_min
from algorithms.top_univasf.simulation import candidate_nodes, simulate_stops
from utils.instances import InstanceData


def best_demand_driven_insertion(
    data: InstanceData,
    state: WorkState,
    remaining: np.ndarray,
    time_limit_minutes: int,
) -> ExpansionProposal | None:
    """Passo guiado pela demanda: a posição do ponto novo vem do par.

    Para cada ponto fora da rota: se chega demanda `A→B` com `A` na rota,
    testa `B` logo depois de `A` (se `A` é o destino final, faz a cruzada
    [..., d, B, d]); se sai demanda `B→Y` com `Y` na rota, testa `B` logo
    antes de `Y` — e, quando `Y` é a partida `o` (posição fixa), testa a
    dobradinha `[o, B, o, ...]`, exceto se `o == d` (aí o fim da rota já é
    o próprio `o` e o caso do destino final cobre). Cada trial é simulada
    inteira (capacidade por trecho, quem desce libera assento) e vale o
    score marginal (ganho de pax / minutos extras). Devolve a melhor
    proposta de expansão, ou None.
    """
    capacity = state.bus.passenger_capacity
    stops = state.stops
    last = len(stops) - 1
    current = simulate_stops(data, stops, capacity, remaining, state.claimed)
    current_qty = {(origin, destination): qty for origin, destination, qty in current.pairs}
    best: ExpansionProposal | None = None
    best_key: tuple | None = None

    def consider(candidate: int, trial: list[int]) -> None:
        nonlocal best, best_key
        outcome = simulate_stops(data, trial, capacity, remaining, state.claimed)
        if outcome.travel_minutes > time_limit_minutes or outcome.peak_load > capacity:
            return
        score = marginal_pax_per_min(
            outcome.passengers - current.passengers,
            outcome.travel_minutes - current.travel_minutes,
        )
        if score <= 0:
            return
        claim = tuple(
            sorted(
                (origin, destination, qty - current_qty.get((origin, destination), 0))
                for origin, destination, qty in outcome.pairs
                if qty > current_qty.get((origin, destination), 0)
            )
        )
        if not claim:
            return
        key = (score, outcome.passengers, -outcome.travel_minutes, -candidate, tuple(trial))
        if best_key is None or key > best_key:
            known = set(stops)
            best_key = key
            best = ExpansionProposal(
                state=state,
                stops=tuple(trial),
                claim=claim,
                new_points=tuple(dict.fromkeys(n for n in trial if n not in known)),
                travel_time_minutes=outcome.travel_minutes,
                peak_load=outcome.peak_load,
                score=score,
            )

    for candidate in candidate_nodes(remaining, stops):
        for index, stop in enumerate(stops):  # chega A→cand: cand logo depois de A
            if int(remaining[stop, candidate]) <= 0:
                continue
            if index == last:  # A é o destino final: cruzada [..., d, cand, d]
                consider(candidate, stops + [candidate, stops[-1]])
            else:
                consider(candidate, stops[:index + 1] + [candidate] + stops[index + 1:])
        for index, stop in enumerate(stops):  # sai cand→Y: cand logo antes de Y
            if int(remaining[candidate, stop]) <= 0:
                continue
            if index == 0:  # Y é a partida: dobradinha [o, cand, o, ...]
                if stops[0] == stops[-1]:  # o == d: o fim já é o o
                    continue
                consider(candidate, stops[:1] + [candidate] + stops[:1] + stops[1:])
            else:
                consider(candidate, stops[:index] + [candidate] + stops[index:])
    return best
