"""Rendering one scenario outcome, shared by main.py and scripts/run_all.py.

Both the interactive CLI and the sweep report show the same facts about a
run: how many buses were used, which pairs were served, which buses stayed
idle and which routes came out. The formatting helpers live here so the two
front ends only decide their own layout (aligned plain text vs markdown).

This module sits above the packages on purpose: it reads `algorithms` model
objects, so it is a view of a run, not a reusable utility.
"""

from collections import Counter

from algorithms.top_univasf import (
    BusPlan,
    FleetSummary,
    InstanceData,
    ServedPair,
)
from entities.bus import Bus

#: Pairs shown in the "top served" and "unserved" previews.
PAIR_PREVIEW = 8
#: Cap on the pair count shown for the served preview.
TOP_PAIRS = 5

#: Header of the per-bus table, in the same order as `plan_cells`.
PLAN_HEADERS = ("bus", "paradas", "pax", "tempo", "pico", "pax/min", "origem", "destino")


def served_ratio(data: InstanceData, plans: list[BusPlan]) -> tuple[int, int, float]:
    """(passageiros atendidos, total, percentual) de um cenário."""
    total = int(data.demand.sum())
    served = sum(plan.served_passengers for plan in plans)
    percentage = 100.0 * served / total if total else 0.0
    return served, total, percentage


def top_served_pairs(
    plans: list[BusPlan], limit: int = TOP_PAIRS
) -> list[ServedPair]:
    """Os `limit` pares OD mais atendidos, somando ônibus, por quantidade."""
    aggregated: Counter[tuple[int, int]] = Counter()
    for plan in plans:
        for origin, destination, quantity in plan.served_pairs:
            aggregated[(origin, destination)] += quantity
    return [
        (origin, destination, quantity)
        for (origin, destination), quantity in aggregated.most_common(limit)
    ]


def idle_bus_ids(buses: list[Bus], plans: list[BusPlan]) -> list[int]:
    """Ônibus que não formaram rota (nenhum commit em nenhuma rodada)."""
    used = {plan.bus_id for plan in plans}
    return [bus.id for bus in buses if bus.id not in used]


def pairs_preview(
    pairs: list[ServedPair], limit: int = PAIR_PREVIEW, overflow_suffix: bool = False
) -> str:
    """Prévia "o→d=q, o→d=q" dos primeiros `limit` pares.

    `overflow_suffix` acrescenta " (+k pares)" quando a lista é maior que
    `limit` — útil onde a prévia é a única informação exibida.
    """
    preview = ", ".join(f"{o}→{d}={q}" for o, d, q in pairs[:limit])
    hidden = len(pairs) - limit
    if overflow_suffix and hidden > 0:
        preview += f" (+{hidden} pares)"
    return preview


def pair_label(plan: BusPlan) -> str:
    """Par travado do plano, ex.: "44 → 45"."""
    return f"{plan.origin} → {plan.destination}"


def route_line(plan: BusPlan) -> str:
    """Rota de um plano, ex.: "bus 3 (44 → 45): 44 -> 20 -> 45"."""
    return (
        f"bus {plan.bus_id} ({pair_label(plan)}): "
        + " -> ".join(str(node) for node in plan.stops)
    )


def plan_cells(
    plan: BusPlan, time_limit_minutes: int, capacity: int | None = None
) -> tuple[str, ...]:
    """Células de um plano, na ordem de `PLAN_HEADERS`.

    `capacity` preenche o pico como "usado/total"; sem ele, só o usado.
    """
    peak = str(plan.peak_load) if capacity is None else f"{plan.peak_load}/{capacity}"
    return (
        str(plan.bus_id),
        str(len(plan.stops)),
        str(plan.served_passengers),
        f"{plan.travel_time_minutes}/{time_limit_minutes}",
        peak,
        f"{plan.score:.2f}",
        str(plan.stops[0]),
        str(plan.destination),
    )


def fleet_totals_line(plans: list[BusPlan], buses: list[Bus], data: InstanceData) -> str:
    """Resumo de uma linha: ônibus usados e passageiros atendidos."""
    served, total, percentage = served_ratio(data, plans)
    return (
        f"{len(plans)} de {len(buses)} ônibus · {served}/{total} pax "
        f"({percentage:.0f}%)"
    )


def unserved_line(summary: FleetSummary) -> str:
    """Prévia da demanda que sobrou, ou "" quando não sobrou nada."""
    if not summary.unserved_pairs:
        return ""
    preview = pairs_preview(summary.unserved_pairs, overflow_suffix=True)
    return f"Não atendidos ({summary.unserved_passengers} pax): {preview}"


def served_pairs_line(plans: list[BusPlan]) -> str:
    """Prévia dos pares mais atendidos, ou "" quando nada foi atendido."""
    pairs = top_served_pairs(plans)
    if not pairs:
        return ""
    return "Pares mais atendidos: " + pairs_preview(pairs, limit=len(pairs))
