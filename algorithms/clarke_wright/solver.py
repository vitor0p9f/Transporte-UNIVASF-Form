"""The Clarke-Wright OVRP algorithm itself."""

import random

from .constants import (
    INF,
    ITER_POSTIMPROVE,
    ITER_TWO_PHASE,
    LAMBDA_MAX,
    LAMBDA_MIN,
    LAMBDA_PASSO,
)
from .construction import _merge, two_phase_selection
from .improvement import post_improvement
from .metrics import _time_limit_text, compute_savings_ovrp
from .model import Context, Route
from .objective import _obj_total


def clarke_wright_ovrp(
    ctx: Context,
    lam: float | None = None,
    use_two_phase: bool = True,
    use_post_improvement: bool = True,
    iterations: int = ITER_TWO_PHASE,
    post_improvement_iterations: int = ITER_POSTIMPROVE,
    seed: int | None = 42,
    verbose: bool = True,
) -> tuple[list[Route], float]:
    """Run the complete Clarke-Wright OVRP (CW-1 + CW-2 + CW-3).

    When lambda is not given, every value from 0.1 to 2.0 (step 0.1) is tried
    and the cheapest one is used -- the CW-1 procedure of the paper (Table 1).

    `seed` fixes the random generator (two-phase + post-improvement) so the run
    is reproducible, which is essential to report results in a paper. Pass
    seed=None to vary on every run.

    The capacity/time constraint(s) come from the key in `ctx.restrictions`;
    the time one only has an effect when `ctx.max_time` is finite.

    Returns:
        (routes, lambda_used)
    """
    if seed is not None:
        random.seed(seed)

    active_stops = set(ctx.stop_loads.keys())

    if not active_stops:
        if verbose:
            print("[clarke_wright] Nenhuma parada com demanda neste período.")
        return [], 0.0

    if verbose:
        print(
            f"\n[CW-OVRP] {len(active_stops)} paradas | "
            f"sentido: {ctx.sense} | depósito: {ctx.depot} | "
            f"cap: {ctx.capacity} | "
            f"limite: {_time_limit_text(ctx.max_time)} | "
            f"restrições: {ctx.restrictions.key} | modelo: {ctx.bus_model.name}"
        )

    # ── CW-1: try several lambdas and keep the best ────────────────────────
    lambdas = (
        [lam]
        if lam is not None
        else [
            round(LAMBDA_MIN + i * LAMBDA_PASSO, 1)
            for i in range(round((LAMBDA_MAX - LAMBDA_MIN) / LAMBDA_PASSO) + 1)
        ]
    )

    best_routes: list[Route] | None = None
    best_cost = INF
    best_lambda = lambdas[0]

    for lambda_value in lambdas:
        savings = compute_savings_ovrp(
            sorted(active_stops), ctx, lambda_value
        )

        if use_two_phase:
            lambda_routes = two_phase_selection(
                savings,
                active_stops,
                ctx,
                iterations=iterations,
            )
        else:
            lambda_routes = _merge(savings, active_stops, ctx)

        lambda_cost = _obj_total(lambda_routes)
        if verbose:
            longest_time = max((r.time_minutes for r in lambda_routes), default=0)
            print(
                f"  lam={lambda_value:.1f} -> {len(lambda_routes)} veiculos | "
                f"R${lambda_cost:.2f} | "
                f"{sum(r.distance_km for r in lambda_routes):.1f} km | "
                f"maior rota {longest_time} min"
            )

        if lambda_cost < best_cost:
            best_cost = lambda_cost
            best_routes = lambda_routes
            best_lambda = lambda_value

    if verbose:
        print(f"\n  [OK] Melhor lam = {best_lambda} | custo R${best_cost:.2f}")

    # ── CW-3: post-improvement over the best solution ──────────────────────
    if use_post_improvement and best_routes:
        if verbose:
            print("  Aplicando post-improvement (2-opt / shift / swap)...")
        best_routes = post_improvement(
            best_routes,
            ctx,
            max_iterations_without_improvement=post_improvement_iterations,
        )
        improved_cost = _obj_total(best_routes)
        if verbose:
            reduction = (
                round((best_cost - improved_cost) / best_cost * 100, 2)
                if best_cost > 0
                else 0.0
            )
            print(
                f"  [OK] Apos post-improvement: R${improved_cost:.2f} "
                f"(-{reduction}%)"
            )

    return best_routes or [], best_lambda
