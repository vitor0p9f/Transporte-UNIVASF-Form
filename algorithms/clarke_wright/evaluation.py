"""Avaliação do atendimento e corte pela frota disponível."""

import numpy as np

from algorithms.top_univasf.simulation import simulate_stops
from utils.instances import InstanceData

from .model import Atendimento, Contexto, Rota


def _instancia_do_contexto(ctx: Contexto) -> InstanceData:
    """`InstanceData` mínimo para a simulação (ela só lê tempo e demanda)."""
    return InstanceData(
        nodes=[], distance=ctx.distancia, time=ctx.tempo, demand=ctx.demanda
    )


def _sequencia_simulada(ctx: Contexto, rota: Rota) -> tuple[int, ...]:
    """A rota aberta como o simulador a vê: depósito + paradas."""
    return (ctx.deposito, *rota.paradas)


def limitar_frota(rotas: list[Rota], ctx: Contexto) -> list[Rota]:
    """Descarta rotas até a solução caber na frota do cenário.

    O CW não conhece o número de veículos: ele abre uma rota por parada e
    funde enquanto as restrições deixam, então pode terminar com mais rotas
    que ônibus. Rota sem veículo não opera; esta etapa escolhe, por simulação
    de embarque contra a demanda restante, as `ctx.max_rotas` que mais
    atendem e descarta o resto (a demanda delas fica como não atendida, do
    mesmo jeito que o TOP deixa o que não embarcou).

    Sem teto (`max_rotas is None`) ou quando a solução já cabe, é um no-op.
    """
    if ctx.max_rotas is None or len(rotas) <= ctx.max_rotas:
        return rotas

    instancia = _instancia_do_contexto(ctx)
    restante = np.array(ctx.demanda, copy=True)
    candidatas = list(rotas)
    escolhidas: list[Rota] = []

    def simular(rota: Rota):
        return simulate_stops(
            instancia,
            _sequencia_simulada(ctx, rota),
            ctx.capacidade,
            restante,
        )

    while candidatas and len(escolhidas) < ctx.max_rotas:
        # Uma simulação por candidata: a escolhida já vem com o resultado.
        resultado, melhor = max(
            ((simular(rota), rota) for rota in candidatas),
            key=lambda par: par[0].passengers,
        )
        for origem, destino, quantidade in resultado.pairs:
            restante[origem, destino] -= quantidade
        escolhidas.append(melhor)
        candidatas = [rota for rota in candidatas if rota is not melhor]

    return escolhidas


def avaliar_atendimento(rotas: list[Rota], ctx: Contexto) -> Atendimento:
    """Mede o atendimento real de cada rota com a simulação do TOP UNIVASF.

    A rota do CW é aberta e começa no depósito, então a sequência simulada é
    `[depósito] + paradas` — o trecho que sai do depósito também ocupa
    assento. A demanda é cobrada em ordem: um par embarcado numa rota sai de
    `restante` e não é contado de novo na próxima.

    NÃO é critério de decisão: preenche `Rota.pax/pico/pares` depois que a
    solução está fechada.
    """
    restante = np.array(ctx.demanda, copy=True)
    instancia = _instancia_do_contexto(ctx)
    pares_totais: list[tuple[int, int, int]] = []

    for rota in rotas:
        resultado = simulate_stops(
            instancia,
            _sequencia_simulada(ctx, rota),
            ctx.capacidade,
            restante,
        )
        rota.pax = resultado.passengers
        rota.pico = resultado.peak_load
        rota.pares = tuple(resultado.pairs)
        for origem, destino, quantidade in resultado.pairs:
            restante[origem, destino] -= quantidade
        pares_totais.extend(resultado.pairs)

    total = int(ctx.demanda.sum())
    atendida = sum(r.pax for r in rotas)
    nao_atendidos = tuple(
        sorted(
            (
                (origem, destino, int(quantidade))
                for (origem, destino), quantidade in np.ndenumerate(restante)
                if quantidade > 0
            ),
            key=lambda par: (-par[2], par[0], par[1]),
        )
    )
    return Atendimento(
        demanda_total=total,
        alocada=sum(r.carga for r in rotas),
        atendida=atendida,
        nao_atendida=total - atendida,
        pico=max((r.pico for r in rotas), default=0),
        pares_atendidos=tuple(pares_totais),
        pares_nao_atendidos=nao_atendidos,
    )
