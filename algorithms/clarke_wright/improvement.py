"""Post-improvement local search (CW-3)."""

import random

from .constants import ITER_POSTIMPROVE
from .construction import _melhor_direcao
from .metrics import _atualizar_custo, _atualizar_rota, _dist_rota, _tempo_rota
from .model import Contexto, Rota
from .objective import _obj_total


def _2opt_rota(rota: Rota, ctx: Contexto) -> Rota:
    """2-opt intra-rota: inverte segmentos internos e mantém o melhor.

    Aplica CW-2 (melhor direção) após cada melhoria.

    A carga não muda, mas o tempo pode: com a restrição ativa, candidato que
    estoura o limite é descartado (a distância cair não garante tempo menor).
    """
    paradas = list(rota.paradas)

    melhorou = True
    while melhorou:
        melhorou = False
        dist_atual = _dist_rota(paradas, ctx)
        for i in range(len(paradas) - 1):
            for j in range(i + 2, len(paradas)):
                nova = (
                    paradas[: i + 1]
                    + list(reversed(paradas[i + 1 : j + 1]))
                    + paradas[j + 1 :]
                )
                nova = _melhor_direcao(nova, ctx)
                if not ctx.cabe(rota.carga, _tempo_rota(nova, ctx)):
                    continue
                d_nova = _dist_rota(nova, ctx)
                if d_nova < dist_atual - 1e-6:
                    paradas = nova
                    dist_atual = d_nova
                    melhorou = True

    rota.paradas = paradas
    return _atualizar_custo(rota, ctx)


def _shift_10(
    rotas: list[Rota],
    ctx: Contexto,
) -> list[Rota]:
    """Shift 1-0: move uma parada de uma rota para outra.

    Aceita se não violar a(s) restrição(ões) ativa(s) e se reduzir o objetivo
    (custo de combustível). Atualiza a carga das rotas.
    """
    melhorou = True
    while melhorou:
        melhorou = False
        for a in range(len(rotas)):
            for pos_i in range(len(rotas[a].paradas)):
                parada = rotas[a].paradas[pos_i]
                delta = ctx.carga_parada.get(parada, 0)

                for b in range(len(rotas)):
                    if a == b:
                        continue

                    carga_a = rotas[a].carga - delta
                    carga_b = rotas[b].carga + delta
                    if ctx.restricoes.capacidade and carga_b > ctx.capacidade:
                        continue

                    obj_antes = rotas[a].custo_brl + rotas[b].custo_brl

                    # Testa inserção no início e fim da rota b
                    for pos_j in [0, len(rotas[b].paradas)]:
                        novas_a = list(rotas[a].paradas)
                        novas_a.pop(pos_i)
                        novas_b = list(rotas[b].paradas)
                        novas_b.insert(pos_j, parada)

                        if not novas_a:
                            continue  # não cria rota vazia

                        novas_a = _melhor_direcao(novas_a, ctx)
                        novas_b = _melhor_direcao(novas_b, ctx)
                        if not (
                            ctx.cabe(carga_a, _tempo_rota(novas_a, ctx))
                            and ctx.cabe(carga_b, _tempo_rota(novas_b, ctx))
                        ):
                            continue

                        dist_a = _dist_rota(novas_a, ctx)
                        dist_b = _dist_rota(novas_b, ctx)
                        custo_a = ctx.modelo.custo_rota(dist_a)
                        custo_b = ctx.modelo.custo_rota(dist_b)
                        obj_depois = custo_a + custo_b

                        if obj_depois < obj_antes - 1e-6:
                            _atualizar_rota(rotas[a], novas_a, carga_a, ctx)
                            _atualizar_rota(rotas[b], novas_b, carga_b, ctx)
                            melhorou = True
                            break
                    if melhorou:
                        break
                if melhorou:
                    break
            if melhorou:
                break

    return rotas


