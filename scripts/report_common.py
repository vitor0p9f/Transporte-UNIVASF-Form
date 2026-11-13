"""Helpers shared by the markdown report runners.

The report scripts differ in what they solve and how they lay the result out,
but they all select scenarios, time a run and format markdown tables the same
way. Keeping those pieces here avoids the copies drifting apart.
"""

import argparse
import sys
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import reporting
from algorithms.top_univasf import (
    BusPlan,
    FleetSummary,
    InstanceData,
    solve_scenario,
)
from entities.bus import Bus
from utils.fleet import load_fleet, parse_fleet_ids
from utils.scenarios import (
    DEFAULT_REPORT_SCENARIOS,
    load_scenarios,
    pick_scenarios,
)


@dataclass
class ScenarioRun:
    """Everything one scenario produced, including when it failed."""

    scenario: dict
    buses: list[Bus]
    elapsed: float
    data: InstanceData | None = None
    plans: list[BusPlan] = field(default_factory=list)
    summary: FleetSummary | None = None
    error: str = ""

    @property
    def scenario_id(self) -> str:
        return str(self.scenario["scenario_id"])


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


def select_scenarios(
    ids: tuple[str, ...] = DEFAULT_REPORT_SCENARIOS,
    root: str | Path = ROOT,
    *,
    files: tuple[str, ...] | None = None,
) -> list[dict]:
    """The requested scenarios, in the requested order.

    ``files`` lets the controlled runner select from its own scenario copy
    while keeping the same ordering and validation rules.
    """
    scenarios = (
        load_scenarios(root, files=files)
        if files is not None
        else load_scenarios(root)
    )
    return pick_scenarios(scenarios, ids)


def parse_scenario_ids(
    only: str | None,
    default: tuple[str, ...] = DEFAULT_REPORT_SCENARIOS,
) -> tuple[str, ...]:
    """Parse the ``--only`` comma-separated value, falling back to ``default``."""
    if not only:
        return default
    return tuple(item.strip() for item in only.split(",") if item.strip())


def add_only_argument(
    parser: argparse.ArgumentParser,
    default: tuple[str, ...] = DEFAULT_REPORT_SCENARIOS,
) -> None:
    """Add the common ``--only`` option to a report parser."""
    parser.add_argument(
        "--only",
        default=None,
        help=(
            "comma-separated scenario ids "
            f"(default: {','.join(default)})"
        ),
    )


def scenario_buses(
    scenario: dict,
    root: str | Path = ROOT,
    *,
    fleet: str = "fleet.csv",
) -> list[Bus]:
    """Load the buses named by a scenario from a fleet CSV."""
    return load_fleet(
        Path(root) / fleet,
        parse_fleet_ids(scenario["fleet_bus_ids"]),
    )


def run_scenario(
    scenario: dict,
    root: str | Path = ROOT,
    *,
    fleet: str = "fleet.csv",
    catch_errors: bool = False,
) -> ScenarioRun:
    """Solve one scenario and record its time, plans and summary.

    With ``catch_errors`` the failure is stored on the result so a batch report
    can keep going; otherwise the exception propagates.
    """
    root = Path(root)
    buses = scenario_buses(scenario, root, fleet=fleet)
    start = time.monotonic()
    try:
        data, plans, summary = solve_scenario(scenario, buses, root)
        error = ""
    except Exception as exc:
        if not catch_errors:
            raise
        data, plans, summary, error = None, [], None, f"{type(exc).__name__}: {exc}"
    return ScenarioRun(
        scenario=scenario,
        buses=buses,
        elapsed=time.monotonic() - start,
        data=data,
        plans=plans,
        summary=summary,
        error=error,
    )


def run_metrics(
    scenario: dict,
    data: InstanceData,
    plans: list[BusPlan],
    buses: list[Bus],
) -> RunMetrics:
    """The served/used/route numbers every summary row reads."""
    served, total, percentage = reporting.served_ratio(data, plans)
    reference = reporting.reference_plan(plans)
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


def scenario_operational_cost(
    scenario: dict,
    data: InstanceData,
    plans: list[BusPlan],
    buses: list[Bus],
) -> reporting.OperationalCost:
    """Cost of a run, charging each route its own bus's fuel autonomy."""
    return reporting.operational_cost_per_bus(
        plans,
        data,
        buses,
        diesel_price=float(scenario["diesel_price_per_liter"]),
        driver_hourly_rate=float(scenario["driver_hourly_rate"]),
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
