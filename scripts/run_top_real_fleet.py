"""Run the TOP heuristic on the real (heterogeneous) fleet.

The controlled reports homogenise the fleet and force every bus to leave from
the scenario's first origin. This runner does neither: it loads the scenario's
buses straight from ``fleet.csv`` (each one keeps its own capacity and fuel
autonomy) and calls the solver with no fixed origin and no depot, so the draft
chooses the OD pair itself -- always respecting the scenario's ``origin`` and
``destination_labels`` columns, which are part of the scenario definition.

TOP scores passengers per real: each bus pays fuel with its own km/L plus the
driver, so the heterogeneous fleet's autonomy is part of the decision. The
operational cost follows the same convention as the other reports (only routes
that serve someone are charged), and fuel is computed per bus with that bus's
own km/L.

Default scenarios: 16, 19, 32, 65 and 69, in that order.

Usage:
  python scripts/run_top_real_fleet.py
  python scripts/run_top_real_fleet.py --only 65,32
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Imports must follow the sys.path setup above (same pattern as the other scripts).
import reporting
from algorithms.top_univasf import BusPlan
from entities.bus import Bus
from scripts import report_common
from scripts.report_common import (
    add_only_argument,
    parse_scenario_ids,
    scenario_operational_cost,
)
from utils.scenarios import DEFAULT_REPORT_SCENARIOS

#: Scenarios run by default, in output order.
DEFAULT_SCENARIOS = DEFAULT_REPORT_SCENARIOS

OUT_PATH = ROOT / "resultados_top_frota_real.md"

#: Header of the summary table, in the same order as `summary_cells`.
SUMMARY_HEADERS = (
    "Cenário",
    "Instância",
    "Período",
    "Frota",
    "Limite (min)",
    "Pax atendidos / Total",
    "%",
    "Ônibus usados / Frota",
    "Maior rota / Limite",
    "Pico / Capacidade do ônibus",
    "Custo operacional (R$)",
    "Custo por passageiro (R$)",
    "Rodadas",
    "Exec (s)",
)

#: Header of the per-bus table, in the same order as `plan_cells`.
PLAN_HEADERS = (
    "bus",
    "lugares",
    "km/L",
    "stops",
    "pax",
    "time",
    "peak",
    "pax/R$",
    "origin",
    "destination",
)


def select_scenarios(
    ids: tuple[str, ...] = DEFAULT_SCENARIOS,
    root: str | Path = ROOT,
) -> list[dict]:
    """The requested scenarios, in the requested order.

    ``load_scenarios`` already sums ``scenarios.csv`` and
    ``scenarios_base.csv``, so ids such as 65 (the hand-written ``base``
    instance) are found alongside the generated ones.
    """
    return report_common.select_scenarios(ids, root)


def run_scenario(
    scenario: dict, root: str | Path = ROOT
) -> reporting.ScenarioRun:
    """Solve one scenario on the real fleet, letting TOP pick the OD pair.

    No ``origin=`` and no ``depot=``: the draft scans the origins allowed by
    the scenario's ``origin`` column and the destinations allowed by
    ``destination_labels``, and the route is born at the chosen pair origin
    (no deadhead).
    """
    return report_common.run_scenario(scenario, root)


def _bus_by_id(buses: list[Bus]) -> dict[int, Bus]:
    return {bus.id: bus for bus in buses}


def operational_cost(run: reporting.ScenarioRun) -> reporting.OperationalCost:
    """Fuel + driver cost of one run, charging each route its own bus.

    The fleet is heterogeneous, so each plan's fuel is computed with the
    km/L of the bus that drove it (the other reports use one reference model
    because they homogenise the fleet). Only routes that serve someone are
    charged, matching the reports' "ônibus usados" column.
    """
    return scenario_operational_cost(
        run.scenario, run.data, run.plans, run.buses
    )


def summary_cells(run: reporting.ScenarioRun, cost: reporting.OperationalCost) -> tuple[str, ...]:
    """One summary row, in `SUMMARY_HEADERS` order."""
    scenario = run.scenario
    metrics = reporting.run_metrics(scenario, run.data, run.plans, run.buses)
    reference = metrics.reference
    capacity = (
        _bus_by_id(run.buses)[reference.bus_id].passenger_capacity
        if reference
        else 0
    )
    return (
        str(scenario["scenario_id"]),
        str(scenario["instance_id"]),
        str(scenario["period"]),
        f"[{scenario['fleet_bus_ids']}]",
        str(metrics.limit),
        f"{metrics.served}/{metrics.total}",
        f"{metrics.percentage:.0f}%",
        f"{metrics.used}/{len(run.buses)}",
        f"{metrics.longest}/{metrics.limit}",
        f"{metrics.peak}/{capacity}",
        f"{cost.total:.2f}",
        f"{cost.per_passenger(metrics.served):.2f}",
        str(run.summary.rounds),
        f"{run.elapsed:.1f}",
    )


def plan_cells(plan: BusPlan, bus: Bus, time_limit_minutes: int) -> tuple[str, ...]:
    """One plan's cells, in `PLAN_HEADERS` order (capacity and km/L added)."""
    cells = reporting.plan_cells(plan, time_limit_minutes, bus.passenger_capacity)
    return (
        cells[0],
        str(bus.passenger_capacity),
        f"{bus.km_autonomy_per_liter:.2f}",
        *cells[1:],
    )


