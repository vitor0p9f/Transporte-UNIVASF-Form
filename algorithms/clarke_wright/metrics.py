"""Route measures and the OVRP savings formula (CW-1)."""

from utils.paths import path_distance, path_time_minutes

from .constants import INF
from .model import Context, Route, Saving


def _route_endpoints(
    stops: list[int], ctx: Context
) -> tuple[int, int | None, float, int]:
    """Choose permitted endpoints for this order, including both access legs.

    A feasible endpoint pair always wins over a shorter, over-time pair.
    If none is feasible we return the shortest one so ``Context.fits`` can
    reject the candidate. Ties use node labels, not the input list order.
    """
    if not stops:
        return ctx.depot, None, 0.0, 0
    cache = ctx._cache.setdefault('geometry', {})
    cache_key = tuple(stops)
    if cache_key in cache:
        return cache[cache_key]
    inner_distance = path_distance(ctx.distance, stops)
    inner_time = path_time_minutes(ctx.time, stops)
    best = None
    for origin in ctx.origins or (ctx.depot,):
        distance = inner_distance + float(ctx.distance[origin, stops[0]])
        minutes = inner_time + int(ctx.time[origin, stops[0]])
        for destination in ctx.destinations or (None,):
            total_distance = distance
            total_time = minutes
            if destination is not None:
                total_distance += float(ctx.distance[stops[-1], destination])
                total_time += int(ctx.time[stops[-1], destination])
            key = (
                ctx.restrictions.time and total_time > ctx.max_time,
                total_distance, total_time, origin,
                stops[-1] if destination is None else destination,
            )
            if best is None or key < best[0]:
                best = (key, origin, destination, total_distance, total_time)
    if len(cache) >= 65536:
        cache.clear()
    cache[cache_key] = best[1:]
    return best[1:]


def anchored_path(stops, origin, destination):
    path = tuple(stops)
    if not path or path[0] != origin:
        path = (origin, *path)
    if destination is not None and path[-1] != destination:
        path += (destination,)
    return path


def route_path(route: Route, ctx: Context) -> tuple[int, ...]:
    if route.anchored:
        return anchored_path(route.stops, route.origin, route.destination)
    return _route_path(route.stops, ctx)


def _route_path(stops: list[int], ctx: Context) -> tuple[int, ...]:
    """Full driven sequence shared by measurements, simulation and reports."""
    origin, destination, _, _ = _route_endpoints(stops, ctx)
    path = list(stops)
    if not path or path[0] != origin:
        path.insert(0, origin)
    if destination is not None and path[-1] != destination:
        path.append(destination)
    return tuple(path)


def _route_distance(stops: list[int], ctx: Context) -> float:
    """Distance including the selected origin and permitted terminal node."""
    return round(_route_endpoints(stops, ctx)[2], 4)


def _route_time(stops: list[int], ctx: Context) -> int:
    """Time including the selected origin and permitted terminal node."""
    return _route_endpoints(stops, ctx)[3]


def _update_cost(route: Route, ctx: Context) -> Route:
    """Recompute the route's distance_km, time_minutes and cost_brl."""
    if route.anchored:
        path = route_path(route, ctx)
        route.distance_km = round(path_distance(ctx.distance, path), 4)
        route.time_minutes = path_time_minutes(ctx.time, path)
        route.cost_brl = ctx.bus_model.route_cost(route.distance_km, route.time_minutes)
        return route
    origin, destination, distance, minutes = _route_endpoints(route.stops, ctx)
    route.origin = origin
    route.destination = destination if destination is not None else (
        route.stops[-1] if route.stops else origin
    )
    route.distance_km = round(distance, 4)
    route.time_minutes = minutes
    route.cost_brl = ctx.bus_model.route_cost(route.distance_km, route.time_minutes)
    return route


def _update_route(
    route: Route, stops: list[int], load: int, ctx: Context
) -> Route:
    """Replace the stops/load and recompute the route measures."""
    route.stops = stops
    route.load = load
    return _update_cost(route, ctx)


def compute_savings_ovrp(
    stops: list[int],
    ctx: Context,
    lam: float,
) -> list[Saving]:
    """Modified OVRP savings, extended to account for permitted endpoints.

    s(i,j) = c(depot, j) - lambda * c(i, j)

    Compared to the CVRP it drops the c(i, depot) term, because the vehicle does
    not return to the depot after visiting i.

    With endpoint filters, use complete singleton costs minus the merged cost
    and the lambda adjustment on the joining arc. The formula above is
    recovered for a single depot with no destination filter.

    Args:
        stops: list of stops (the depot is not one of them)
        ctx: distance matrix + depot
        lam: shape parameter, lambda in [0.1, 2.0]
    """
    savings = []
    for idx_i in range(len(stops)):
        for idx_j in range(idx_i + 1, len(stops)):
            stop_i, stop_j = stops[idx_i], stops[idx_j]

            if ctx.origins is None and ctx.destinations is None:
                # Legacy single-depot/open-end equation (paper equation 5).
                s = float(ctx.distance[ctx.depot, stop_j]) - lam * float(
                    ctx.distance[stop_i, stop_j]
                )
            else:
                # Savings from joining complete routes, with their permitted
                # endpoints. For one depot and an unrestricted end this reduces
                # to c(depot,j) - lambda*c(i,j).
                s = (
                    _route_distance([stop_i], ctx)
                    + _route_distance([stop_j], ctx)
                    - _route_distance([stop_i, stop_j], ctx)
                    - (lam - 1.0) * float(ctx.distance[stop_i, stop_j])
                )
            savings.append(Saving(i=stop_i, j=stop_j, value=round(s, 6)))

    savings.sort()  # descending, via __lt__
    return savings


def _time_limit_text(limit: float) -> str:
    return "sem limite" if limit == INF else f"{limit:g} min"  # report text: pt-BR
