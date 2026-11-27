"""Run the default report scenarios with TOP and write the report.

TOP runs on the real scenario fleet and limits. This is the standard
operational view; the Clarke-Wright comparison lives in the controlled reports
(``scripts/run_controlled_reports.py``), where both heuristics share the same
homogeneous fleet and the same scenario filters. TOP scores passengers per
real (R$), using each bus's own fuel autonomy.

This is the single producer of ``results.md``; ``scripts/run_all.py`` is a thin
``--only`` wrapper around it.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from itertools import groupby
from pathlib import Path

import reporting
from algorithms.top_univasf import solve_scenario
from entities.bus import Bus
from scripts import report_common
from utils.fleet import load_fleet, parse_fleet_ids
from utils.scenarios import (
    DEFAULT_REPORT_SCENARIOS,
    load_scenarios,
    pick_scenarios,
)

ROOT = Path(__file__).resolve().parent

OUT_PATH = ROOT / "results.md"

TOP_NAME = "TOP (Greedy OD)"


def run_top(scenario: dict, buses: list[Bus]) -> reporting.ScenarioRun:
    """TOP's outcome for one scenario, on the scenario's real fleet.

    No `origin`/`depot` override: the draft chooses the OD pair among the
    scenario's `origin` and `destination_labels` columns.
    """
    return report_common.run_scenario(
        scenario,
        ROOT,
        solver=solve_scenario,
        buses=buses,
        heuristic=TOP_NAME,
    )


def iter_scenario_runs(
    scenario_ids: tuple[str, ...] = DEFAULT_REPORT_SCENARIOS,
) -> Iterator[reporting.ScenarioRun]:
    """One TOP run per scenario, in scenario order."""
    for scenario in pick_scenarios(load_scenarios(ROOT), scenario_ids):
        buses = load_fleet(
            ROOT / "fleet.csv", parse_fleet_ids(scenario["fleet_bus_ids"])
        )
        yield run_top(scenario, buses)


def _scenario_detail(
    runs: list[reporting.ScenarioRun],
) -> list[str]:
    """One scenario's detail: heading, then one block per heuristic."""
    first = runs[0]
    capacity = {bus.id: bus.passenger_capacity for bus in first.buses}
    time_limit = int(first.scenario.get("max_time_limit") or 0) or 60
    origin = f" · origin {first.scenario['origin']}" if first.scenario.get("origin") else ""
    destinations = (
        f" -> [{first.scenario['destination_labels']}]"
        if first.scenario.get("destination_labels")
        else ""
    )
    lines = [
        f"## Scenario {first.scenario_id} — {first.instance_id} / {first.period}",
        "",
        f"Fleet [{first.fleet}] · limit {first.limit} min{origin}{destinations}",
        "",
    ]
    for run in runs:
        heading = [f"### {run.heuristic}"]
        if run.error:
            lines += reporting.scenario_detail_lines(
                run, heading=heading, metrics_line="", plan_table=[]
            )
            continue
        metrics_line = (
            f"{reporting.fleet_totals_line(run.plans, run.buses, run.data)} · "
            f"{run.summary.rounds} rounds · {run.elapsed:.1f}s"
        )
        plan_table = reporting.markdown_table(
            reporting.PLAN_HEADERS,
            (
                reporting.plan_cells(
                    plan, time_limit, capacity.get(plan.bus_id)
                )
                for plan in run.plans
            ),
        )
        lines += reporting.scenario_detail_lines(
            run,
            heading=heading,
            metrics_line=metrics_line,
            plan_table=plan_table,
        )
    return lines


def _reference_capacity(
    run: reporting.ScenarioRun, metrics: reporting.RunMetrics
) -> int:
    """Passenger capacity of the bus that drove the summary's reference route."""
    if metrics.reference is None:
        return 0
    by_id = {bus.id: bus.passenger_capacity for bus in run.buses}
    return by_id.get(metrics.reference.bus_id, 0)


