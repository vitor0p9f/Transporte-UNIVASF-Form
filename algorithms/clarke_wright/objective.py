"""Função objetivo: combustível + penalidade de superlotação."""

from .model import Rota


def _excesso(carga: int, conforto: int) -> int:
    """Passageiros acima da capacidade de conforto (0 se dentro do conforto)."""
    return max(0, carga - conforto)


def _obj_carga(
    custo_brl: float, carga: int, peso_superlotacao: float, conforto: int
) -> float:
    """Custo de uma rota com a penalidade de conforto aplicada à carga."""
    return custo_brl + peso_superlotacao * _excesso(carga, conforto)


def _obj_rota(rota: Rota, peso_superlotacao: float, conforto: int) -> float:
    """Custo de uma rota para fins de otimização.

    custo_combustível + peso · (passageiros em desconforto)

    Com peso_superlotacao = 0 recai no custo puro (comportamento original).
    Com peso > 0 o algoritmo passa a EVITAR ônibus lotados além do conforto,
    redistribuindo passageiros mesmo que custe um pouco mais de combustível.
    """
    return _obj_carga(rota.custo_brl, rota.carga, peso_superlotacao, conforto)


def _obj_total(rotas: list[Rota], peso_superlotacao: float, conforto: int) -> float:
    return sum(_obj_rota(r, peso_superlotacao, conforto) for r in rotas)


def _custo_total(rotas: list[Rota]) -> float:
    return sum(r.custo_brl for r in rotas)
