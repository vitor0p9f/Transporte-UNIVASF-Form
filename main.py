"""Menu: pick a scenario + heuristic and run it."""

import time
from pathlib import Path

from algorithms.top_univasf import solve_scenario
from utils.fleet import load_fleet, parse_fleet_ids
from utils.scenarios import load_scenarios

ROOT = Path(__file__).resolve().parent

HEURISTICS = ["Greedy OD (trava par OD; sem conflito comitta junto, senão maior score)"]


def pick(menu, label):
    for key, text in menu:
        print(f"  [{key}] {text}")
    while True:
        choice = input(f"Pick {label} (number): ").strip()
        if choice in dict(menu):
            return choice
        print("Invalid option, try again.")


def print_results_table(scenario: dict, data, plans: list, summary, buses: list, elapsed: float) -> None:
    from collections import Counter

    total = int(data.demand.sum())
    served = sum(plan.served_passengers for plan in plans)
    pct = 100.0 * served / total if total else 0.0
    print(f"\n=== Results ({elapsed:.1f}s, {summary.rounds} rodadas) ===")
    print("pax = atendidos · tempo = usado/limite (min) · pico = lotação máx · pax/min = eficiência")
    header = ("bus", "paradas", "pax", "tempo", "pico", "pax/min", "origem", "destino")
    rows = []
    for plan in plans:
        rows.append((
            str(plan.bus_id),
            str(len(plan.stops)),
            str(plan.served_passengers),
            f"{plan.travel_time_minutes}/{scenario['max_time_limit']}",
            f"{plan.peak_load}",
            f"{plan.score:.2f}",
            str(plan.stops[0]),
            str(plan.destination) if plan.destination is not None else "livre",
        ))

    widths = [len(h) for h in header]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*header))
    print(fmt.format(*["-" * w for w in widths]))
    for row in rows:
        print(fmt.format(*row))

    used = len(plans)
    print(f"\nΣ {used} de {len(buses)} ônibus · {served}/{total} pax ({pct:.0f}%)")

    agg: Counter = Counter()
    for plan in plans:
        for o, d, q in plan.served_pairs:
            agg[(o, d)] += q
    if agg:
        top = ", ".join(f"{o}→{d}={q}" for (o, d), q in agg.most_common(5))
        print(f"Pares mais atendidos: {top}")

    idle = [b.id for b in buses if b.id not in {p.bus_id for p in plans}]
    if idle:
        print(f"Ociosos ({len(idle)}): {idle} — sem commit em nenhuma rodada")
    if summary.unserved_pairs:
        top_left = ", ".join(
            f"{o}→{d}={q}" for o, d, q in summary.unserved_pairs[:8]
        )
        extra = (
            f" (+{len(summary.unserved_pairs) - 8} pares)"
            if len(summary.unserved_pairs) > 8
            else ""
        )
        print(f"Não atendidos ({summary.unserved_passengers} pax): {top_left}{extra}")

    print("\nRoutes:")
    for plan in plans:
        official = (
            f"({plan.stops[0]} → {plan.destination})"
            if plan.destination is not None
            else "(terminal livre)"
        )
        print(f"  bus {plan.bus_id} {official}: {' -> '.join(map(str, plan.stops))}")
    if not plans:
        print("  (nenhum ônibus formou rota viável)")


def main() -> None:
    scenarios = load_scenarios(ROOT)
    print("=== Transport — Experiments ===")
    print("Scenarios:")
    scen_menu = [(str(i + 1),
                  f"Scenario {s['scenario_id']} | instance {s['instance_id']} | "
                  f"fleet [{s['fleet_bus_ids']}] | {s['period']} | limit {s['max_time_limit']} min"
                  + (f" | origin {s['origin']}" if s.get("origin") else "")
                  + (f" -> [{s['destination_labels']}]" if s.get("destination_labels") else ""))
                 for i, s in enumerate(scenarios)]
    scenario = scenarios[int(pick(scen_menu, "the scenario")) - 1]
    buses = load_fleet(ROOT / "fleet.csv", parse_fleet_ids(scenario["fleet_bus_ids"]))
    print("Heuristics:")
    heur_menu = [(str(i + 1), name) for i, name in enumerate(HEURISTICS)]
    heuristic = HEURISTICS[int(pick(heur_menu, "the heuristic")) - 1]
    print(f"\nSelected: scenario {scenario['scenario_id']} "
          f"(instance {scenario['instance_id']}) + '{heuristic}' heuristic.")
    print("Fleet:")
    for bus in buses:
        print(f"  Bus {bus.id}: {bus.passenger_capacity} seats, "
              f"{bus.fuel_capacity:g} L tank, {bus.km_autonomy_per_liter} km/L")

    print(f"\nRunning '{heuristic}'...")
    start = time.monotonic()
    data, plans, summary = solve_scenario(scenario, buses, ROOT)
    elapsed = time.monotonic() - start
    print_results_table(scenario, data, plans, summary, buses, elapsed)


if __name__ == "__main__":
    main()
