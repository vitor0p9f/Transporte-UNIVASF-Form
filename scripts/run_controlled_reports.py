"""Controlled reports: TOP (cost) x Clarke-Wright.

The controlled scenarios are the copy in ``scenarios_control.csv`` +
``scenarios_base_control.csv``; the fleet is the homogeneous copy in
``fleet_control.csv``: every bus is the smallest-capacity model of ``fleet.csv``
(24 seats and the same fuel autonomy). Two constraint regimes are reported:

``apenas_tempo``
    Only the time limit is enforced. Capacity is switched off in both
    heuristics: the fleet runs with an "infinite" capacity, so neither the
    decisions nor the boarding simulation reject anyone for lack of room, and
    CW runs with ``restricoes="tempo"``.

``tempo_capacidade``
    Time and capacity are both enforced.

Each regime runs two heuristics on the same fleet, allowed endpoints and demand:

* **TOP (custo)** -- scores passengers per real (R$). Maximising pax/R$ is
  equivalent to minimising R$ per passenger; in the insertion stage it
  minimises R$ per extra passenger. Each bus pays fuel with its own km/L plus
  the driver, priced by the scenario;
* **Clarke-Wright** -- the existing savings heuristic.

Both heuristics read the allowed endpoints from the scenario: any node of the
``origin`` column may start a route, and ``destination_labels`` constrains the
terminal node. The cost is recomputed from the final routes with each bus's
own km/L (all the same in the controlled fleet), charging only routes that
served someone.

Outputs:

    resultados_controlados_apenas_tempo.md
    resultados_controlados_tempo_capacidade.md

Usage:
  python scripts/run_controlled_reports.py --workers 8
  python scripts/run_controlled_reports.py --only 16,19,32,65,69 --workers 8
  python scripts/run_controlled_reports.py --only 1,2,3 --workers 8
"""

import argparse
import dataclasses
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import reporting
from algorithms import clarke_wright, top_univasf
from scripts import report_common
from scripts.report_common import (
    add_only_argument,
    parse_scenario_ids,
    scenario_operational_cost,
)
from utils.fleet import load_fleet
from utils.scenarios import DEFAULT_REPORT_SCENARIOS

#: Capacity that stands in for "no capacity restriction at all".
INFINITE_CAPACITY = 10**9

#: Controlled inputs (written by scripts/make_controlled_scenarios.py).
CONTROLLED_SCENARIOS = ("scenarios_control.csv", "scenarios_base_control.csv")
CONTROLLED_FLEET = "fleet_control.csv"
#: Scenarios run by default, in output order.
DEFAULT_SCENARIOS = DEFAULT_REPORT_SCENARIOS

#: Full CW setup for the controlled comparison: the paper's parameters.
CW_KWARGS: dict = {
    "lam": None,
    "use_two_phase": True,
    "use_post_improvement": True,
    "iterations": clarke_wright.ITER_TWO_PHASE,
    "post_improvement_iterations": 500,
    "seed": 42,
}

TOP_COST = "TOP (custo)"
CW = "Clarke-Wright"

#: Header of the summary table, in the same order as `row_cells`.
TABLE_HEADER = (
    "Cenário",
    "Instância",
    "Período",
    "Heurística",
    "Passageiros atendidos / Total",
    "Ônibus usados / Frota",
    "Maior rota / Limite (min)",
    "Pico / Capacidade de referência",
    "Diesel (R$/L)",
    "Motorista (R$/h)",
    "Custo operacional (R$)",
    "Custo por passageiro (R$)",
)

OCCUPANCY_HEADER = (
    "Cenário",
    "Heurística",
    "Pico global / Capacidade física",
    "Ônibus do pico",
    "Rota do pico",
    "Rotas acima da capacidade",
    "Maior excedente",
    "Ônibus/rota do maior excedente",
)


