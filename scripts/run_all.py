"""Run the report scenarios and write the results to a .md report.

Each scenario runs exactly once: the outcome feeds both the summary table and
the per-scenario detail (routes, served pairs, idle buses). TOP scores
passengers per real (R$), using each bus's own fuel autonomy. The rendering
itself comes from `reporting`, the same module `main.py` uses.

Default scenarios: 16, 19, 32, 65 and 69, in that order.
"""

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import reporting
from scripts import report_common
from scripts.report_common import (
    ScenarioRun,
    add_only_argument,
    markdown_table,
    parse_scenario_ids,
)
from utils.scenarios import DEFAULT_REPORT_SCENARIOS
from utils.seed import DEFAULT_SEED

OUT = ROOT / "results.md"
#: Scenarios run by default, in output order.
DEFAULT_SCENARIOS = DEFAULT_REPORT_SCENARIOS
#: Scenarios using the `base` instance are fixed, not sampled.
FIXED_INSTANCE = "base"
#: Header of the summary table, in the same order as `_summary_row`.
SUMMARY_HEADERS = (
    "scenario",
    "instance",
    "period",
    "fleet",
    "limit",
    "used",
    "pax",
    "%",
    "rounds",
    "exec (s)",
)


def run_scenario(scenario: dict) -> ScenarioRun:
    """Run one scenario and record its time, plans and summary (or the error)."""
    return report_common.run_scenario(scenario, catch_errors=True)


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


def _summary_row(run: ScenarioRun) -> tuple[str, ...]:
    scenario = run.scenario
    prefix = (
        str(scenario["scenario_id"]),
        str(scenario["instance_id"]),
        str(scenario["period"]),
        f"[{scenario['fleet_bus_ids']}]",
        str(scenario["max_time_limit"]),
    )
    if run.error:
        return prefix + ("ERROR", "—", "—", "—", f"{run.elapsed:.1f}")
    served, total, percentage = reporting.served_ratio(run.data, run.plans)
    return prefix + (
        f"{len(run.plans)}/{len(run.buses)}",
        f"{served}/{total}",
        f"{percentage:.0f}%",
        str(run.summary.rounds),
        f"{run.elapsed:.1f}",
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
    lines += markdown_table(
        reporting.PLAN_HEADERS,
        (
            reporting.plan_cells(
                plan, scenario["max_time_limit"], capacity.get(plan.bus_id)
            )
            for plan in run.plans
        ),
    )
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
        "# Results — report scenarios (TOP UNIVASF)",
        "",
        f"Generated on {generated_at} · {len(runs)} scenarios "
        + f"({fixed} fixed base) · generation seed {DEFAULT_SEED} (utils/seed.py).",
        "",
    ]
    lines += markdown_table(SUMMARY_HEADERS, (_summary_row(run) for run in runs))
    lines.append("")
    for run in runs:
        lines += _detail_lines(run)
    return lines


def select_scenarios(
    ids: tuple[str, ...] = DEFAULT_SCENARIOS, root: str | Path = ROOT
) -> list[dict]:
    """The requested scenarios, in the requested order."""
    return report_common.select_scenarios(ids, root)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    add_only_argument(parser, DEFAULT_SCENARIOS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ids = parse_scenario_ids(args.only, DEFAULT_SCENARIOS)
    scenarios = select_scenarios(ids)
    runs = [run_scenario(scenario) for scenario in scenarios]
    generated_at = datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    OUT.write_text("\n".join(render(runs, generated_at)), encoding="utf-8")
    print(f"OK: {OUT} ({len(scenarios)} scenarios)")


if __name__ == "__main__":
    main()
