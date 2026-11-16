"""Dump one scenario outcome per line as canonical JSON.

The output is the regression fixture used by ``tests/test_golden.py``: it
records every decision the heuristic makes (locked pair, stop sequence,
served pairs, rounds) with no volatile field such as execution time.
Generate it from the code you want to freeze, then diff it after every
refactor step::

    .venv/bin/python scripts/dump_results.py --out tests/fixtures/results_baseline.json
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Imports must follow the sys.path setup above (same pattern as run_all.py).
from algorithms.top_univasf import solve_scenario
from utils.fleet import load_fleet, parse_fleet_ids
from utils.scenarios import load_scenarios

DEFAULT_OUT = ROOT / "tests" / "fixtures" / "results_baseline.json"


def scenario_outcome(scenario: dict, root: str | Path = ROOT) -> dict:
    """Run one scenario and return its outcome as plain JSON-ready data."""
    root = Path(root)
    buses = load_fleet(root / "fleet.csv", parse_fleet_ids(scenario["fleet_bus_ids"]))
    data, plans, summary = solve_scenario(scenario, buses, root)
    return {
        "scenario_id": scenario["scenario_id"],
        "instance_id": scenario["instance_id"],
        "period": scenario["period"],
        "fleet_bus_ids": scenario["fleet_bus_ids"],
        "max_time_limit": int(scenario["max_time_limit"]),
        "total_passengers": int(data.demand.sum()),
        "rounds": summary.rounds,
        "served_passengers": sum(plan.served_passengers for plan in plans),
        "wins_per_bus": [list(item) for item in summary.wins_per_bus],
        "unserved_passengers": summary.unserved_passengers,
        "unserved_pairs": [list(pair) for pair in summary.unserved_pairs],
        "plans": [
            {
                "bus_id": plan.bus_id,
                "stops": list(plan.stops),
                "origin": plan.origin,
                "destination": plan.destination,
                "served_passengers": plan.served_passengers,
                "travel_time_minutes": plan.travel_time_minutes,
                "peak_load": plan.peak_load,
                "served_pairs": [list(pair) for pair in plan.served_pairs],
            }
            for plan in plans
        ],
    }


def build(root: str | Path = ROOT) -> list[dict]:
    """Outcome of every scenario, in ``utils.scenarios.load_scenarios`` order."""
    return [scenario_outcome(scenario, root) for scenario in load_scenarios(root)]


def dumps(payload: list[dict]) -> str:
    """Canonical JSON text: stable order, no volatile fields."""
    return json.dumps(payload, indent=1, ensure_ascii=False) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT, help="Output JSON path.")
    args = parser.parse_args()
    payload = build()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(dumps(payload), encoding="utf-8")
    print(f"OK: {args.out} ({len(payload)} scenarios)")


if __name__ == "__main__":
    main()
