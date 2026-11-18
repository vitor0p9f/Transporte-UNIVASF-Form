"""Rendering one scenario outcome, shared by every report runner.

All the report front ends show the same facts about a run: how many buses were
used, which pairs were served, which buses stayed idle and which routes came
out. The formatting helpers live here so the front ends only decide their own
layout (aligned plain text vs markdown) and their own columns.

This module sits above the packages on purpose: it reads `algorithms` model
objects, so it is a view of a run, not a reusable utility.
"""

from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field

from algorithms.top_univasf import (
    BusPlan,
    CostModel,
    FleetSummary,
    InstanceData,
    ServedPair,
    route_distance_km,
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
    "pax/R$",
    "origin",
    "destination",
)


@dataclass
class ScenarioRun:
    """One heuristic's outcome for one scenario, including a failure.

    The runners build one of these per (scenario, heuristic): the summary
    tables read the numbers through `run_metrics`, the detail blocks read the
    plans, and `error` carries a failed run so a batch report can keep going.
    """

    scenario: dict
    buses: list[Bus]
    elapsed: float
    data: InstanceData | None = None
    plans: list[BusPlan] = field(default_factory=list)
    summary: FleetSummary | None = None
    error: str = ""
    heuristic: str = ""

    @property
    def scenario_id(self) -> str:
        return str(self.scenario["scenario_id"])

    @property
    def instance_id(self) -> str:
        return str(self.scenario["instance_id"])

    @property
    def period(self) -> str:
        return str(self.scenario["period"])

    @property
    def fleet(self) -> str:
        return str(self.scenario["fleet_bus_ids"])

    @property
    def limit(self) -> str:
        return str(self.scenario["max_time_limit"])


@dataclass(frozen=True)
class RunMetrics:
    """Numbers shared by the summary tables of the report runners."""

    served: int
    total: int
    percentage: float
    used: int
    limit: int
    longest: int
    peak: int
    reference: BusPlan | None


def served_ratio(data: InstanceData, plans: list[BusPlan]) -> tuple[int, int, float]:
    """(passengers served, total demand, percentage) of one scenario."""
    total = int(data.demand.sum())
    served = sum(plan.served_passengers for plan in plans)
    percentage = 100.0 * served / total if total else 0.0
    return served, total, percentage


def reference_plan(plans: list[BusPlan]) -> BusPlan | None:
    """The route every route-level column of a report row is read from.

    It is the longest route that served someone, the same set of routes the
    reports count as "ônibus usados" and charge in the cost. Empty routes are
    skipped on purpose: a CW route that boards nobody can still be the longest
    one driven, and it would otherwise become the reference for the time, the
    peak and the capacity of a row that does not count it anywhere else. When
    no route served anyone, falls back to the longest route overall so the
    time column still reports something; ``None`` only for an empty fleet.
    """
    served = [plan for plan in plans if plan.served_passengers > 0]
    candidates = served or plans
    return max(candidates, key=lambda plan: plan.travel_time_minutes, default=None)


def plan_distance_km(plan: BusPlan, data: InstanceData) -> float:
    """Distance driven by one plan, in km (open route, no return leg).

    `plan.stops` already starts at the depot, so the first leg is counted;
    repeated nodes (dobradinha) count every time they are driven.
    """
    return route_distance_km(data.distance, plan.stops)


@dataclass(frozen=True)
class OperationalCost:
    """Fuel + driver cost of one heuristic's routes in one scenario.

    The same vehicle model (km per liter and diesel price) and the same driver
    rate are applied to both heuristics, and both heuristics optimise this same
    fuel + driver total internally, so the numbers are comparable; the driver
    rate comes from the scenario. Only routes that carry at least one passenger
    are charged -- the same set the reports count as "ônibus usados".
    """

    distance_km: float
    liters: float
    fuel: float
    driver: float
    diesel_price: float
    driver_hourly_rate: float

    @property
    def total(self) -> float:
        return self.fuel + self.driver

    def per_passenger(self, served: int) -> float:
        """Cost per passenger carried; the metric that does not reward idling."""
        return self.total / served if served else 0.0


