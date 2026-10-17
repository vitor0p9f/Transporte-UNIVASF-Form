"""Roda todos os cenários e grava os resultados num .md.

Cada cenário roda uma única vez: o resultado alimenta tanto a tabela-resumo
quanto o detalhe (rotas, pares atendidos, ônibus ociosos). A renderização em
si vem de `reporting`, o mesmo módulo usado pelo `main.py`.
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
#: Cenários que usam a instância `base` são fixos, não sorteados.
FIXED_INSTANCE = "base"


@dataclass
class ScenarioRun:
    """Tudo o que um cenário produziu, inclusive quando ele falhou."""

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
    """Roda um cenário e registra tempo, planos e resumo (ou o erro)."""
    buses = load_fleet(ROOT / "fleet.csv", parse_fleet_ids(scenario["fleet_bus_ids"]))
    start = time.monotonic()
    try:
        data, plans, summary = solve_scenario(scenario, buses, ROOT)
        error = ""
    except Exception as exc:  # noqa: BLE001 — registra e segue para o próximo
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
    origin = f" | origem {scenario['origin']}" if scenario.get("origin") else ""
    destinations = (
        f" -> [{scenario['destination_labels']}]"
        if scenario.get("destination_labels")
        else ""
    )
    return (
        f"## Cenário {scenario['scenario_id']} — {scenario['instance_id']} / "
        f"{scenario['period']} (frota [{scenario['fleet_bus_ids']}], "
        f"limite {scenario['max_time_limit']} min{origin}{destinations})"
    )


def _summary_row(run: ScenarioRun) -> str:
    scenario = run.scenario
    prefix = (
        f"| {scenario['scenario_id']} | {scenario['instance_id']} | {scenario['period']} | "
        f"[{scenario['fleet_bus_ids']}] | {scenario['max_time_limit']} | "
    )
    if run.error:
        return prefix + f"ERRO | — | — | — | {run.elapsed:.1f} |"
    served, total, percentage = reporting.served_ratio(run.data, run.plans)
    return (
        prefix
        + f"{len(run.plans)}/{len(run.buses)} | {served}/{total} | {percentage:.0f}% | "
        + f"{run.summary.rounds} | {run.elapsed:.1f} |"
    )


def _detail_lines(run: ScenarioRun) -> list[str]:
    """Detalhe de um cenário: cabeçalho, tabela de ônibus e rotas."""
    lines = [_scenario_heading(run), ""]
    if run.error:
        return lines + [f"ERRO após {run.elapsed:.1f}s: `{run.error}`", ""]

    scenario = run.scenario
    capacity = {bus.id: bus.passenger_capacity for bus in run.buses}
    lines.append(
        f"{reporting.fleet_totals_line(run.plans, run.buses, run.data)} · "
        f"{run.summary.rounds} rodadas · {run.elapsed:.1f}s"
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

    lines += ["Rotas:", "", "```"]
    lines += [reporting.route_line(plan) for plan in run.plans]
    lines += ["```", ""]
    return lines


def _idle_line(run: ScenarioRun) -> str:
    idle = reporting.idle_bus_ids(run.buses, run.plans)
    return f"Ociosos ({len(idle)}): {idle}" if idle else ""


def render(runs: list[ScenarioRun], generated_at: str) -> list[str]:
    """Relatório completo: cabeçalho, tabela-resumo e detalhe por cenário."""
    fixed = sum(1 for run in runs if run.scenario["instance_id"] == FIXED_INSTANCE)
    lines = [
        "# Resultados — todos os cenários (TOP UNIVASF)",
        "",
        f"Gerado em {generated_at} · {len(runs)} cenários ({fixed} fixos de base) · "
        + f"seed de geração {DEFAULT_SEED} (utils/seed.py).",
        "",
        "| cenário | instância | período | frota | limite | usados | pax | % | rounds | exec (s) |",
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
    print(f"OK: {OUT} ({len(scenarios)} cenários)")


if __name__ == "__main__":
    main()
