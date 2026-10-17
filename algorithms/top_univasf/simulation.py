"""Boarding simulation: capacity-locked, ordered by route position."""

import itertools

import numpy as np

from algorithms.top_univasf.model import (
    BoardingOutcome,
    ServedPair,
    StopSequence,
)
from utils.instances import InstanceData


def board_greedily(
    stops: StopSequence,
    capacity: int,
    remaining: np.ndarray,
    leg_loads: list[int],
    *,
    deduplicate_pairs: bool,
) -> tuple[list[ServedPair], int]:
    """Embarque guloso com trava de capacidade, na ordem da rota.

    Ordem de avaliação: origem crescente, depois destino. Para cada par
    (o, d) embarca `min(demanda, assentos livres no trecho mais cheio entre
    o e d)` e ocupa os trechos percorridos. `leg_loads` é o estado de
    ocupação por trecho e já pode vir preenchido com assentos que o ônibus
    ocupa por demanda já reivindicada; é atualizado no lugar.

    `deduplicate_pairs` abate do par o que já subiu nesta mesma chamada —
    uma rota com nó repetido nunca embarca um par duas vezes além do que
    existe. Desligar é a versão rápida do draft (ver `stretch_passengers`).

    Returns:
        (pairs, passengers), com os pares embarcados agora, em ordem de
        embarque.
    """
    boarded: dict[tuple[int, int], int] = {}
    pairs: list[ServedPair] = []
    served = 0
    for origin_index, origin in enumerate(stops):
        for destination_index in range(origin_index + 1, len(stops)):
            destination = stops[destination_index]
            quantity = int(remaining[origin, destination])
            if deduplicate_pairs:
                quantity -= boarded.get((origin, destination), 0)
            if quantity <= 0:
                continue
            peak_in_range = max(leg_loads[origin_index:destination_index], default=0)
            room = capacity - peak_in_range
            if room <= 0:
                continue
            taken = min(quantity, room)
            for leg in range(origin_index, destination_index):
                leg_loads[leg] += taken
            if deduplicate_pairs:
                boarded[(origin, destination)] = taken + boarded.get(
                    (origin, destination), 0
                )
            pairs.append((origin, destination, taken))
            served += taken
    return pairs, served


def simulate_stops(
    data: InstanceData,
    stops: StopSequence,
    capacity: int,
    remaining: np.ndarray,
    claimed: dict[tuple[int, int], int] | None = None,
) -> BoardingOutcome:
    """Simula uma sequência de paradas. Retorna (pax, tempo, pico, pares).

    Embarque com restrição de capacidade, na ordem da rota. `claimed`
    (demanda já internalizada pelo ônibus) ocupa assentos mas nunca é
    recontada nos pares retornados. Cada embarque abate uma cópia local da
    demanda, então um par nunca embarca duas vezes (rota com nó repetido)
    além do que existe — `remaining` nunca é alterada.
    """
    stops = tuple(stops)
    travel = sum(int(data.time[a, b]) for a, b in itertools.pairwise(stops))
    leg_loads = [0] * max(0, len(stops) - 1)

    if claimed:
        first_index: dict[int, int] = {}
        last_index: dict[int, int] = {}
        for index, node in enumerate(stops):
            first_index.setdefault(node, index)
            last_index[node] = index
        for (origin, destination), quantity in sorted(claimed.items()):
            if quantity <= 0 or origin == destination:
                continue
            start = first_index.get(origin, -1)
            end = last_index.get(destination, -1)
            if start < 0 or end < 0 or start >= end:
                continue
            for leg in range(start, end):
                leg_loads[leg] += quantity

    pairs, served = board_greedily(
        stops, capacity, remaining, leg_loads, deduplicate_pairs=True
    )
    return BoardingOutcome(
        passengers=served,
        travel_minutes=travel,
        peak_load=max(leg_loads, default=0),
        pairs=tuple(pairs),
    )


def candidate_nodes(demand: np.ndarray, stops: list[int]) -> list[int]:
    """Nós com demanda (embarque ou desembarque) ainda fora da rota."""
    blocked = set(stops)
    candidates: set[int] = set()
    for origin, destination in zip(*np.nonzero(demand)):
        if int(origin) not in blocked:
            candidates.add(int(origin))
        if int(destination) not in blocked:
            candidates.add(int(destination))
    return sorted(candidates)


def stretch_passengers(
    stops: StopSequence, capacity: int, remaining: np.ndarray
) -> int:
    """Embarques de um trecho curto do draft, com trava de capacidade.

    Mesmo `board_greedily` de `simulate_stops`, sem deduplicar pares e sem
    copiar a matriz de demanda: o draft avalia milhares de trechos
    minúsculos por rodada.

    As formas que o draft avalia ([o, d], [o, P, d] e [o, P, o]) nunca
    repetem um par OD, então aqui a versão rápida e `simulate_stops` dão o
    mesmo embarque (ver tests/test_units.py). Rota com nó repetido em
    posições disjuntas só existe na expansão, que usa `simulate_stops`.
    """
    leg_loads = [0] * max(0, len(stops) - 1)
    _, served = board_greedily(
        stops, capacity, remaining, leg_loads, deduplicate_pairs=False
    )
    return served
