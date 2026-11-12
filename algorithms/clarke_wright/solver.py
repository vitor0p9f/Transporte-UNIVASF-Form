"""Algoritmo principal e análise de Pareto do Clarke-Wright OVRP."""

import random
from dataclasses import replace

from .constants import (
    INF,
    ITER_POSTIMPROVE,
    ITER_TWO_PHASE,
    LAMBDA_MAX,
    LAMBDA_MIN,
    LAMBDA_PASSO,
)
from .construction import _fundir, two_phase_selection
from .evaluation import avaliar_atendimento
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
    peso_superlotacao: float = 0.0,
    conforto: int | None = None,
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

    if conforto is None:
        conforto = ctx.modelo.capacidade_conforto or ctx.capacidade

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
                peso_superlotacao=peso_superlotacao,
                conforto=conforto,
            )
        else:
            rotas_lam = _fundir(savings, paradas_ativas, ctx)

        custo_lam = _obj_total(rotas_lam, peso_superlotacao, conforto)
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
            peso_superlotacao=peso_superlotacao,
            conforto=conforto,
        )
        custo_pos = _obj_total(melhor_rotas, peso_superlotacao, conforto)
        if verbose:
            reducao = round((melhor_custo - custo_pos) / melhor_custo * 100, 2)
            print(
                f"  [OK] Apos post-improvement: R${custo_pos:.2f} "
                f"(-{reducao}%)"
            )

    return melhor_rotas or [], melhor_lam


def analise_pareto(
    ctx: Contexto,
    capacidades: list[int] | None = None,
    verbose: bool = True,
) -> list[dict]:
    """Varre limites de lotação e mostra o trade-off custo × superlotação.

    Reduzir a capacidade efetiva força o algoritmo a usar MAIS ônibus,
    aliviando a lotação. Cada linha da tabela é uma política possível para o
    gestor.

    A chave de restrições de `ctx` é mantida em todos os pontos da varredura.
    Retorna uma lista de dicts (uma por capacidade testada).
    """
    if capacidades is None:
        # do conforto (todos sentados) até a lotação máxima do veículo
        cmin = ctx.modelo.capacidade_conforto or ctx.modelo.capacidade
        cmax = ctx.modelo.capacidade
        capacidades = sorted(set(range(cmin, cmax + 1, 4)) | {cmin, cmax})

    linhas = []
    for cap in capacidades:
        ctx_cap = replace(ctx, capacidade=cap)
        # Varredura usa CW-1 (rápido): basta para comparar níveis de conforto.
        rotas, _ = clarke_wright_ovrp(
            ctx_cap,
            usar_two_phase=False,
            usar_postimprove=False,
            verbose=False,
        )
        if not rotas:
            continue
        maior = max(r.carga for r in rotas)
        custo = round(sum(r.custo_brl for r in rotas), 2)
        dist = round(sum(r.dist_km for r in rotas), 1)
        tempo = max(r.tempo_min for r in rotas)
        atend = avaliar_atendimento(rotas, ctx_cap)
        linhas.append(
            {
                "cap_efetiva": cap,
                "veiculos": len(rotas),
                "dist_km": dist,
                "custo_brl": custo,
                "maior_onibus": maior,
                "maior_tempo": tempo,
                "ocup_maior_%": round(maior / ctx.modelo.capacidade * 100),
                "pax": atend.atendida,
                "pax_%": round(atend.pct_atendida),
            }
        )

    if verbose:
        print(f"\n{'=' * 78}")
        print("ANÁLISE DE PARETO  —  custo (combustível) × superlotação")
        print(
            f"Depósito: {ctx.deposito} | modelo: {ctx.modelo.nome} | "
            f"máx: {ctx.modelo.capacidade} | "
            f"conforto: {ctx.modelo.capacidade_conforto} | "
            f"restrições: {ctx.restricoes.chave}"
        )
        print(f"{'=' * 78}")
        print(
            f"  {'cap/ônibus':>11} | {'ônibus':>6} | {'km':>7} | "
            f"{'R$ comb.':>9} | {'maior':>6} | {'tempo':>6} | "
            f"{'pax':>5} | {'% lot.':>6}"
        )
        print(
            f"  {'-'*11} | {'-'*6} | {'-'*7} | {'-'*9} | {'-'*6} | "
            f"{'-'*6} | {'-'*5} | {'-'*6}"
        )
        for linha in linhas:
            print(
                f"  {linha['cap_efetiva']:>11} | {linha['veiculos']:>6} | "
                f"{linha['dist_km']:>7.1f} | {linha['custo_brl']:>9.2f} | "
                f"{linha['maior_onibus']:>6} | "
                f"{linha['maior_tempo']:>6} | "
                f"{linha['pax']:>5} | {linha['ocup_maior_%']:>5}%"
            )
        print()

    return linhas
