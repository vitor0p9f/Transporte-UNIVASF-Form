"""Objective function: the solution fuel cost."""

from .model import Route


def _obj_total(routes: list[Route]) -> float:
    """Fuel cost (BRL) of a set of routes."""
    return sum(r.cost_brl for r in routes)
