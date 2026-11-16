"""Run the default report scenarios with both heuristics and write the report.

The TOP heuristic and Clarke-Wright run on the SAME scenarios and limits, and
both land in one markdown report (one row each in the summary table) so the
reader sees the trade-off without lining up two separate reports. TOP scores
passengers per real (R$), using each bus's own fuel autonomy.

This is the single producer of ``results.md``; ``scripts/run_all.py`` is a thin
``--only`` wrapper around it.
"""

from collections.abc import Iterator
from datetime import UTC, datetime
from functools import partial
from itertools import groupby
from pathlib import Path

import reporting
from algorithms import clarke_wright
from algorithms.top_univasf import (
    BusPlan,
    FleetSummary,
    InstanceData,
    solve_scenario,
)
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
CW_NAME = "Clarke-Wright"

#: Solver settings used by the sweep in `main`. The CW defaults come from the
#: paper (two-phase, post-improvement); the sweep trades generality for runtime.
SWEEP_CW_KWARGS: dict = {
    "lam": 1.0,            # λ fixo (CW-1) em vez de varrer 0.1–2.0
    "use_two_phase": False,  # CW-1: without the two-phase selection
    "use_post_improvement": False,  # CW-1: without post-improvement
}


def run_heuristic(
    scenario: dict,
    buses: list[Bus],
    heuristic: str,
    cw_kwargs: dict | None = None,
) -> reporting.ScenarioRun:
    """One heuristic's outcome for one scenario (TOP or Clarke-Wright)."""
    if heuristic == TOP_NAME:
        solver = solve_scenario
    elif heuristic == CW_NAME:
        solver = partial(solve_clarke_wright, cw_kwargs=cw_kwargs)
    else:
        raise ValueError(f"unknown heuristic: {heuristic}")
    return report_common.run_scenario(
        scenario,
        ROOT,
        solver=solver,
        buses=buses,
        heuristic=heuristic,
    )


def iter_scenario_runs(
    heuristics: tuple[str, ...] = (TOP_NAME, CW_NAME),
    cw_kwargs: dict | None = None,
    scenario_ids: tuple[str, ...] = DEFAULT_REPORT_SCENARIOS,
) -> Iterator[reporting.ScenarioRun]:
    """Every (scenario, heuristic) run, in scenario order."""
    for scenario in pick_scenarios(load_scenarios(ROOT), scenario_ids):
        buses = load_fleet(
            ROOT / "fleet.csv", parse_fleet_ids(scenario["fleet_bus_ids"])
        )
        for heuristic in heuristics:
            yield run_heuristic(scenario, buses, heuristic, cw_kwargs)


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


def _summary_row(run: reporting.ScenarioRun) -> str:
    """One row of the summary table (scenario × heuristic)."""
    prefix = (
        f"| {run.scenario_id} | {run.instance_id} | {run.period} | "
        f"[{run.fleet}] | {run.limit} | {run.heuristic} | "
    )
    if run.error:
        return prefix + "ERROR | — | — | — | — | — | " f"{run.elapsed:.1f} |"
    served, total, percentage = reporting.served_ratio(run.data, run.plans)
    return (
        prefix
        + f"{len(run.plans)}/{len(run.buses)} | {served}/{total} | "
        f"{run.summary.unserved_passengers} | {percentage:.0f}% | "
        f"{run.summary.rounds} | {run.elapsed:.1f} |"
    )


def render_markdown(
    runs: list[reporting.ScenarioRun], generated_at: str
) -> str:
    """Full markdown report: one summary-table row per scenario × heuristic."""
    scenarios = len({run.scenario_id for run in runs})
    lines = [
        "# Results — report scenarios (TOP + Clarke-Wright)",
        "",
        (
            f"Generated on {generated_at} · {scenarios} scenarios · "
            f"{len(runs)} runs · both heuristics on the same scenario."
        ),
        "",
        (
            "| scenario | instance | period | fleet | limit | heuristic | used | "
            "pax atendidos / total | pax não atendidos | % | rounds | exec (s) |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|",
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


def solve_clarke_wright(
    scenario: dict,
    buses: list[Bus],
    root: Path = ROOT,
    cw_kwargs: dict | None = None,
) -> tuple[InstanceData, list[BusPlan], FleetSummary]:
    """Run CW on the scenario and reshape its solution into the run model.

    The scenario's fleet is the same one `load_fleet` gave the caller, so the
    bus ids assigned by `planos_e_resumo` match the ones in the table.
    """
    data, routes, context, attendance, _lam = clarke_wright.solve_scenario(
        scenario, **(cw_kwargs or {})
    )
    plans, summary = clarke_wright.plans_and_summary(
        routes, context, attendance, buses
    )
    return data, plans, summary


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
    """Run the default scenarios with both heuristics and write results.md."""
    run()


if __name__ == "__main__":
    main()