def operational_cost(
    plans: list[BusPlan],
    data: InstanceData,
    *,
    km_per_liter: float,
    diesel_price: float,
    driver_hourly_rate: float,
) -> OperationalCost:
    """Fuel + driver cost of a set of plans under one vehicle model.

    Routes that serve nobody are not charged: the Clarke-Wright can return a
    route whose boarding simulation carries zero passengers, and an operator
    would not put a bus on the road for it. Charging only the routes that
    served someone keeps the cost and the "ônibus usados" column talking about
    the same set of routes.
    """
    driven = [plan for plan in plans if plan.served_passengers > 0]
    breakdown = CostModel(
        diesel_price_per_liter=diesel_price,
        driver_hourly_rate=driver_hourly_rate,
    ).route_breakdown(
        sum(plan_distance_km(plan, data) for plan in driven),
        sum(plan.travel_time_minutes for plan in driven),
        km_per_liter,
    )
    return OperationalCost(
        distance_km=breakdown.distance_km,
        liters=breakdown.liters,
        fuel=breakdown.fuel,
        driver=breakdown.driver,
        diesel_price=diesel_price,
        driver_hourly_rate=driver_hourly_rate,
    )


def operational_cost_per_bus(
    plans: list[BusPlan],
    data: InstanceData,
    buses: list[Bus],
    *,
    diesel_price: float,
    driver_hourly_rate: float,
) -> OperationalCost:
    """Fuel + driver cost charging each route its own bus's km per liter.

    The heterogeneous-fleet counterpart of `operational_cost`, which applies a
    single reference model: here every plan burns its own vehicle's fuel. The
    rest of the convention is the same -- only routes that serve someone are
    charged.
    """
    by_id = {bus.id: bus for bus in buses}
    model = CostModel(
        diesel_price_per_liter=diesel_price,
        driver_hourly_rate=driver_hourly_rate,
    )
    breakdowns = [
        model.route_breakdown(
            plan_distance_km(plan, data),
            plan.travel_time_minutes,
            by_id[plan.bus_id].km_autonomy_per_liter,
        )
        for plan in plans
        if plan.served_passengers > 0
    ]
    return OperationalCost(
        distance_km=sum(breakdown.distance_km for breakdown in breakdowns),
        liters=sum(breakdown.liters for breakdown in breakdowns),
        fuel=sum(breakdown.fuel for breakdown in breakdowns),
        driver=sum(breakdown.driver for breakdown in breakdowns),
        diesel_price=diesel_price,
        driver_hourly_rate=driver_hourly_rate,
    )


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
    pairs: list[ServedPair] | tuple[ServedPair, ...], limit: int = PAIR_PREVIEW, overflow_suffix: bool = False
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


def idle_line(run: ScenarioRun) -> str:
    """Buses that never formed a route, or "" when the whole fleet ran."""
    idle = idle_bus_ids(run.buses, run.plans)
    return f"Idle ({len(idle)}): {idle}" if idle else ""


def run_metrics(
    scenario: dict,
    data: InstanceData,
    plans: list[BusPlan],
) -> RunMetrics:
    """The served/used/route numbers every summary row reads."""
    served, total, percentage = served_ratio(data, plans)
    reference = reference_plan(plans)
    raw_limit = scenario.get("max_time_limit")
    return RunMetrics(
        served=served,
        total=total,
        percentage=percentage,
        used=sum(1 for plan in plans if plan.served_passengers > 0),
        limit=int(raw_limit) if raw_limit else 0,
        longest=reference.travel_time_minutes if reference else 0,
        peak=reference.peak_load if reference else 0,
        reference=reference,
    )


def markdown_table(
    headers: Sequence[str],
    rows: Iterable[Sequence[str]],
) -> list[str]:
    """Header, separator and body of a markdown table."""
    return [
        "| " + " | ".join(headers) + " |",
        "|" + "---|" * len(headers),
        *["| " + " | ".join(row) + " |" for row in rows],
    ]


def scenario_detail_lines(
    run: ScenarioRun,
    heading: list[str],
    metrics_line: str,
    plan_table: list[str],
) -> list[str]:
    """One run's detail block: heading, bus table and the shared tail.

    The heading, the metrics line and the per-bus table are rendered by the
    caller because each report lays them out differently; the tail (served
    pairs, idle buses, unserved demand and routes) is the same everywhere.
    """
    if run.error:
        return [
            *heading,
            "",
            f"ERROR after {run.elapsed:.1f}s: `{run.error}`",
            "",
        ]

    lines = [*heading, "", metrics_line, "", *plan_table, ""]
    for line in (
        served_pairs_line(run.plans),
        unserved_line(run.summary),
        idle_line(run),
    ):
        if line:
            lines += [line, ""]

    lines += ["Routes:", "", "```"]
    lines += [route_line(plan) for plan in run.plans]
    lines += ["```", ""]
    return lines
