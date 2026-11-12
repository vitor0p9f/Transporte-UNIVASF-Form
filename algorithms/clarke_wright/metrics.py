"""Medidas de rota e fórmula de savings OVRP (CW-1)."""

import itertools

from .constants import INF
from .model import Contexto, Rota, Saving


def _dist_rota(paradas: list[int], ctx: Contexto) -> float:
    """Distância da rota aberta: depot → p1 → p2 → ... → pn.

    Não inclui retorno ao depósito (OVRP).
    """
    if not paradas:
        return 0.0
    dist = float(ctx.distancia[ctx.deposito, paradas[0]])
    for a, b in itertools.pairwise(paradas):
        dist += float(ctx.distancia[a, b])
    return round(dist, 4)


def _tempo_rota(paradas: list[int], ctx: Contexto) -> int:
    """Tempo total da rota aberta, em minutos (matriz `time` do cenário)."""
    if not paradas:
        return 0
    total = int(ctx.tempo[ctx.deposito, paradas[0]])
    for a, b in itertools.pairwise(paradas):
        total += int(ctx.tempo[a, b])
    return total


def _atualizar_custo(rota: Rota, ctx: Contexto) -> Rota:
    """Recalcula dist_km, tempo_min e custo_brl da rota."""
    rota.dist_km = _dist_rota(rota.paradas, ctx)
    rota.tempo_min = _tempo_rota(rota.paradas, ctx)
    rota.custo_brl = ctx.modelo.custo_rota(rota.dist_km)
    return rota


def _atualizar_rota(
    rota: Rota, paradas: list[int], carga: int, ctx: Contexto
) -> Rota:
    """Troca as paradas/carga e recalcula as medidas da rota."""
    rota.paradas = paradas
    rota.carga = carga
    return _atualizar_custo(rota, ctx)


def calcular_savings_ovrp(
    paradas: list[int],
    ctx: Contexto,
    lam: float,
) -> list[Saving]:
    """Fórmula OVRP modificada (equação 5 do artigo).

    s(i,j) = c(depot, j) - λ · c(i, j)

    Diferença em relação ao CVRP: remove o termo c(i, depot) porque o veículo
    não retorna ao depósito após visitar i.

    Args:
        paradas: lista de paradas (sem o depósito)
        ctx: matriz de distâncias + depósito
        lam: parâmetro de forma λ ∈ [0.1, 2.0]
    """
    savings = []
    for idx_i in range(len(paradas)):
        for idx_j in range(idx_i + 1, len(paradas)):
            pi, pj = paradas[idx_i], paradas[idx_j]

            # Equação 5 do artigo (OVRP com λ)
            s = float(ctx.distancia[ctx.deposito, pj]) - lam * float(
                ctx.distancia[pi, pj]
            )
            savings.append(Saving(i=pi, j=pj, valor=round(s, 6)))

    savings.sort()  # decrescente via __lt__
    return savings


def _limite_texto(limite: float) -> str:
    return "sem limite" if limite == INF else f"{limite:g} min"
