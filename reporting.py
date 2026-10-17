"""Rendering one scenario outcome, shared by main.py and scripts/run_all.py.

Both the interactive CLI and the sweep report show the same facts about a run:
how many buses were used, which pairs were served, which buses stayed idle and
which routes came out. The formatting helpers live here so the two front ends
only decide their own layout (aligned plain text vs markdown).

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

#: Pairs shown in the "most served" and "unserved" previews.
PAIR_PREVIEW = 8
#: Cap on the pair count shown for the served preview.
TOP_PAIRS = 5

#: Header of the per-bus table, in the same order as `plan_cells`.
PLAN_HEADERS = (
    "bus",
    "stops",
    "pax",
    "time",
    "peak",
    "pax/min",
    "origin",
    "destination",
)


def served_ratio(data: InstanceData, plans: list[BusPlan]) -> tuple[int, int, float]:
    """(passengers served, total demand, percentage) of one scenario."""
    total = int(data.demand.sum())
    served = sum(plan.served_passengers for plan in plans)
    percentage = 100.0 * served / total if total else 0.0
    return served, total, percentage


def top_served_pairs(
    plans: list[BusPlan], limit: int = TOP_PAIRS
) -> list[ServedPair]:
    """The `limit` most served OD pairs, summing buses, highest quantity first."""
    aggregated: Counter[tuple[int, int]] = Counter()
    for plan in plans:
        for origin, destination, quantity in plan.served_pairs:
            aggregated[(origin, destination)] += quantity
    return [
        (origin, destination, quantity)
        for (origin, destination), quantity in aggregated.most_common(limit)
    ]


def idle_bus_ids(buses: list[Bus], plans: list[BusPlan]) -> list[int]:
    """Buses that never formed a route (no commit in any round)."""
    used = {plan.bus_id for plan in plans}
    return [bus.id for bus in buses if bus.id not in used]


def pairs_preview(
    pairs: list[ServedPair], limit: int = PAIR_PREVIEW, overflow_suffix: bool = False
) -> str:
    """Preview "o→d=q, o→d=q" of the first `limit` pairs.

    `overflow_suffix` appends " (+k pairs)" when the list is longer than
    `limit` -- useful where the preview is all the reader gets to see.
    """
    preview = ", ".join(f"{o}→{d}={q}" for o, d, q in pairs[:limit])
    hidden = len(pairs) - limit
    if overflow_suffix and hidden > 0:
        preview += f" (+{hidden} pairs)"
    return preview


def pair_label(plan: BusPlan) -> str:
    """The plan's locked pair, e.g. "44 → 45"."""
    return f"{plan.origin} → {plan.destination}"


def route_line(plan: BusPlan) -> str:
    """One plan's route, e.g. "bus 3 (44 → 45): 44 -> 20 -> 45"."""
    return (
        f"bus {plan.bus_id} ({pair_label(plan)}): "
        + " -> ".join(str(node) for node in plan.stops)
    )


def plan_cells(
    plan: BusPlan, time_limit_minutes: int, capacity: int | None = None
) -> tuple[str, ...]:
    """One plan's cells, in `PLAN_HEADERS` order.

    `capacity` fills the peak as "used/total"; without it, only the used value.
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


def fleet_totals_line(
    plans: list[BusPlan], buses: list[Bus], data: InstanceData
) -> str:
    """One-line summary: buses used and passengers served."""
    served, total, percentage = served_ratio(data, plans)
    return (
        f"{len(plans)} of {len(buses)} buses · {served}/{total} pax "
        f"({percentage:.0f}%)"
    )


def unserved_line(summary: FleetSummary) -> str:
    """Preview of the demand left over, or "" when nothing was left."""
    if not summary.unserved_pairs:
        return ""
    preview = pairs_preview(summary.unserved_pairs, overflow_suffix=True)
    return f"Unserved ({summary.unserved_passengers} pax): {preview}"


def served_pairs_line(plans: list[BusPlan]) -> str:
    """Preview of the most served pairs, or "" when nothing was served."""
    pairs = top_served_pairs(plans)
    if not pairs:
        return ""
    return "Most served pairs: " + pairs_preview(pairs, limit=len(pairs))