@dataclass(frozen=True)
class Config:
    """One constraint regime and the report it writes."""

    filename: str
    title: str
    ignore_capacity: bool

    @property
    def cw_restricao(self) -> str:
        return "tempo" if self.ignore_capacity else "ambas"


@dataclass(frozen=True)
class ControlledResult:
    """One existing report row plus its complementary occupancy audit."""

    row: tuple[str, ...]
    audit_row: tuple[str, ...]


CONFIGS = {
    "apenas_tempo": Config(
        filename="resultados_controlados_apenas_tempo.md",
        title="Resultados controlados — Apenas Restrição Temporal",
        ignore_capacity=True,
    ),
    "tempo_capacidade": Config(
        filename="resultados_controlados_tempo_capacidade.md",
        title="Resultados controlados — Tempo e Capacidade",
        ignore_capacity=False,
    ),
}


def controlled_fleet(root: str | Path = ROOT) -> list:
    """The whole controlled fleet, validating that it is homogeneous."""
    buses = load_fleet(Path(root) / CONTROLLED_FLEET)
    capacities = {bus.passenger_capacity for bus in buses}
    autonomies = {bus.km_autonomy_per_liter for bus in buses}
    if len(capacities) != 1 or len(autonomies) != 1:
        raise ValueError(
            f"{CONTROLLED_FLEET} is not homogeneous: "
            f"capacities={capacities}, autonomies={autonomies}"
        )
    return buses


def scenario_buses(scenario: dict, config: Config, root: str | Path = ROOT) -> list:
    """The scenario's buses from the controlled fleet, capacity off if asked."""
    buses = report_common.scenario_buses(
        scenario, root, fleet=CONTROLLED_FLEET
    )
    if config.ignore_capacity:
        buses = [
            dataclasses.replace(bus, passenger_capacity=INFINITE_CAPACITY)
            for bus in buses
        ]
    return buses


def run_top(scenario: dict, buses) -> tuple:
    """TOP on the controlled scenario, using the scenario's allowed endpoints.

    No `origin`/`depot` override: the draft chooses the OD pair among the
    scenario's `origin` and `destination_labels` columns.
    """
    data, plans, _summary = top_univasf.solve_scenario(
        scenario,
        buses,
        ROOT,
    )
    return data, plans


def run_cw(scenario: dict, buses, config: Config) -> tuple:
    """Clarke-Wright on the controlled scenario, with the same endpoints."""
    capacity = (
        INFINITE_CAPACITY
        if config.ignore_capacity
        else min(bus.passenger_capacity for bus in buses)
    )
    data, routes, context, attendance, _lam = clarke_wright.solve_scenario(
        scenario,
        restrictions=config.cw_restricao,
        capacity=capacity,
        max_routes=len(buses),
        **CW_KWARGS,
    )
    plans, _summary = clarke_wright.plans_and_summary(
        routes, context, attendance, buses
    )
    return data, plans


def run_heuristic(
    scenario: dict, buses, config: Config, heuristic: str
) -> tuple:
    if heuristic == TOP_COST:
        return run_top(scenario, buses)
    if heuristic == CW:
        return run_cw(scenario, buses, config)
    raise ValueError(f"unknown heuristic: {heuristic}")


def row_cells(
    scenario: dict,
    heuristic: str,
    data,
    plans,
    buses,
    capacity_reference: int,
    cost: reporting.OperationalCost,
) -> tuple[str, ...]:
    """One table row, in `TABLE_HEADER` order."""
    metrics = reporting.run_metrics(scenario, data, plans, buses)
    time_cell = (
        f"{metrics.longest}/{metrics.limit}"
        if metrics.limit
        else str(metrics.longest)
    )
    return (
        str(scenario["scenario_id"]),
        str(scenario["instance_id"]),
        str(scenario["period"]),
        heuristic,
        f"{metrics.served}/{metrics.total}",
        f"{metrics.used}/{len(buses)}",
        time_cell,
        f"{metrics.peak}/{capacity_reference}",
        f"{cost.diesel_price:.2f}",
        f"{cost.driver_hourly_rate:.2f}",
        f"{cost.total:.2f}",
        f"{cost.per_passenger(metrics.served):.2f}",
    )


