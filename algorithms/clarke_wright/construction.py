"""Construção OVRP: fusão de rotas, direction choice e two-phase selection."""

import random

from .constants import ITER_TWO_PHASE
from .metrics import _route_distance, _route_time, _update_cost
from .model import Context, Route, Saving
from .objective import _obj_total


def _best_direction(stops: list[int], ctx: Context) -> list[int]:
    """Procedimento CW-2: testa as duas direções da rota aberta.

    Em OVRP:
      forward : depot → p1 → p2 → ... → pn   (distância D_f)
      reverse : depot → pn → p(n-1) → ... → p1 (distância D_r)

    Com a restrição de tempo ativa a direção não é indiferente (o primeiro
    trecho sai do depósito), então direções que já estouram o limite são
    descartadas antes de escolher a mais curta. Se nenhuma couber, devolve a
    mais curta e quem chamou rejeita a rota em `Contexto.cabe`.
    """
    directions = [list(stops), list(reversed(stops))]
    if ctx.restrictions.time:
        feasible = [d for d in directions if _route_time(d, ctx) <= ctx.max_time]
        if feasible:
            directions = feasible
    return min(directions, key=lambda d: _route_distance(d, ctx))


def _merge(
    savings: list[Saving],
    active_stops: set[int],
    ctx: Context,
) -> list[Route]:
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
    routes: list[Route] = []
    endpoint: dict[int, Route] = {}  # extremo → rota que o contém

    for p in sorted(active_stops):  # ordem fixa → resultado reprodutível
        r = Route(stops=[p], load=ctx.stop_loads.get(p, 0))
        _update_cost(r, ctx)
        routes.append(r)
        endpoint[p] = r

    for s in savings:
        ri = endpoint.get(s.i)
        rj = endpoint.get(s.j)

        if ri is None or rj is None or ri is rj:
            continue

        load = ri.load + rj.load
        if ctx.restrictions.capacity and load > ctx.capacity:
            continue

        new_order = None

        if ri.last() == s.i and rj.first() == s.j:
            new_order = ri.stops + rj.stops
        elif rj.last() == s.j and ri.first() == s.i:
            new_order = rj.stops + ri.stops
        elif ri.last() == s.i and rj.last() == s.j:
            new_order = ri.stops + list(reversed(rj.stops))
        elif ri.first() == s.i and rj.first() == s.j:
            new_order = list(reversed(ri.stops)) + rj.stops

        if new_order is None:
            continue

        # Aplica CW-2: escolhe a melhor direção da rota aberta
        new_order = _best_direction(new_order, ctx)
        if not ctx.fits(load, _route_time(new_order, ctx)):
            continue

        new_route = Route(stops=new_order, load=load)
        _update_cost(new_route, ctx)

        # Remove as rotas fundidas (por identidade: `Rota` compara por valor)
        routes = [r for r in routes if r is not ri and r is not rj]
        for p in ri.stops + rj.stops:
            endpoint.pop(p, None)

        # Registra nova rota
        routes.append(new_route)
        endpoint[new_route.first()] = new_route
        endpoint[new_route.last()] = new_route

    return routes


def _roulette_wheel(savings: list[Saving], size: int) -> list[Saving]:
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

    ordered = []
    remaining = list(savings)

    while remaining:
        window = min(size, len(remaining))
        candidates = remaining[:window]

        lowest = min(s.value for s in candidates)
        weights = [s.value - lowest + 1e-9 for s in candidates]
        total = sum(weights)

        r = random.random() * total
        cumulative = 0.0
        idx = window - 1
        for k, w in enumerate(weights):
            cumulative += w
            if r <= cumulative:
                idx = k
                break

        ordered.append(remaining.pop(idx))

    return ordered


def two_phase_selection(
    savings: list[Saving],
    active_stops: set[int],
    ctx: Context,
    iterations: int = ITER_TWO_PHASE,
) -> list[Route]:
    """Procedimento CW-2: reordena savings via roleta e guarda a melhor."""
    best_routes = _merge(savings, active_stops, ctx)
    best_cost = _obj_total(best_routes)

    current_savings = list(savings)

    for _ in range(iterations):
        # Tamanho do torneio T ∈ [3, 6] conforme o artigo (seção 2.3).
        tournament_size = random.randint(
            3, min(6, max(3, len(current_savings)))
        )
        new_order = _roulette_wheel(current_savings, tournament_size)
        new_routes = _merge(new_order, active_stops, ctx)
        new_cost = _obj_total(new_routes)

        if new_cost < best_cost:
            best_cost = new_cost
            best_routes = new_routes
            current_savings = new_order

    return best_routes