def _swap_11(
    rotas: list[Rota],
    ctx: Contexto,
) -> list[Rota]:
    """Swap 1-1: troca uma parada entre duas rotas.

    Aceita se não violar a(s) restrição(ões) ativa(s) e se reduzir o objetivo
    (custo de combustível). Atualiza a carga das rotas.
    """
    melhorou = True
    while melhorou:
        melhorou = False
        for a in range(len(rotas)):
            for b in range(a + 1, len(rotas)):
                for pos_i in range(len(rotas[a].paradas)):
                    for pos_j in range(len(rotas[b].paradas)):
                        pi = rotas[a].paradas[pos_i]
                        pj = rotas[b].paradas[pos_j]
                        cp_i = ctx.carga_parada.get(pi, 0)
                        cp_j = ctx.carga_parada.get(pj, 0)

                        carga_a = rotas[a].carga - cp_i + cp_j
                        carga_b = rotas[b].carga - cp_j + cp_i
                        if ctx.restricoes.capacidade and (
                            carga_a > ctx.capacidade
                            or carga_b > ctx.capacidade
                        ):
                            continue

                        obj_antes = rotas[a].custo_brl + rotas[b].custo_brl

                        novas_a = list(rotas[a].paradas)
                        novas_b = list(rotas[b].paradas)
                        novas_a[pos_i] = pj
                        novas_b[pos_j] = pi

                        novas_a = _melhor_direcao(novas_a, ctx)
                        novas_b = _melhor_direcao(novas_b, ctx)
                        if not (
                            ctx.cabe(carga_a, _tempo_rota(novas_a, ctx))
                            and ctx.cabe(carga_b, _tempo_rota(novas_b, ctx))
                        ):
                            continue

                        dist_a = _dist_rota(novas_a, ctx)
                        dist_b = _dist_rota(novas_b, ctx)
                        custo_a = ctx.modelo.custo_rota(dist_a)
                        custo_b = ctx.modelo.custo_rota(dist_b)
                        obj_depois = custo_a + custo_b

                        if obj_depois < obj_antes - 1e-6:
                            _atualizar_rota(rotas[a], novas_a, carga_a, ctx)
                            _atualizar_rota(rotas[b], novas_b, carga_b, ctx)
                            melhorou = True
                            break
                    if melhorou:
                        break
                if melhorou:
                    break
            if melhorou:
                break

    return rotas


def post_improvement(
    rotas: list[Rota],
    ctx: Contexto,
    max_iter_sem_melhora: int = ITER_POSTIMPROVE,
) -> list[Rota]:
    """Procedimento CW-3: aplica busca local até não haver mais melhorias.

    Operadores (com igual probabilidade, conforme Tabela 1 do artigo):
      - 2-opt intra-rota
      - shift 1-0 inter-rotas
      - swap 1-1 inter-rotas
    """
    rotas = [_copiar_rota(r) for r in rotas]
    melhor_custo = _obj_total(rotas)
    iter_sem_melhora = 0

    operadores = [
        lambda r: [_2opt_rota(x, ctx) for x in r],
        lambda r: _shift_10(r, ctx),
        lambda r: _swap_11(r, ctx),
    ]

    while iter_sem_melhora < max_iter_sem_melhora:
        op = random.choice(operadores)
        rotas_novas = op(rotas)
        novo_custo = _obj_total(rotas_novas)

        if novo_custo < melhor_custo - 1e-6:
            melhor_custo = novo_custo
            rotas = rotas_novas
            iter_sem_melhora = 0
        else:
            iter_sem_melhora += 1

    return rotas


def _copiar_rota(rota: Rota) -> Rota:
    """Cópia da rota: os operadores do CW-3 a mutam no lugar."""
    return Rota(
        paradas=list(rota.paradas),
        carga=rota.carga,
        dist_km=rota.dist_km,
        tempo_min=rota.tempo_min,
        custo_brl=rota.custo_brl,
    )