def occupancy_cells(
    scenario: dict,
    heuristic: str,
    audit: reporting.OccupancyAudit,
) -> tuple[str, ...]:
    """One complementary global-occupancy row."""
    peak_bus = str(audit.bus_id) if audit.bus_id is not None else "—"
    worst = (
        f"{audit.max_excess_bus_id}: {reporting.stops_text(audit.max_excess_route)}"
        if audit.max_excess_bus_id is not None
        else "—"
    )
    return (
        str(scenario["scenario_id"]),
        heuristic,
        f"{audit.peak}/{audit.capacity}",
        peak_bus,
        reporting.stops_text(audit.route),
        str(audit.violating_routes),
        str(audit.max_excess),
        worst,
    )


def scenario_results(scenario: dict, config: Config) -> list[ControlledResult]:
    """Both heuristic rows and audits, in TOP-custo/CW order."""
    buses = scenario_buses(scenario, config)
    physical_buses = report_common.scenario_buses(
        scenario, ROOT, fleet=CONTROLLED_FLEET
    )
    capacity_reference = physical_buses[0].passenger_capacity
    results = []
    for heuristic in (TOP_COST, CW):
        data, plans = run_heuristic(scenario, buses, config, heuristic)
        cost = scenario_operational_cost(scenario, data, plans, buses)
        audit = reporting.occupancy_audit(plans, physical_buses)
        results.append(
            ControlledResult(
                row=row_cells(
                    scenario,
                    heuristic,
                    data,
                    plans,
                    buses,
                    capacity_reference,
                    cost,
                ),
                audit_row=occupancy_cells(scenario, heuristic, audit),
            )
        )
    return results


def scenario_rows(scenario: dict, config: Config) -> list[tuple[str, ...]]:
    """The two legacy indicator rows, kept as a stable public helper."""
    return [result.row for result in scenario_results(scenario, config)]


def _scenario_results_indexed(
    item: tuple[int, dict, Config],
) -> tuple[int, list[ControlledResult]]:
    """Picklable worker: results of one scenario, tagged with its index."""
    index, scenario, config = item
    return index, scenario_results(scenario, config)


def build_results(
    config: Config,
    scenarios: list[dict],
    workers: int = 1,
) -> list[ControlledResult]:
    """Every scenario x heuristic result, preserving scenario order."""
    if workers <= 1:
        results: list[ControlledResult] = []
        for scenario in scenarios:
            results.extend(scenario_results(scenario, config))
        return results

    blocks: dict[int, list[ControlledResult]] = {}
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_scenario_results_indexed, (index, scenario, config))
            for index, scenario in enumerate(scenarios)
        ]
        for done, future in enumerate(as_completed(futures), start=1):
            index, block = future.result()
            blocks[index] = block
            print(
                f"  [{done}/{len(scenarios)}] cenário "
                f"{scenarios[index]['scenario_id']}",
                flush=True,
            )
    return [result for index in range(len(scenarios)) for result in blocks[index]]


def build_rows(
    config: Config,
    scenarios: list[dict],
    workers: int = 1,
) -> list[tuple[str, ...]]:
    """Every legacy indicator row, preserving the existing helper contract."""
    return [result.row for result in build_results(config, scenarios, workers)]


def fleet_note(root: str | Path = ROOT) -> str:
    """Human-readable description of the controlled reference model."""
    reference = controlled_fleet(root)[0]
    return (
        f"{reference.passenger_capacity} lugares e "
        f"{reference.km_autonomy_per_liter:.2f} km/L"
    )


