"""The Clarke-Wright OVRP algorithm itself."""

import random

from .anchoring import anchor_routes
from .constants import (
    ITER_POSTIMPROVE,
    ITER_TWO_PHASE,
    LAMBDA_MAX,
    LAMBDA_MIN,
    LAMBDA_PASSO,
)
from .construction import _merge, two_phase_selection
from .evaluation import limit_fleet
from .improvement import post_improvement
from .metrics import _time_limit_text, compute_savings_ovrp
from .model import Context, Route
from .objective import _obj_total, estimated_served, solution_key


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
    and the best one is used -- the CW-1 procedure of the paper (Table 1).
    "Best" means the solution that carries the most passengers, with the fuel
    cost as the tie-break.

    The pipeline is: the construction (CW-1 and CW-2), the anchoring that
    gives each route the origin and the destination the scenario allows, the
    cut by the available fleet, and the local search (CW-3). The local search
    comes last on purpose: it optimizes the routes that are actually operated,
    so what it improves is what the report shows.

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
            f"sentido: {ctx.sense} | origens: {ctx.origins or (ctx.depot,)} | "
            f"destinos: {ctx.destinations or 'livre'} | "
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
    best_key: tuple[int, float] | None = None
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
        lambda_served = estimated_served(lambda_routes, ctx)
        if verbose:
            longest_time = max((r.time_minutes for r in lambda_routes), default=0)
            print(
                f"  lam={lambda_value:.1f} -> {len(lambda_routes)} veiculos | "
                f"R${lambda_cost:.2f} | "
                f"{sum(r.distance_km for r in lambda_routes):.1f} km | "
                f"~{lambda_served} pax | "
                f"maior rota {longest_time} min"
            )

        key = solution_key(lambda_served, lambda_cost)
        if best_key is None or key < best_key:
            best_key = key
            best_routes = lambda_routes
            best_lambda = lambda_value

    if verbose:
        print(
            f"\n  [OK] Melhor lam = {best_lambda} | "
            f"custo R${_obj_total(best_routes or []):.2f}"
        )

    # ── Endpoints and fleet: the routes that will actually operate ─────────
    routes = anchor_routes(best_routes or [], ctx)
    routes = limit_fleet(routes, ctx)

    # ── CW-3: post-improvement over the routes that will operate ───────────
    if use_post_improvement and routes:
        if verbose:
            print("  Aplicando post-improvement (2-opt / shift / swap)...")
        before = _obj_total(routes)
        routes = post_improvement(
            routes,
            ctx,
            max_iterations_without_improvement=post_improvement_iterations,
        )
        improved_cost = _obj_total(routes)
        if verbose:
            reduction = (
                round((before - improved_cost) / before * 100, 2)
                if before > 0
                else 0.0
            )
            print(
                f"  [OK] Apos post-improvement: R${improved_cost:.2f} "
                f"(-{reduction}%)"
            )

    return routes, best_lambda
