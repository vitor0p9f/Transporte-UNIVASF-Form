"""Run every scenario with both heuristics and write the results report.

The TOP heuristic and Clarke-Wright run on the SAME scenarios and limits, and
both land in one markdown report (one row each in the summary table) so the
reader sees the trade-off without lining up two separate reports.
"""

import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple

import reporting
from algorithms import clarke_wright
from algorithms.top_univasf import (
    BusPlan,
    FleetSummary,
    InstanceData,
    solve_scenario,
)
from entities.bus import Bus
from utils.fleet import load_fleet, parse_fleet_ids
from utils.scenarios import load_scenarios

ROOT = Path(__file__).resolve().parent

OUT_PATH = ROOT / "results.md"

TOP_NAME = "TOP (Greedy OD)"
CW_NAME = "Clarke-Wright"

#: Solver settings used by the sweep in `main`. The CW defaults come from the
#: paper (two-phase, post-improvement); the sweep trades generality for runtime.
SWEEP_CW_KWARGS: dict = {
    "lam": 1.0,            # λ fixo (CW-1) em vez de varrer 0.1–2.0
    "usar_two_phase": False,  # CW-1: without the two-phase selection
    "usar_postimprove": False,  # CW-1: without post-improvement
}


class Result(NamedTuple):
    """One heuristic's outcome on the scenario, ready for the summary table."""

    heuristic: str
    data: InstanceData
    plans: list[BusPlan]
    summary: FleetSummary
    elapsed: float


@dataclass
class ScenarioOutcome:
    """One scenario with one run per heuristic (TOP and/or Clarke-Wright)."""

    scenario: dict
    buses: list[Bus]
    runs: list[Result]

    @property
    def scenario_id(self) -> str:
        return str(self.scenario.get("scenario_id"))

    @property
    def instance_id(self) -> str:
        return str(self.scenario.get("instance_id"))

    @property
    def period(self) -> str:
        return str(self.scenario.get("period"))

    @property
    def fleet(self) -> str:
        return str(self.scenario.get("fleet_bus_ids"))

    @property
    def limit(self) -> str:
        return str(self.scenario.get("max_time_limit"))


def run_heuristic(
    scenario: dict,
    buses: list[Bus],
    heuristic: str,
    cw_kwargs: dict | None = None,
) -> Result:
    """One heuristic's outcome for one scenario (TOP or Clarke-Wright)."""
    start = time.monotonic()
    if heuristic == TOP_NAME:
        data, plans, summary = solve_scenario(scenario, buses, ROOT)
    elif heuristic == CW_NAME:
        data, plans, summary = solve_clarke_wright(scenario, buses, cw_kwargs)
    else:
        raise ValueError(f"heurística desconhecida: {heuristic}")
    return Result(heuristic, data, plans, summary, time.monotonic() - start)


def iter_all_scenarios(
    heuristics: list[str] = (TOP_NAME, CW_NAME),
    cw_kwargs: dict | None = None,
) -> Iterator[ScenarioOutcome]:
    """Run every scenario, each with the given heuristics, in scenario order."""
    for scenario in load_scenarios(ROOT):
        buses = load_fleet(
            ROOT / "fleet.csv", parse_fleet_ids(scenario["fleet_bus_ids"])
        )
        runs = [
            run_heuristic(scenario, buses, heuristic, cw_kwargs)
            for heuristic in heuristics
        ]
        yield ScenarioOutcome(scenario=scenario, buses=buses, runs=runs)


def run_all_scenarios(
    heuristics: list[str] = (TOP_NAME, CW_NAME),
    cw_kwargs: dict | None = None,
) -> list[ScenarioOutcome]:
    """All scenarios with one run per heuristic, as a list."""
    return list(iter_all_scenarios(heuristics, cw_kwargs))


def _scenario_markdown(outcome: ScenarioOutcome) -> list[str]:
    lines = [
        f"## Scenario {outcome.scenario_id} — {outcome.instance_id} / {outcome.period}",
        "",
        f"Fleet [{outcome.fleet}] · limit {outcome.limit} min",
        "",
    ]
    for result in outcome.runs:
        served, total, percentage = reporting.served_ratio(result.data, result.plans)
        lines += [
            f"### {result.heuristic}",
            "",
            (
                f"{reporting.fleet_totals_line(result.plans, outcome.buses, result.data)} · "
                f"{result.summary.rounds} rounds · {result.elapsed:.1f}s · "
                f"{served}/{total} pax atendidos ({percentage:.0f}%)"
            ),
            "",
            "| bus | stops | pax | time | peak | pax/min | origin | destination |",
            "|---|---|---|---|---|---|---|---|",
        ]
        capacity = {bus.id: bus.passenger_capacity for bus in outcome.buses}
        time_limit = int(outcome.scenario.get("max_time_limit") or 0) or 60
        for plan in result.plans:
            lines.append(
                "| "
                + " | ".join(
                    reporting.plan_cells(plan, time_limit, capacity.get(plan.bus_id))
                )
                + " |"
            )
        served_pairs = reporting.served_pairs_line(result.plans)
        if served_pairs:
            lines += ["", served_pairs]
        unserved = reporting.unserved_line(result.summary)
        if unserved:
            lines += ["", unserved]
        idle = reporting.idle_bus_ids(outcome.buses, result.plans)
        if idle:
            lines += ["", f"Idle ({len(idle)}): {idle}"]
        lines += ["", "Routes:", "", "```"]
        lines += [reporting.route_line(plan) for plan in result.plans]
        lines += ["", "```", ""]
    return lines