def _scenario_markdown(run: reporting.ScenarioRun) -> list[str]:
    scenario = run.scenario
    limit = int(scenario["max_time_limit"])
    buses = _bus_by_id(run.buses)
    heading = [
        (
            f"## Cenário {scenario['scenario_id']} — "
            f"{scenario['instance_id']} / {scenario['period']}"
        ),
        "",
        f"Frota [{scenario['fleet_bus_ids']}] · limite {limit} min",
    ]
    metrics_line = (
        f"{reporting.fleet_totals_line(run.plans, run.buses, run.data)} · "
        f"{run.summary.rounds} rodadas · {run.elapsed:.1f}s"
    )
    plan_table = reporting.markdown_table(
        PLAN_HEADERS,
        (
            plan_cells(plan, buses[plan.bus_id], limit)
            for plan in run.plans
        ),
    )
    return reporting.scenario_detail_lines(
        run,
        heading=heading,
        metrics_line=metrics_line,
        plan_table=plan_table,
    )


def render_markdown(runs: list[reporting.ScenarioRun], generated_at: str) -> str:
    """Full report: configuration note, summary table and per-scenario detail."""
    lines = [
        "# Resultados — TOP na frota real",
        "",
        f"Gerado em {generated_at} · {len(runs)} cenários.",
        "",
        (
            "O TOP roda na frota heterogênea do `fleet.csv`: cada ônibus "
            "mantém a capacidade e a autonomia do seu próprio modelo, sem "
            "homogeneização. Não há origem nem depósito forçados: o draft "
            "escolhe o par origem-destino sozinho, respeitando as colunas "
            "`origin` e `destination_labels` do cenário (que fazem parte da "
            "definição dele), e a rota nasce no nó de origem do par, sem "
            "deadhead. As restrições de tempo e de capacidade estão ativas."
        ),
        "",
        (
            "O custo operacional é calculado por ônibus: combustível = km "
            "percorridos / (km por litro do veículo que fez a rota) × diesel "
            "do cenário; motorista = horas de rota × valor da hora do "
            "cenário. Só entram no custo e na rota de referência as rotas que "
            "atendem alguém."
        ),
        "",
    ]
    costs = [operational_cost(run) for run in runs]
    lines += reporting.markdown_table(
        SUMMARY_HEADERS,
        (
            summary_cells(run, cost)
            for run, cost in zip(runs, costs, strict=True)
        ),
    )
    lines.append("")
    for run in runs:
        lines += _scenario_markdown(run)
        lines.append("")
    return "\n".join(lines).rstrip("\n") + "\n"


def _print_progress(index: int, total: int, run: reporting.ScenarioRun) -> None:
    scenario = run.scenario
    served, total_pax, percentage = reporting.served_ratio(run.data, run.plans)
    used = sum(1 for plan in run.plans if plan.served_passengers > 0)
    print(
        f"[{index}/{total}] cenário {scenario['scenario_id']} "
        f"({scenario['instance_id']}/{scenario['period']}): "
        f"{served}/{total_pax} pax ({percentage:.0f}%) · "
        f"{used}/{len(run.buses)} ônibus · {run.elapsed:.1f}s",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=OUT_PATH)
    add_only_argument(parser, DEFAULT_SCENARIOS)
    args = parser.parse_args()

    ids = parse_scenario_ids(args.only, DEFAULT_SCENARIOS)
    scenarios = select_scenarios(ids)
    runs: list[reporting.ScenarioRun] = []
    for index, scenario in enumerate(scenarios, start=1):
        run = run_scenario(scenario)
        runs.append(run)
        _print_progress(index, len(scenarios), run)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    args.out.write_text(render_markdown(runs, generated_at), encoding="utf-8")
    print(f"OK: {args.out} ({len(runs)} cenários)")


if __name__ == "__main__":
    main()
