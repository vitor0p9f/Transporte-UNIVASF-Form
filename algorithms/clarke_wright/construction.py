"""Construção OVRP: fusão de rotas, direction choice e two-phase selection."""

import random

from .constants import ITER_TWO_PHASE
from .metrics import _atualizar_custo, _dist_rota, _tempo_rota
from .model import Contexto, Rota, Saving
from .objective import _obj_total


def _melhor_direcao(paradas: list[int], ctx: Contexto) -> list[int]:
    """Procedimento CW-2: testa as duas direções da rota aberta.

    Em OVRP:
      forward : depot → p1 → p2 → ... → pn   (distância D_f)
      reverse : depot → pn → p(n-1) → ... → p1 (distância D_r)

    Com a restrição de tempo ativa a direção não é indiferente (o primeiro
    trecho sai do depósito), então direções que já estouram o limite são
    descartadas antes de escolher a mais curta. Se nenhuma couber, devolve a
    mais curta e quem chamou rejeita a rota em `Contexto.cabe`.
    """
    direcoes = [list(paradas), list(reversed(paradas))]
    if ctx.restricoes.tempo:
        viaveis = [d for d in direcoes if _tempo_rota(d, ctx) <= ctx.limite_tempo]
        if viaveis:
            direcoes = viaveis
    return min(direcoes, key=lambda d: _dist_rota(d, ctx))


def _fundir(
    savings: list[Saving],
    paradas_ativas: set[int],
    ctx: Contexto,
) -> list[Rota]:
    """Procedimento de fusão (route merging) do Clarke-Wright paralelo.

    Para cada saving s(i,j) em ordem decrescente:
      - Se i e j estão em rotas diferentes
      - Se a fusão não viola a(s) restrição(ões) ativa(s) (capacidade/tempo)
      - Se i é extremo (início ou fim) da sua rota
      - Se j é extremo da sua rota
      → funde as rotas

    Uma parada cuja demanda sozinha já estoura o limite continua virando rota
    própria (o algoritmo não descarta demanda); o relatório sinaliza o caso.
    """
    # Solução inicial: uma rota por parada
    rotas: dict[int, Rota] = {}
    extremo: dict[int, Rota] = {}  # extremo → rota que o contém

    for p in sorted(paradas_ativas):  # ordem fixa → resultado reprodutível
        r = Rota(paradas=[p], carga=ctx.carga_parada.get(p, 0))
        _atualizar_custo(r, ctx)
        rotas[id(r)] = r
        extremo[p] = r

    for s in savings:
        ri = extremo.get(s.i)
        rj = extremo.get(s.j)

        if ri is None or rj is None or ri is rj:
            continue

        carga = ri.carga + rj.carga
        if ctx.restricoes.capacidade and carga > ctx.capacidade:
            continue

        nova_ordem = None

        if ri.ultima() == s.i and rj.primeira() == s.j:
            nova_ordem = ri.paradas + rj.paradas
        elif rj.ultima() == s.j and ri.primeira() == s.i:
            nova_ordem = rj.paradas + ri.paradas
        elif ri.ultima() == s.i and rj.ultima() == s.j:
            nova_ordem = ri.paradas + list(reversed(rj.paradas))
        elif ri.primeira() == s.i and rj.primeira() == s.j:
            nova_ordem = list(reversed(ri.paradas)) + rj.paradas

        if nova_ordem is None:
            continue

        # Aplica CW-2: escolhe a melhor direção da rota aberta
        nova_ordem = _melhor_direcao(nova_ordem, ctx)
        if not ctx.cabe(carga, _tempo_rota(nova_ordem, ctx)):
            continue

        nova_rota = Rota(paradas=nova_ordem, carga=carga)
        _atualizar_custo(nova_rota, ctx)

        # Remove rotas antigas
        rotas.pop(id(ri), None)
        rotas.pop(id(rj), None)
        for p in ri.paradas + rj.paradas:
            extremo.pop(p, None)

        # Registra nova rota
        rotas[id(nova_rota)] = nova_rota
        extremo[nova_rota.primeira()] = nova_rota
        extremo[nova_rota.ultima()] = nova_rota

    return list(rotas.values())


def _roulette_wheel(savings: list[Saving], tamanho: int) -> list[Saving]:
    """Seleção por roleta sobre os `tamanho` melhores savings (seção 2.3).

    Reconstrói a lista de savings embaralhando probabilisticamente os
    melhores a cada iteração — explora ordens de fusão diferentes.

    Probabilidade (eq. do artigo): p_n = s_n / Σ s_i, favorecendo savings
    MAIORES. Como em OVRP s(i,j)=c(depot,j)-λ·c(i,j) pode ser negativo,
    deslocamos a janela pelo menor valor (em vez de usar abs(), que
    favoreceria erroneamente savings muito negativos).
    """
    if len(savings) <= 1:
        return list(savings)

    nova_lista = []
    restantes = list(savings)

    while restantes:
        janela = min(tamanho, len(restantes))
        candidatos = restantes[:janela]

        menor = min(s.valor for s in candidatos)
        pesos = [s.valor - menor + 1e-9 for s in candidatos]
        soma = sum(pesos)

        r = random.random() * soma
        acumulado = 0.0
        idx = janela - 1
        for k, w in enumerate(pesos):
            acumulado += w
            if r <= acumulado:
                idx = k
                break

        nova_lista.append(restantes.pop(idx))

    return nova_lista


def two_phase_selection(
    savings: list[Saving],
    paradas_ativas: set[int],
    ctx: Contexto,
    iteracoes: int = ITER_TWO_PHASE,
    peso_superlotacao: float = 0.0,
    conforto: int | None = None,
) -> list[Rota]:
    """Procedimento CW-2: reordena savings via roleta e guarda a melhor."""
    if conforto is None:
        conforto = ctx.modelo.capacidade_conforto or ctx.capacidade

    melhor_rotas = _fundir(savings, paradas_ativas, ctx)
    melhor_custo = _obj_total(melhor_rotas, peso_superlotacao, conforto)

    savings_atual = list(savings)

    for _ in range(iteracoes):
        # Tamanho do torneio T ∈ [3, 6] conforme o artigo (seção 2.3).
        tamanho_torneio = random.randint(
            3, min(6, max(3, len(savings_atual)))
        )
        nova_ordem = _roulette_wheel(savings_atual, tamanho_torneio)
        novas_rotas = _fundir(nova_ordem, paradas_ativas, ctx)
        novo_custo = _obj_total(novas_rotas, peso_superlotacao, conforto)

        if novo_custo < melhor_custo:
            melhor_custo = novo_custo
            melhor_rotas = novas_rotas
            savings_atual = nova_ordem

    return melhor_rotas
