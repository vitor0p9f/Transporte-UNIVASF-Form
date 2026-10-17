"""Boarding simulation: capacity-locked, ordered by route position."""

import itertools

import numpy as np

from algorithms.top_univasf.model import (
    BoardingOutcome,
    ServedPair,
    StopSequence,
)
from utils.instances import InstanceData


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
    position = {node: i for i, node in enumerate(stops)}
    n_legs = max(0, len(stops) - 1)
    leg_loads = [0] * n_legs

    first_index: dict[int, int] = {}
    last_index: dict[int, int] = {}
    for idx, node in enumerate(stops):
        first_index.setdefault(node, idx)
        last_index[node] = idx

    if claimed:
        for (origin, destination), qty in sorted(claimed.items()):
            if qty <= 0 or origin == destination:
                continue
            i = first_index.get(origin, -1)
            j = last_index.get(destination, -1)
            if i < 0 or j < 0 or i >= j:
                continue
            for leg in range(i, j):
                leg_loads[leg] += qty

    boardable: list[tuple[int, int, int, int]] = []
    for i, origin in enumerate(stops):
        for destination in stops[i + 1:]:
            if int(remaining[origin, destination]) > 0:
                boardable.append((i, position[destination], origin, destination))
    boardable.sort(key=lambda item: (item[0], item[1]))

    left = remaining.copy()  # abate local: 2ª passagem não reembarca o mesmo par
    pairs: list[ServedPair] = []
    served = 0
    for origin_idx, dest_idx, origin, destination in boardable:
        qty = int(left[origin, destination])
        if qty <= 0:
            continue
        peak_in_range = max(leg_loads[origin_idx:dest_idx], default=0)
        boarded = min(qty, max(0, capacity - peak_in_range))
        if boarded <= 0:
            continue
        for leg in range(origin_idx, dest_idx):
            leg_loads[leg] += boarded
        left[origin, destination] -= boarded
        pairs.append((origin, destination, boarded))
        served += boarded

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

    Mesma conta gulosa de `simulate_stops` (origem crescente, depois
    destino), mas sem copiar a matriz de demanda: o draft avalia milhares
    de trechos minúsculos por rodada.

    As formas que o draft avalia ([o, d], [o, P, d] e [o, P, o]) nunca
    repetem um par OD, então esta versão rápida e `simulate_stops` dão o
    mesmo embarque (ver tests/test_units.py). Rota com nó repetido em
    posições disjuntas só existe na expansão, que usa `simulate_stops`.
    """
    n = len(stops)
    leg_loads = [0] * (n - 1)
    served = 0
    for i in range(n):
        for j in range(i + 1, n):
            qty = int(remaining[stops[i], stops[j]])
            if qty <= 0:
                continue
            room = capacity - max(leg_loads[i:j], default=0)
            if room <= 0:
                continue
            boarded = min(qty, room)
            for leg in range(i, j):
                leg_loads[leg] += boarded
            served += boarded
    return served
