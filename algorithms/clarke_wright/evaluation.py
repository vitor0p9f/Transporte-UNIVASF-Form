"""Avaliação do atendimento e corte pela frota disponível."""

import numpy as np

from algorithms.top_univasf.simulation import simulate_stops
from utils.instances import InstanceData

from .model import Attendance, Context, Route


def _instance_from_context(ctx: Context) -> InstanceData:
    """`InstanceData` mínimo para a simulação (ela só lê tempo e demanda)."""
    return InstanceData(
        nodes=[], distance=ctx.distance, time=ctx.time, demand=ctx.demanda
    )


def _simulated_sequence(ctx: Context, route: Route) -> tuple[int, ...]:
    """A rota aberta como o simulador a vê: depósito + paradas."""
    return (ctx.depot, *route.stops)


def limit_fleet(routes: list[Route], ctx: Context) -> list[Route]:
    """Descarta rotas até a solução caber na frota do cenário.

    O CW não conhece o número de veículos: ele abre uma rota por parada e
    funde enquanto as restrições deixam, então pode terminar com mais rotas
    que ônibus. Rota sem veículo não opera; esta etapa escolhe, por simulação
    de embarque contra a demanda restante, as `ctx.max_rotas` que mais
    atendem e descarta o resto (a demanda delas fica como não atendida, do
    mesmo jeito que o TOP deixa o que não embarcou).

    Sem teto (`max_rotas is None`) ou quando a solução já cabe, é um no-op.
    """
    if ctx.max_routes is None or len(routes) <= ctx.max_routes:
        return routes

    instance = _instance_from_context(ctx)
    remaining = np.array(ctx.demanda, copy=True)
    candidates = list(routes)
    chosen: list[Route] = []

    def simulate(route: Route):
        return simulate_stops(
            instance,
            _simulated_sequence(ctx, route),
            ctx.capacity,
            remaining,
        )

    while candidates and len(chosen) < ctx.max_routes:
        # Uma simulação por candidata: a escolhida já vem com o resultado.
        outcome, best = max(
            ((simulate(route), route) for route in candidates),
            key=lambda pair: pair[0].passengers,
        )
        for origin, destination, quantity in outcome.pairs:
            remaining[origin, destination] -= quantity
        chosen.append(best)
        candidates = [route for route in candidates if route is not best]

    return chosen


def evaluate_attendance(routes: list[Route], ctx: Context) -> Attendance:
    """Mede o atendimento real de cada rota com a simulação do TOP UNIVASF.

    A rota do CW é aberta e começa no depósito, então a sequência simulada é
    `[depósito] + paradas` — o trecho que sai do depósito também ocupa
    assento. A demanda é cobrada em ordem: um par embarcado numa rota sai de
    `restante` e não é contado de novo na próxima.

    NÃO é critério de decisão: preenche `Rota.pax/pico/pares` depois que a
    solução está fechada.
    """
    remaining = np.array(ctx.demanda, copy=True)
    instance = _instance_from_context(ctx)
    all_pairs: list[tuple[int, int, int]] = []

    for route in routes:
        outcome = simulate_stops(
            instance,
            _simulated_sequence(ctx, route),
            ctx.capacity,
            remaining,
        )
        route.passengers = outcome.passengers
        route.peak_load = outcome.peak_load
        route.pairs = tuple(outcome.pairs)
        for origin, destination, quantity in outcome.pairs:
            remaining[origin, destination] -= quantity
        all_pairs.extend(outcome.pairs)

    total = int(ctx.demanda.sum())
    served = sum(r.passengers for r in routes)
    unserved = tuple(
        sorted(
            (
                (origin, destination, int(quantity))
                for (origin, destination), quantity in np.ndenumerate(remaining)
                if quantity > 0
            ),
            key=lambda pair: (-pair[2], pair[0], pair[1]),
        )
    )
    return Attendance(
        total_demand=total,
        allocated=sum(r.load for r in routes),
        served=served,
        unserved=total - served,
        peak_load=max((r.peak_load for r in routes), default=0),
        served_pairs=tuple(all_pairs),
        unserved_pairs=unserved,
    )
