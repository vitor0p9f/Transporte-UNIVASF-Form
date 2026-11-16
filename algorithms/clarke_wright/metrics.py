"""Route measures and the OVRP savings formula (CW-1)."""

from utils.paths import path_distance, path_time_minutes

from .constants import INF
from .model import Context, Route, Saving


def _route_distance(stops: list[int], ctx: Context) -> float:
    """Distance of the open route: depot -> p1 -> p2 -> ... -> pn.

    The return leg to the depot is not counted (OVRP).
    """
    if not stops:
        return 0.0
    return round(path_distance(ctx.distance, stops, start=ctx.depot), 4)


def _route_time(stops: list[int], ctx: Context) -> int:
    """Total time of the open route, in minutes (the scenario `time` matrix)."""
    if not stops:
        return 0
    return path_time_minutes(ctx.time, stops, start=ctx.depot)


def _update_cost(route: Route, ctx: Context) -> Route:
    """Recompute the route's distance_km, time_minutes and cost_brl."""
    route.distance_km = _route_distance(route.stops, ctx)
    route.time_minutes = _route_time(route.stops, ctx)
    route.cost_brl = ctx.bus_model.route_cost(route.distance_km)
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
    """Modified OVRP formula (equation 5 of the paper).

    s(i,j) = c(depot, j) - lambda * c(i, j)

    Compared to the CVRP it drops the c(i, depot) term, because the vehicle does
    not return to the depot after visiting i.

    Args:
        stops: list of stops (the depot is not one of them)
        ctx: distance matrix + depot
        lam: shape parameter, lambda in [0.1, 2.0]
    """
    savings = []
    for idx_i in range(len(stops)):
        for idx_j in range(idx_i + 1, len(stops)):
            stop_i, stop_j = stops[idx_i], stops[idx_j]

            # Equation 5 of the paper (OVRP with lambda)
            s = float(ctx.distance[ctx.depot, stop_j]) - lam * float(
                ctx.distance[stop_i, stop_j]
            )
            savings.append(Saving(i=stop_i, j=stop_j, value=round(s, 6)))

    savings.sort()  # descending, via __lt__
    return savings


def _time_limit_text(limit: float) -> str:
    return "sem limite" if limit == INF else f"{limit:g} min"  # report text: pt-BR
