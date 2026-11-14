"""Medidas de rota e fórmula de savings OVRP (CW-1)."""

from utils.paths import path_distance, path_time_minutes

from .constants import INF
from .model import Context, Route, Saving


def _route_distance(stops: list[int], ctx: Context) -> float:
    """Distância da rota aberta: depot → p1 → p2 → ... → pn.

    Não inclui retorno ao depósito (OVRP).
    """
    if not stops:
        return 0.0
    return round(path_distance(ctx.distance, stops, start=ctx.depot), 4)


def _route_time(stops: list[int], ctx: Context) -> int:
    """Tempo total da rota aberta, em minutos (matriz `time` do cenário)."""
    if not stops:
        return 0
    return path_time_minutes(ctx.time, stops, start=ctx.depot)


def _update_cost(route: Route, ctx: Context) -> Route:
    """Recalcula dist_km, tempo_min e custo_brl da rota."""
    route.distance_km = _route_distance(route.stops, ctx)
    route.time_minutes = _route_time(route.stops, ctx)
    route.cost_brl = ctx.bus_model.route_cost(route.distance_km)
    return route


def _update_route(
    route: Route, stops: list[int], load: int, ctx: Context
) -> Route:
    """Troca as paradas/carga e recalcula as medidas da rota."""
    route.stops = stops
    route.load = load
    return _update_cost(route, ctx)


def compute_savings_ovrp(
    stops: list[int],
    ctx: Context,
    lam: float,
) -> list[Saving]:
    """Fórmula OVRP modificada (equação 5 do artigo).

    s(i,j) = c(depot, j) - λ · c(i, j)

    Diferença em relação ao CVRP: remove o termo c(i, depot) porque o veículo
    não retorna ao depósito após visitar i.

    Args:
        paradas: lista de paradas (sem o depósito)
        ctx: matriz de distâncias + depósito
        lam: parâmetro de forma λ ∈ [0.1, 2.0]
    """
    savings = []
    for idx_i in range(len(stops)):
        for idx_j in range(idx_i + 1, len(stops)):
            stop_i, stop_j = stops[idx_i], stops[idx_j]

            # Equação 5 do artigo (OVRP com λ)
            s = float(ctx.distance[ctx.depot, stop_j]) - lam * float(
                ctx.distance[stop_i, stop_j]
            )
            savings.append(Saving(i=stop_i, j=stop_j, value=round(s, 6)))

    savings.sort()  # decrescente via __lt__
    return savings


def _time_limit_text(limit: float) -> str:
    return "sem limite" if limit == INF else f"{limit:g} min"
