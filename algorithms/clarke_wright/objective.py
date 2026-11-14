"""Função objetivo: custo de combustível da solução."""

from .model import Rota


def _obj_total(rotas: list[Rota]) -> float:
    """Custo de combustível (R$) de um conjunto de rotas."""
    return sum(r.custo_brl for r in rotas)
