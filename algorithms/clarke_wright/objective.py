"""Função objetivo: custo de combustível da solução."""

from .model import Route


def _obj_total(routes: list[Route]) -> float:
    """Custo de combustível (R$) de um conjunto de rotas."""
    return sum(r.cost_brl for r in routes)
