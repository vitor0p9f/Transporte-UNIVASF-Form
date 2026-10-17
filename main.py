"""Menu: pick a scenario + heuristic and run it."""

import time
from pathlib import Path

import reporting
from algorithms.top_univasf import solve_scenario
from utils.fleet import load_fleet, parse_fleet_ids
from utils.scenarios import load_scenarios

ROOT = Path(__file__).resolve().parent

HEURISTICS = [
    "Greedy OD (locked OD pair; conflict-free steps commit together, "
    + "otherwise only the highest score acts)"
]


def pick(menu, label):
    for key, text in menu:
        print(f"  [{key}] {text}")
    while True:
        choice = input(f"Pick {label} (number): ").strip()
        if choice in dict(menu):
            return choice
        print("Invalid option, try again.")


def print_results_table(scenario: dict, data, plans: list, summary, buses: list, elapsed: float) -> None:
    print(f"\n=== Results ({elapsed:.1f}s, {summary.rounds} rounds) ===")
    print("pax = served · time = used/limit (min) · peak = highest load · pax/min = efficiency")

    header = reporting.PLAN_HEADERS
    rows = [
        reporting.plan_cells(plan, scenario["max_time_limit"]) for plan in plans
    ]
    widths = [len(cell) for cell in header]
    for row in rows:
        for i, cell in enumerate(row):
            widths[i] = max(widths[i], len(cell))
    fmt = "  ".join(f"{{:<{w}}}" for w in widths)
    print(fmt.format(*header))
    print(fmt.format(*["-" * w for w in widths]))
    for row in rows:
        print(fmt.format(*row))

    print(f"\nΣ {reporting.fleet_totals_line(plans, buses, data)}")

    served_pairs = reporting.served_pairs_line(plans)
    if served_pairs:
        print(served_pairs)
    idle = reporting.idle_bus_ids(buses, plans)
    if idle:
        print(f"Idle ({len(idle)}): {idle} — no commit in any round")
    unserved = reporting.unserved_line(summary)
    if unserved:
        print(unserved)

    print("\nRoutes:")
    for plan in plans:
        print(f"  {reporting.route_line(plan)}")
    if not plans:
        print("  (no bus formed a feasible route)")


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
