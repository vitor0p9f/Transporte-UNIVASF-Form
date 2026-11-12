"""Controlled reports: TOP (time) x TOP (cost) x Clarke-Wright.

The controlled scenarios are the copy in ``scenarios_control.csv`` +
``scenarios_base_control.csv``; the fleet is the homogeneous copy in
``fleet_control.csv``: every bus is the smallest-capacity model of ``fleet.csv``
(24 seats and the same fuel autonomy). Two constraint regimes are reported:

``apenas_tempo``
    Only the time limit is enforced. Capacity is switched off in all three
    heuristics: the fleet runs with an "infinite" capacity, so neither the
    decisions nor the boarding simulation reject anyone for lack of room, and
    CW runs with ``restricoes="tempo"``.

``tempo_capacidade``
    Time and capacity are both enforced.

Each regime runs three heuristics on the same fleet, depot and demand:

* **TOP (tempo)** -- the original, scoring passengers per minute;
* **TOP (custo)** -- the same TOP with the cost objective, scoring passengers
  per real (R$).
  Maximising pax/R$ is equivalent to minimising R$ per passenger; in the
  insertion stage it minimises R$ per extra passenger. Each bus pays fuel with
  its own km/L plus the driver, priced by the scenario;
* **Clarke-Wright** -- the existing savings heuristic.

The depot is the first node of the scenario's ``origin`` column, the same for
all three. The cost is recomputed from the final routes with each bus's own
km/L (all the same in the controlled fleet), charging only routes that served
someone.

Outputs:

    resultados_controlados_apenas_tempo.md
    resultados_controlados_tempo_capacidade.md

Usage:
  python scripts/run_controlled_reports.py --workers 8
  python scripts/run_controlled_reports.py --only 65,19,16,32,37 --workers 8
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
from utils.fleet import load_fleet, parse_fleet_ids
from utils.scenarios import (
    DEFAULT_REPORT_SCENARIOS,
    load_scenarios,
    parse_node_labels,
    pick_scenarios,
)

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
    "usar_two_phase": True,
    "usar_postimprove": True,
    "iteracoes": 2000,
    "iter_postimprov": 500,
    "seed": 42,
}

TOP_TIME = "TOP (tempo)"
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


def controlled_scenarios(root: str | Path = ROOT) -> list[dict]:
    """The controlled scenario copy, in file order."""
    return load_scenarios(root, files=CONTROLLED_SCENARIOS)


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
    buses = load_fleet(
        Path(root) / CONTROLLED_FLEET,
        parse_fleet_ids(scenario["fleet_bus_ids"]),
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


def run_top(scenario: dict, buses, objective: str) -> tuple:
    """TOP on the controlled scenario, starting at the scenario depot."""
    data, plans, _summary = top_univasf.solve_scenario(
        scenario,
        buses,
        ROOT,
        origin=scenario_depot(scenario),
        objective=objective,
    )
    return data, plans


def run_cw(scenario: dict, buses, config: Config) -> tuple:
    """Clarke-Wright on the controlled scenario, with the same depot."""
    capacity = (
        INFINITE_CAPACITY
        if config.ignore_capacity
        else min(bus.passenger_capacity for bus in buses)
    )
    data, routes, context, attendance, _lam = clarke_wright.resolver_cenario(
        scenario,
        deposito=scenario_depot(scenario),
        restricoes=config.cw_restricao,
        capacidade=capacity,
        max_rotas=len(buses),
        **CW_KWARGS,
    )
    plans, _summary = clarke_wright.planos_e_resumo(
        routes, context, attendance, buses
    )
    return data, plans


def run_heuristic(
    scenario: dict, buses, config: Config, heuristic: str
) -> tuple:
    if heuristic == TOP_TIME:
        return run_top(scenario, buses, "time")
    if heuristic == TOP_COST:
        return run_top(scenario, buses, "cost")
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
    served, total, _percentage = reporting.served_ratio(data, plans)
    used = sum(1 for plan in plans if plan.served_passengers > 0)
    reference = reporting.reference_plan(plans)
    longest = reference.travel_time_minutes if reference else 0
    peak = reference.peak_load if reference else 0
    limit = scenario.get("max_time_limit")
    time_cell = f"{longest}/{int(limit)}" if limit else str(longest)
    return (
        str(scenario["scenario_id"]),
        str(scenario["instance_id"]),
        str(scenario["period"]),
        heuristic,
        f"{served}/{total}",
        f"{used}/{len(buses)}",
        time_cell,
        f"{peak}/{capacity_reference}",
        f"{cost.diesel_price:.2f}",
        f"{cost.driver_hourly_rate:.2f}",
        f"{cost.total:.2f}",
        f"{cost.per_passenger(served):.2f}",
    )


def scenario_rows(scenario: dict, config: Config) -> list[tuple[str, ...]]:
    """The three heuristic rows of one scenario, in TOP-tempo/TOP-custo/CW order."""
    buses = scenario_buses(scenario, config)
    reference = controlled_fleet()
    capacity_reference = reference[0].passenger_capacity
    rows = []
    for heuristic in (TOP_TIME, TOP_COST, CW):
        data, plans = run_heuristic(scenario, buses, config, heuristic)
        cost = reporting.operational_cost_per_bus(
            plans,
            data,
            buses,
            diesel_price=float(scenario["diesel_price_per_liter"]),
            driver_hourly_rate=float(scenario["driver_hourly_rate"]),
        )
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
            "nas decisões e na avaliação das três heurísticas (frota com "
            "capacidade infinita)."
        )
    else:
        regime = (
            "As restrições de tempo e de capacidade estão ativas nas três "
            "heurísticas."
        )
    return (
        f"{regime} Os cenários são a cópia controlada "
        "(`scenarios_control.csv` + `scenarios_base_control.csv`) e a frota é "
        f"a homogênea de `{CONTROLLED_FLEET}`: todos os ônibus são o modelo "
        f"de menor capacidade do `fleet.csv` ({fleet_note(root)}). O depósito "
        "é o primeiro nó da coluna `origin` do cenário, o mesmo para as três "
        "heurísticas, e o Clarke-Wright é limitado ao número de ônibus da "
        "frota.\n\n"
        "O **TOP (tempo)** pontua passageiros por minuto. O **TOP (custo)** "
        "pontua passageiros por real: cada rota paga o combustível (km / km "
        "por litro do ônibus × diesel do cenário) e o motorista (horas × valor "
        "da hora do cenário). Maximizar passageiros por real é equivalente a "
        "minimizar o custo por passageiro; na inserção de uma parada, o score "
        "marginal minimiza o custo por passageiro extra. O custo mostrado é "
        "recalculado por ônibus a partir das rotas finais, cobrando apenas as "
        "rotas que atendem alguém."
    )


def render_report(
    config: Config,
    rows: list[tuple[str, ...]],
    generated_at: str,
) -> str:
    """Full markdown report: title, date, note and the summary table."""
    lines = [
        f"# {config.title}",
        "",
        f"Gerado em {generated_at}.",
        "",
        report_note(config),
        "",
        "| " + " | ".join(TABLE_HEADER) + " |",
        "|" + "---|" * len(TABLE_HEADER),
    ]
    lines += ["| " + " | ".join(cells) + " |" for cells in rows]
    return "\n".join(lines) + "\n\n"


def select_scenarios(
    ids: tuple[str, ...] | None = None, root: str | Path = ROOT
) -> list[dict]:
    """The controlled scenarios in requested order (default: 5 report scenarios)."""
    return pick_scenarios(controlled_scenarios(root), ids or DEFAULT_SCENARIOS)


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
    parser.add_argument(
        "--only",
        default=None,
        help=(
            "comma-separated scenario ids "
            f"(default: {','.join(DEFAULT_SCENARIOS)})"
        ),
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT,
        help="directory for the reports (default: project root)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ids = (
        tuple(item.strip() for item in args.only.split(",") if item.strip())
        if args.only
        else None
    )
    scenarios = select_scenarios(ids)
    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    for config in CONFIGS.values():
        print(f"== {config.filename} ({len(scenarios)} cenários)", flush=True)
        rows = build_rows(config, scenarios, workers=args.workers)
        path = args.out_dir / config.filename
        path.write_text(
            render_report(config, rows, generated_at), encoding="utf-8"
        )
        print(f"OK: {path} ({len(rows)} rows)", flush=True)


if __name__ == "__main__":
    main()
