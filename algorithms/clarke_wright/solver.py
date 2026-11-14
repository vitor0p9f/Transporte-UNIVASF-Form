"""Algoritmo principal do Clarke-Wright OVRP."""

import random

from .constants import (
    INF,
    ITER_POSTIMPROVE,
    ITER_TWO_PHASE,
    LAMBDA_MAX,
    LAMBDA_MIN,
    LAMBDA_PASSO,
)
from .construction import _fundir, two_phase_selection
from .improvement import post_improvement
from .metrics import _limite_texto, calcular_savings_ovrp
from .model import Contexto, Rota
from .objective import _obj_total


def clarke_wright_ovrp(
    ctx: Contexto,
    lam: float | None = None,
    usar_two_phase: bool = True,
    usar_postimprove: bool = True,
    iteracoes: int = ITER_TWO_PHASE,
    iter_postimprov: int = ITER_POSTIMPROVE,
    seed: int | None = 42,
    verbose: bool = True,
) -> tuple[list[Rota], float]:
    """Executa o Clarke-Wright OVRP completo (CW-1 + CW-2 + CW-3).

    Se λ não for fornecido, testa todos os valores de 0.1 a 2.0 (incremento
    0.1) e usa o que gerar menor custo total — conforme procedimento CW-1 do
    artigo (Tabela 1).

    `seed` fixa o gerador aleatório (two-phase + post-improvement) para que a
    execução seja reprodutível — essencial para reportar resultados em um
    artigo. Passe seed=None para variar a cada execução.

    A(s) restrição(ões) de capacidade/tempo vêm da chave em `ctx.restricoes`;
    a de tempo só tem efeito se `ctx.limite_tempo` for finito.

    Retorna:
        (rotas, lambda_usado)
    """
    if seed is not None:
        random.seed(seed)

    paradas_ativas = set(ctx.carga_parada.keys())

    if not paradas_ativas:
        if verbose:
            print("[clarke_wright] Nenhuma parada com demanda neste período.")
        return [], 0.0

    if verbose:
        print(
            f"\n[CW-OVRP] {len(paradas_ativas)} paradas | "
            f"sentido: {ctx.sentido} | depósito: {ctx.deposito} | "
            f"cap: {ctx.capacidade} | "
            f"limite: {_limite_texto(ctx.limite_tempo)} | "
            f"restrições: {ctx.restricoes.chave} | modelo: {ctx.modelo.nome}"
        )

    # ── CW-1: testa múltiplos λ e guarda o melhor ──────────────────────────
    lambdas = (
        [lam]
        if lam is not None
        else [
            round(LAMBDA_MIN + i * LAMBDA_PASSO, 1)
            for i in range(round((LAMBDA_MAX - LAMBDA_MIN) / LAMBDA_PASSO) + 1)
        ]
    )

    melhor_rotas: list[Rota] | None = None
    melhor_custo = INF
    melhor_lam = lambdas[0]

    for lam_valor in lambdas:
        savings = calcular_savings_ovrp(
            sorted(paradas_ativas), ctx, lam_valor
        )

        if usar_two_phase:
            rotas_lam = two_phase_selection(
                savings,
                paradas_ativas,
                ctx,
                iteracoes=iteracoes,
            )
        else:
            rotas_lam = _fundir(savings, paradas_ativas, ctx)

        custo_lam = _obj_total(rotas_lam)
        if verbose:
            maior_tempo = max((r.tempo_min for r in rotas_lam), default=0)
            print(
                f"  lam={lam_valor:.1f} -> {len(rotas_lam)} veiculos | "
                f"R${custo_lam:.2f} | "
                f"{sum(r.dist_km for r in rotas_lam):.1f} km | "
                f"maior rota {maior_tempo} min"
            )

        if custo_lam < melhor_custo:
            melhor_custo = custo_lam
            melhor_rotas = rotas_lam
            melhor_lam = lam_valor

    if verbose:
        print(f"\n  [OK] Melhor lam = {melhor_lam} | custo R${melhor_custo:.2f}")

    # ── CW-3: post-improvement sobre a melhor solução ──────────────────────
    if usar_postimprove and melhor_rotas:
        if verbose:
            print("  Aplicando post-improvement (2-opt / shift / swap)...")
        melhor_rotas = post_improvement(
            melhor_rotas,
            ctx,
            max_iter_sem_melhora=iter_postimprov,
        )
        custo_pos = _obj_total(melhor_rotas)
        if verbose:
            reducao = (
                round((melhor_custo - custo_pos) / melhor_custo * 100, 2)
                if melhor_custo > 0
                else 0.0
            )
            print(
                f"  [OK] Apos post-improvement: R${custo_pos:.2f} "
                f"(-{reducao}%)"
            )

    return melhor_rotas or [], melhor_lam