def report_note(config: Config, root: str | Path = ROOT) -> str:
    """Configuration note shown before the table."""
    if config.ignore_capacity:
        regime = (
            "Apenas o limite de tempo está ativo: a capacidade foi desativada "
            "nas decisões e na avaliação das duas heurísticas (frota com "
            "capacidade infinita)."
        )
    else:
        regime = (
            "As restrições de tempo e de capacidade estão ativas nas duas "
            "heurísticas."
        )
    return (
        f"{regime} Os cenários são a cópia controlada "
        "(`scenarios_control.csv` + `scenarios_base_control.csv`) e a frota é "
        f"a homogênea de `{CONTROLLED_FLEET}`: todos os ônibus são o modelo "
        f"de menor capacidade do `fleet.csv` ({fleet_note(root)}). As origens e "
        "os destinos permitidos vêm das colunas `origin` e "
        "`destination_labels` do cenário, as mesmas para as duas heurísticas, "
        "e o Clarke-Wright é limitado ao número de ônibus da frota.\n\n"
        "O **TOP (custo)** pontua passageiros por real: cada rota paga o "
        "combustível (km / km por litro do ônibus × diesel do cenário) e o "
        "motorista (horas × valor da hora do cenário). Maximizar passageiros "
        "por real é equivalente a minimizar o custo por passageiro; na "
        "inserção de uma parada, o score marginal minimiza o custo por "
        "passageiro extra. O custo mostrado é recalculado por ônibus a partir "
        "das rotas finais, cobrando apenas as rotas que atendem alguém.\n\n"
        "O **Clarke-Wright** usa esse mesmo custo operacional (combustível + "
        "motorista) no cálculo das economias, na escolha de direção e "
        "terminais, na seleção por lambda e nas melhorias locais. Assim, o "
        "critério que constrói as rotas coincide com o custo exibido na tabela."
    )


def render_report(
    config: Config,
    rows: list[tuple[str, ...]],
    generated_at: str,
    occupancy_rows: list[tuple[str, ...]] | None = None,
) -> str:
    """Full report with the unchanged indicators and a complementary audit."""
    lines = [
        f"# {config.title}",
        "",
        f"Gerado em {generated_at}.",
        "",
        report_note(config),
        "",
    ]
    lines += reporting.markdown_table(TABLE_HEADER, rows)
    if occupancy_rows is not None:
        lines += [
            "",
            "## Verificação global de ocupação",
            "",
            (
                "Esta tabela é complementar. O indicador `Pico / Capacidade de "
                "referência` acima continua associado à rota mais longa; aqui "
                "o pico simultâneo é procurado em todas as rotas e comparado "
                "com a capacidade física original do ônibus."
            ),
            "",
        ]
        lines += reporting.markdown_table(OCCUPANCY_HEADER, occupancy_rows)
    return "\n".join(lines) + "\n\n"


def select_scenarios(
    ids: tuple[str, ...] | None = None, root: str | Path = ROOT
) -> list[dict]:
    """The controlled scenarios in requested order (default: 5 report scenarios)."""
    return report_common.select_scenarios(
        ids or DEFAULT_SCENARIOS,
        root,
        files=CONTROLLED_SCENARIOS,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help=(
            "parallel scenario workers (default: 1; the full CW takes ~20 s "
            "per scenario, so use 8 for the full run)"
        ),
    )
    add_only_argument(parser, DEFAULT_SCENARIOS)
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT,
        help="directory for the reports (default: project root)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ids = parse_scenario_ids(args.only, DEFAULT_SCENARIOS)
    scenarios = select_scenarios(ids)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for config in CONFIGS.values():
        print(f"== {config.filename} ({len(scenarios)} cenários)", flush=True)
        results = build_results(config, scenarios, workers=args.workers)
        rows = [result.row for result in results]
        occupancy_rows = [result.audit_row for result in results]
        path = args.out_dir / config.filename
        path.write_text(
            render_report(config, rows, generated_at, occupancy_rows),
            encoding="utf-8",
        )
        print(f"OK: {path} ({len(rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
