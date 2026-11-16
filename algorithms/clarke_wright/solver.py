"""Service-first selection of distance-based Clarke-Wright constructions."""

import random
from dataclasses import replace
from .constants import ITER_POSTIMPROVE, ITER_TWO_PHASE, LAMBDA_MIN, LAMBDA_MAX, LAMBDA_PASSO
from .construction import _merge, two_phase_selection
from .context import build_active_nodes, route_load
from .anchoring import anchor_routes
from .evaluation import limit_fleet
from .improvement import post_improvement
from .metrics import compute_savings_ovrp
from .model import Context, Route
from .objective import exact_key


def clarke_wright_ovrp(
    ctx: Context, lam: float | None = None, use_two_phase: bool = True,
    use_post_improvement: bool = True, iterations: int = ITER_TWO_PHASE,
    post_improvement_iterations: int = ITER_POSTIMPROVE,
    seed: int | None = 42, verbose: bool = True,
) -> tuple[list[Route], float]:
    """Construct -> anchor -> fleet cut -> CW-3; evaluation follows in scenario.

    The two-phase loop uses an optimistic service_bound (not exact boarding).
    Lambda candidates are selected by exact shared boarding, then full cost.
    No service-first rule is substituted for the savings merge construction.
    """
    if seed is not None:
        random.seed(seed)
    active = build_active_nodes(ctx.demand)
    if not active:
        return [], 0.0
    raw_ctx = replace(ctx, origins=None, destinations=None)
    lambdas = [lam] if lam is not None else [
        round(LAMBDA_MIN + i * LAMBDA_PASSO, 1)
        for i in range(round((LAMBDA_MAX - LAMBDA_MIN) / LAMBDA_PASSO) + 1)
    ]
    best_routes, best_lambda, best_key = [], lambdas[0], None
    prepared = {}
    def prepare(routes):
        key = tuple(tuple(r.stops) for r in routes)
        if key not in prepared:
            result = anchor_routes(routes, ctx)
            result = [r for r in result if ctx.fits(r.load, r.time_minutes)]
            prepared[key] = limit_fleet(result, ctx)
        return prepared[key]
    for value in lambdas:
        savings = compute_savings_ovrp(sorted(active), raw_ctx, value)
        if ctx.restrictions.capacity:
            # Touch-load is monotone, making this a safe prefilter.
            savings = [s for s in savings if route_load((s.i, s.j), raw_ctx) <= ctx.capacity]
        if use_two_phase and savings:
            routes = two_phase_selection(
                savings, active, raw_ctx, iterations, selection_ctx=ctx,
                finalize=lambda routes: exact_key(prepare(routes), ctx),
            )
        else:
            routes = _merge(savings, active, raw_ctx)
        routes = prepare(routes)
        key = exact_key(routes, ctx)
        if verbose:
            print(f'  lam={value:.1f}: served={-key[0]} cost=R${key[1]:.2f}', flush=True)
        if best_key is None or key < best_key:
            best_routes, best_lambda, best_key = routes, value, key
    if use_post_improvement and best_routes:
        best_routes = post_improvement(best_routes, ctx, post_improvement_iterations)
    return best_routes, best_lambda
