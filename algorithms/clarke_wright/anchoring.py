"""Choose permitted endpoints AFTER savings construction, before CW-3."""

from dataclasses import replace
from algorithms.top_univasf.simulation import simulate_stops
from utils.instances import InstanceData
from .context import route_load
from .metrics import _update_cost, route_path
from .model import Context, Route
from .objective import solution_key


def _score(route: Route, ctx: Context, remaining=None):
    """Exact service first, operational cost only as a tie-breaker."""
    data = InstanceData([], ctx.distance, ctx.time, ctx.demand)
    result = simulate_stops(data, route_path(route, ctx), ctx.capacity,
                            ctx.demand if remaining is None else remaining)
    return solution_key(result.passengers, route.cost_brl), result


def anchor_candidates(route: Route, ctx: Context) -> list[Route]:
    key = tuple(route.stops)
    cache = ctx._cache.setdefault('anchor_candidates', {})
    if key in cache:
        return cache[key]
    candidates = []
    seen = set()
    for order in (key, key[::-1]):
        for origin in ctx.origins or (ctx.depot,):
            for destination in ctx.destinations or (order[-1] if order else origin,):
                # Anchors are endpoints, not static-load customer stops.
                body = [n for n in order if n != origin and n != destination]
                trial = Route(stops=body, load=route_load(body, ctx),
                              origin=origin, destination=destination, anchored=True)
                path = route_path(trial, ctx)
                if path in seen:
                    continue
                seen.add(path)
                _update_cost(trial, ctx)
                if ctx.fits(trial.load, trial.time_minutes):
                    candidates.append(trial)
    cache[key] = candidates
    return candidates


def anchor_routes(routes: list[Route], ctx: Context) -> list[Route]:
    if not (ctx.origins or ctx.destinations):
        return routes
    remaining = ctx.demand.copy()
    pending = [(index, anchor_candidates(route, ctx)) for index, route in enumerate(routes)]
    selected = []
    while pending:
        options = []
        for index, candidates in pending:
            for candidate in candidates:
                key, outcome = _score(candidate, ctx, remaining)
                if outcome.passengers > 0:
                    options.append(((*key, route_path(candidate, ctx), index), index, candidate, outcome))
        if not options:
            break
        _, index, best, outcome = min(options, key=lambda option: option[0])
        selected.append(replace(best, stops=list(best.stops)))
        for o, d, quantity in outcome.pairs:
            remaining[o, d] -= quantity
        pending = [(i, c) for i, c in pending if i != index]
    return selected
