"""Run every scenario and write the results to a .md report.

Each scenario runs exactly once: the outcome feeds both the summary table and
the per-scenario detail (routes, served pairs, idle buses). The rendering
itself comes from `reporting`, the same module `main.py` uses.
"""

import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
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
from utils.scenarios import load_scenarios
from utils.seed import DEFAULT_SEED

OUT = ROOT / "results.md"
#: Scenarios using the `base` instance are fixed, not sampled.
FIXED_INSTANCE = "base"


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
        return self.scenario["scenario_id"]


def run_scenario(scenario: dict) -> ScenarioRun:
    """Run one scenario and record its time, plans and summary (or the error)."""
    buses = load_fleet(ROOT / "fleet.csv", parse_fleet_ids(scenario["fleet_bus_ids"]))
    start = time.monotonic()
    try:
        data, plans, summary = solve_scenario(scenario, buses, ROOT)
        error = ""
    except Exception as exc:  # noqa: BLE001 -- record it and move on
        data, plans, summary, error = None, [], None, f"{type(exc).__name__}: {exc}"
    elapsed = time.monotonic() - start
    return ScenarioRun(
        scenario=scenario,
        buses=buses,
        elapsed=elapsed,
        data=data,
        plans=plans,
        summary=summary,
        error=error,
    )


def _scenario_heading(run: ScenarioRun) -> str:
    scenario = run.scenario
    origin = f" | origin {scenario['origin']}" if scenario.get("origin") else ""
    destinations = (
        f" -> [{scenario['destination_labels']}]"
        if scenario.get("destination_labels")
        else ""
    )
    return (
        f"## Scenario {scenario['scenario_id']} — {scenario['instance_id']} / "
        f"{scenario['period']} (fleet [{scenario['fleet_bus_ids']}], "
        f"limit {scenario['max_time_limit']} min{origin}{destinations})"
    )


def _summary_row(run: ScenarioRun) -> str:
    scenario = run.scenario
    prefix = (
        f"| {scenario['scenario_id']} | {scenario['instance_id']} | {scenario['period']} | "
        f"[{scenario['fleet_bus_ids']}] | {scenario['max_time_limit']} | "
    )
    if run.error:
        return prefix + f"ERROR | — | — | — | {run.elapsed:.1f} |"
    served, total, percentage = reporting.served_ratio(run.data, run.plans)
    return (
        prefix
        + f"{len(run.plans)}/{len(run.buses)} | {served}/{total} | {percentage:.0f}% | "
        + f"{run.summary.rounds} | {run.elapsed:.1f} |"
    )


def _detail_lines(run: ScenarioRun) -> list[str]:
    """One scenario's detail: heading, bus table and routes."""
    lines = [_scenario_heading(run), ""]
    if run.error:
        return lines + [f"ERROR after {run.elapsed:.1f}s: `{run.error}`", ""]

    scenario = run.scenario
    capacity = {bus.id: bus.passenger_capacity for bus in run.buses}
    lines.append(
        f"{reporting.fleet_totals_line(run.plans, run.buses, run.data)} · "
        f"{run.summary.rounds} rounds · {run.elapsed:.1f}s"
    )
    lines.append("")
    lines.append("| " + " | ".join(reporting.PLAN_HEADERS) + " |")
    lines.append("|" + "---|" * len(reporting.PLAN_HEADERS))
    for plan in run.plans:
        cells = reporting.plan_cells(
            plan, scenario["max_time_limit"], capacity.get(plan.bus_id)
        )
        lines.append("| " + " | ".join(cells) + " |")
    lines.append("")

    for line in (
        reporting.served_pairs_line(run.plans),
        _idle_line(run),
        reporting.unserved_line(run.summary),
    ):
        if line:
            lines += [line, ""]

    lines += ["Routes:", "", "```"]
    lines += [reporting.route_line(plan) for plan in run.plans]
    lines += ["```", ""]
    return lines


def _idle_line(run: ScenarioRun) -> str:
    idle = reporting.idle_bus_ids(run.buses, run.plans)
    return f"Idle ({len(idle)}): {idle}" if idle else ""


def render(runs: list[ScenarioRun], generated_at: str) -> list[str]:
    """Full report: header, summary table and one detail block per scenario."""
    fixed = sum(1 for run in runs if run.scenario["instance_id"] == FIXED_INSTANCE)
    lines = [
        "# Results — all scenarios (TOP UNIVASF)",
        "",
        f"Generated on {generated_at} · {len(runs)} scenarios "
        + f"({fixed} fixed base) · generation seed {DEFAULT_SEED} (utils/seed.py).",
        "",
        "| scenario | instance | period | fleet | limit | used | pax | % | rounds | exec (s) |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [_summary_row(run) for run in runs]
    lines.append("")
    for run in runs:
        lines += _detail_lines(run)
    return lines


def main() -> None:
    scenarios = load_scenarios(ROOT)
    runs = [run_scenario(scenario) for scenario in scenarios]
    generated_at = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    OUT.write_text("\n".join(render(runs, generated_at)), encoding="utf-8")
    print(f"OK: {OUT} ({len(scenarios)} scenarios)")


if __name__ == "__main__":
    main()
