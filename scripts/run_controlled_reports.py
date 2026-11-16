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

Each regime runs two heuristics on the same fleet, depot and demand:

* **TOP (custo)** -- scores passengers per real (R$). Maximising pax/R$ is
  equivalent to minimising R$ per passenger; in the insertion stage it
  minimises R$ per extra passenger. Each bus pays fuel with its own km/L plus
  the driver, priced by the scenario;
* **Clarke-Wright** -- the existing savings heuristic.

The depot is the first node of the scenario's ``origin`` column, the same for
both. The cost is recomputed from the final routes with each bus's own km/L
(all the same in the controlled fleet), charging only routes that served
someone.

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
from utils.scenarios import DEFAULT_REPORT_SCENARIOS, parse_node_labels

#: Capacity that stands in for "no capacity restriction at all".
INFINITE_CAPACITY = 10**9

#: Controlled inputs (written by scripts/make_controlled_scenarios.py).
CONTROLLED_SCENARIOS = ("scenarios_control.csv", "scenarios_base_control.csv")
CONTROLLED_FLEET = "fleet_control.csv"
#: Scenarios run by default, in output order.
DEFAULT_SCENARIOS = DEFAULT_REPORT_SCENARIOS

#: Full CW setup for the controlled comparison.
CW_KWARGS: dict = {
    "lam": None,
    "use_two_phase": True,
    "use_post_improvement": True,
    "iterations": 5000,
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


@dataclass(frozen=True)
class Config:
    """One constraint regime and the report it writes."""

    filename: str
    title: str
    ignore_capacity: bool

    @property
    def cw_restricao(self) -> str:
        return "tempo" if self.ignore_capacity else "ambas"


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


def scenario_depot(scenario: dict) -> int | None:
    origins = parse_node_labels(scenario.get("origin"))
    return origins[0] if origins else None


def run_top(scenario: dict, buses) -> tuple:
    """TOP on the controlled scenario, starting at the scenario depot."""
    data, plans, _summary = top_univasf.solve_scenario(
        scenario,
        buses,
        ROOT,
        origin=scenario_depot(scenario),
    )
    return data, plans


def run_cw(scenario: dict, buses, config: Config) -> tuple:
    """Clarke-Wright on the controlled scenario, with the same depot."""
    capacity = (
        INFINITE_CAPACITY
        if config.ignore_capacity
        else min(bus.passenger_capacity for bus in buses)
    )
    data, routes, context, attendance, _lam = clarke_wright.solve_scenario(
        scenario,
        depot=scenario_depot(scenario),
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


def scenario_rows(scenario: dict, config: Config) -> list[tuple[str, ...]]:
    """The two heuristic rows of one scenario, in TOP-custo/CW order."""
    buses = scenario_buses(scenario, config)
    reference = controlled_fleet()
    capacity_reference = reference[0].passenger_capacity
    rows = []
    for heuristic in (TOP_COST, CW):
        data, plans = run_heuristic(scenario, buses, config, heuristic)
        cost = scenario_operational_cost(scenario, data, plans, buses)
        rows.append(
            row_cells(
                scenario,
                heuristic,
                data,
                plans,
                buses,
                capacity_reference,
                cost,
            )
        )
    return rows


def _scenario_rows_indexed(
    item: tuple[int, dict, Config],
) -> tuple[int, list[tuple[str, ...]]]:
    """Picklable worker: rows of one scenario, tagged with its index."""
    index, scenario, config = item
    return index, scenario_rows(scenario, config)


def build_rows(
    config: Config,
    scenarios: list[dict],
    workers: int = 1,
) -> list[tuple[str, ...]]:
    """Every scenario x heuristic row of one configuration, in scenario order."""
    if workers <= 1:
        rows: list[tuple[str, ...]] = []
        for scenario in scenarios:
            rows.extend(scenario_rows(scenario, config))
        return rows

    blocks: dict[int, list[tuple[str, ...]]] = {}
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(_scenario_rows_indexed, (index, scenario, config))
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
    return [row for index in range(len(scenarios)) for row in blocks[index]]


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
        f"de menor capacidade do `fleet.csv` ({fleet_note(root)}). O depósito "
        "é o primeiro nó da coluna `origin` do cenário, o mesmo para as duas "
        "heurísticas, e o Clarke-Wright é limitado ao número de ônibus da "
        "frota.\n\n"
        "O **TOP (custo)** pontua passageiros por real: cada rota paga o "
        "combustível (km / km por litro do ônibus × diesel do cenário) e o "
        "motorista (horas × valor da hora do cenário). Maximizar passageiros "
        "por real é equivalente a minimizar o custo por passageiro; na "
        "inserção de uma parada, o score marginal minimiza o custo por "
        "passageiro extra. O custo mostrado é recalculado por ônibus a partir "
        "das rotas finais, cobrando apenas as rotas que atendem alguém. "
        "O CW é um baseline adaptado: as economias de distância constroem as "
        "rotas, e a seleção prioriza atendimento, com custo operacional como "
        "desempate. A carga estática da fusão soma a demanda OD que toca as "
        "paradas intermediárias, contando cada par uma vez; as âncoras não são "
        "clientes dessa projeção, mas entram na simulação de embarque. "
        "O pipeline é construção → anchoring → corte da frota → CW-3 → "
        "avaliação. A two-phase usa limite superior otimista, não atendimento "
        "exato. As duas heurísticas são avaliadas pela mesma simulação, mesmos "
        "limites, frota homogênea e fórmula de custo (diesel + motorista)."
    )


def render_report(
    config: Config,
    rows: list[tuple[str, ...]],
    generated_at: str,
    *, reproducible: bool = False,
) -> str:
    """Full markdown report: title, date, note and the summary table."""
    lines = [
        f"# {config.title}",
        "",
        'Relatório reprodutível · seed 42.' if reproducible else f"Gerado em {generated_at}.",
        "",
        report_note(config),
        "",
    ]
    lines += reporting.markdown_table(TABLE_HEADER, rows)
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
        rows = build_rows(config, scenarios, workers=args.workers)
        path = args.out_dir / config.filename
        path.write_text(
            render_report(config, rows, generated_at, reproducible=True), encoding="utf-8", newline="\n"
        )
        print(f"OK: {path} ({len(rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