def render_markdown(outcomes: list[ScenarioOutcome], generated_at: str) -> str:
    """Full markdown report: one summary-table row per scenario × heuristic."""
    lines = [
        "# Results — all scenarios (TOP + Clarke-Wright)",
        "",
        (
            f"Generated on {generated_at} · {len(outcomes)} scenarios · "
            f"{sum(len(outcome.runs) for outcome in outcomes)} runs · both heuristics "
            "on the same scenario."
        ),
        "",
        (
            "| scenario | instance | period | fleet | limit | heuristic | used | "
            "pax total | pax atendidos | pax não atendidos | % | rounds | exec (s) |"
        ),
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for outcome in outcomes:
        for result in outcome.runs:
            served, total, percentage = reporting.served_ratio(result.data, result.plans)
            lines.append(
                f"| {outcome.scenario_id} | {outcome.instance_id} | {outcome.period} | "
                f"[{outcome.fleet}] | {outcome.limit} | {result.heuristic} | "
                f"{len(result.plans)}/{len(outcome.buses)} | {served}/{total} | {served} | "
                f"{result.summary.unserved_passengers} | {percentage:.0f}% | "
                f"{result.summary.rounds} | {result.elapsed:.1f} |"
            )
    lines.append("")
    for outcome in outcomes:
        lines += _scenario_markdown(outcome)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def write_markdown(
    outcomes: list[ScenarioOutcome], path: Path = OUT_PATH
) -> str:
    """Write the sweep report to `results.md` and return the text."""
    markdown = render_markdown(
        outcomes,
        datetime.now(UTC).astimezone().strftime("%Y-%m-%d %H:%M %Z"),
    )
    path.write_text(markdown, encoding="utf-8")
    return markdown


def solve_clarke_wright(
    scenario: dict, buses: list[Bus], cw_kwargs: dict | None = None
) -> tuple[InstanceData, list[BusPlan], FleetSummary]:
    """Run CW on the scenario and reshape its solution into the run model.

    The scenario's fleet is the same one `load_fleet` gave the caller, so the
    bus ids assigned by `planos_e_resumo` match the ones in the table.
    """
    data, routes, context, attendance, _lam = clarke_wright.resolver_cenario(
        scenario, **(cw_kwargs or {})
    )
    plans, summary = clarke_wright.planos_e_resumo(
        routes, context, attendance, buses
    )
    return data, plans, summary


def print_results_table(
    scenario: dict, results: list[Result], buses: list[Bus]
) -> None:
    print("\n=== Results ===")
    print(
        "atendidos = medida pela simulação de embarque/desembarque · "
        "peak = maior pico simultâneo entre as rotas · "
        "tempo = duração da rota mais longa (min)"
    )

    header = reporting.SUMMARY_HEADERS
    rows = [
        reporting.summary_cells(
            scenario["scenario_id"],
            result.heuristic,
            result.data,
            result.plans,
            result.summary,
            buses,
        )
        for result in results
    ]
    widths = [len(cell) for cell in header]
    for row in rows:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*header))
    print(fmt.format(*["-" * width for width in widths]))
    for row in rows:
        print(fmt.format(*row))

    for result in results:
        print(f"\n--- {result.heuristic} ({result.elapsed:.1f}s) ---")
        print(f"Σ {reporting.fleet_totals_line(result.plans, buses, result.data)}")

        served_pairs = reporting.served_pairs_line(result.plans)
        if served_pairs:
            print(served_pairs)
        idle = reporting.idle_bus_ids(buses, result.plans)
        if idle:
            print(f"Idle ({len(idle)}): {idle} — no route formed")
        unserved = reporting.unserved_line(result.summary)
        if unserved:
            print(unserved)

        print("Routes:")
        for plan in result.plans:
            print(f"  {reporting.route_line(plan)}")
        if not result.plans:
            print("  (no bus formed a feasible route)")


def main() -> None:
    """Run every scenario with both heuristics and write results.md as it goes."""
    heuristics: list[str] = [TOP_NAME, CW_NAME]
    outcomes: list[ScenarioOutcome] = []
    for outcome in iter_all_scenarios(heuristics, SWEEP_CW_KWARGS):
        outcomes.append(outcome)
        write_markdown(outcomes, OUT_PATH)
    print(f"OK: {OUT_PATH} ({len(outcomes)} scenarios, "
          f"{sum(len(outcome.runs) for outcome in outcomes)} runs)")


if __name__ == "__main__":
    main()