def _summary_row(run: reporting.ScenarioRun) -> str:
    """One row of the summary table (scenario × heuristic).

    The time and the peak come from the longest route that served someone (the
    same reference the per-bus table and the other reports use); the peak is
    that route's highest simultaneous occupancy over the capacity of the bus
    that drove it. The costs charge each route its own bus's fuel autonomy, so
    the heterogeneous fleet is priced per vehicle.
    """
    prefix = (
        f"| {run.scenario_id} | {run.instance_id} | {run.period} | "
        f"[{run.fleet}] | {run.limit} | {run.heuristic} | "
    )
    if run.error:
        return prefix + "ERROR | — | — | — | — | — | — | — | — | " f"{run.elapsed:.1f} |"
    metrics = reporting.run_metrics(run.scenario, run.data, run.plans)
    cost = report_common.scenario_operational_cost(
        run.scenario, run.data, run.plans, run.buses
    )
    time_cell = (
        f"{metrics.longest}/{metrics.limit}"
        if metrics.limit
        else str(metrics.longest)
    )
    capacity = _reference_capacity(run, metrics)
    return (
        prefix
        + f"{len(run.plans)}/{len(run.buses)} | "
        f"{metrics.served}/{metrics.total} | "
        f"{run.summary.unserved_passengers} | {metrics.percentage:.0f}% | "
        f"{time_cell} | {metrics.peak}/{capacity} | {cost.total:.2f} | "
        f"{cost.per_passenger(metrics.served):.2f} | "
        f"{run.summary.rounds} | {run.elapsed:.1f} |"
    )


def render_markdown(
    runs: list[reporting.ScenarioRun], generated_at: str
) -> str:
    """Full markdown report: one summary-table row per scenario × heuristic."""
    scenarios = len({run.scenario_id for run in runs})
    lines = [
        "# Results — report scenarios (TOP)",
        "",
        (
            f"Generated on {generated_at} · {scenarios} scenarios · "
            f"{len(runs)} runs."
        ),
        "",
        (
            "The costs are recomputed per bus from the final routes: fuel uses "
            "each bus's own km/L (the heterogeneous fleet of `fleet.csv`) and "
            "the driver the route hours, both priced by the scenario. Only "
            "routes that serve someone are charged, and the longest route is "
            "the longest one that served someone (shown as route/limit); the "
            "peak is that route's highest simultaneous occupancy over the "
            "capacity of the bus that drove it."
        ),
        "",
        (
            "| scenario | instance | period | fleet | limit | heuristic | used | "
            "pax atendidos / total | pax não atendidos | % | maior rota / "
            "limite (min) | pico / capacidade | custo operacional (R$) | "
            "custo por passageiro (R$) | rounds | exec (s) |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    lines += [_summary_row(run) for run in runs]
    lines.append("")
    for _, group in groupby(runs, key=lambda run: run.scenario_id):
        lines += _scenario_detail(list(group))
    return "\n".join(lines).rstrip("\n") + "\n"


def write_markdown(
    runs: list[reporting.ScenarioRun], path: Path = OUT_PATH
) -> str:
    """Write the sweep report to `path` and return the text."""
    markdown = render_markdown(
        runs,
        datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
    )
    path.write_text(markdown, encoding="utf-8")
    return markdown


def run(
    scenario_ids: tuple[str, ...] = DEFAULT_REPORT_SCENARIOS,
    path: Path = OUT_PATH,
) -> Path:
    """Run the selected scenarios and write the report; return its path."""
    runs = list(iter_scenario_runs(scenario_ids=scenario_ids))
    write_markdown(runs, path)
    scenarios = len({run.scenario_id for run in runs})
    print(f"OK: {path} ({scenarios} scenarios, {len(runs)} runs)")
    return path


def main() -> None:
    """Run the default scenarios with TOP and write results.md."""
    run()


if __name__ == "__main__":
    main()
