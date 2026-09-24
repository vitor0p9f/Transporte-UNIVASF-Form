"""Menu: pick a scenario + heuristic (heuristics not implemented)."""

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parent

HEURISTICS = ["Nearest neighbor", "Max demand"]


def load_scenarios() -> list[dict]:
    with (ROOT / "scenarios.csv").open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def pick(menu, label):
    for key, text in menu:
        print(f"  [{key}] {text}")
    while True:
        choice = input(f"Pick {label} (number): ").strip()
        if choice in dict(menu):
            return choice
        print("Invalid option, try again.")


def main() -> None:
    scenarios = [s for s in load_scenarios()
                 if (ROOT / "instances" / s["instance_id"] / "distance.csv").exists()]
    print("=== Transport — Experiments ===")
    print("Scenarios:")
    scen_menu = [(str(i + 1),
                  f"Scenario {s['scenario_id']} | instance {s['instance_id']} | "
                  f"fleet [{s['fleet_bus_ids']}] | {s['period']} | limit {s['max_time_limit']} min")
                 for i, s in enumerate(scenarios)]
    scenario = scenarios[int(pick(scen_menu, "the scenario")) - 1]
    print("Heuristics:")
    heur_menu = [(str(i + 1), name) for i, name in enumerate(HEURISTICS)]
    heuristic = HEURISTICS[int(pick(heur_menu, "the heuristic")) - 1]
    print(f"\nSelected: scenario {scenario['scenario_id']} "
          f"(instance {scenario['instance_id']}) + '{heuristic}' heuristic.")


if __name__ == "__main__":
    main()
