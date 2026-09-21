"""Random scenarios generator.

Generates scenarios.csv with columns:
  scenario_id,instance_id,fleet_bus_ids,max_time_limit,diesel_price_per_liter,driver_hourly_rate

fleet_bus_ids is a ";"-separated subset of the ids in fleet.csv.
instance_id references instances/index.csv.

Usage:
  python generate_scenarios.py --num-scenarios 10 --seed 42
"""
import argparse
import csv
import random
from pathlib import Path


def read_fleet_ids(fleet_path: Path) -> list[int]:
    with fleet_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [int(row["id"]) for row in reader]


def read_instance_ids(index_path: Path) -> list[str]:
    with index_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [row["instance_id"] for row in reader]


def generate_scenarios(
    num_scenarios: int,
    fleet_ids: list[int],
    instance_ids: list[str],
    seed: int | None,
) -> list[dict]:
    rng = random.Random(seed)
    n = len(fleet_ids)
    low = max(1, min(3, n))
    scenarios = []
    for scenario_id in range(1, num_scenarios + 1):
        k = rng.randint(low, n)
        subset = sorted(rng.sample(fleet_ids, k))
        scenarios.append({
            "scenario_id": scenario_id,
            "instance_id": rng.choice(instance_ids),
            "fleet_bus_ids": ";".join(str(i) for i in subset),
            "max_time_limit": rng.randint(60, 120),
            "diesel_price_per_liter": round(rng.uniform(5.0, 7.0), 2),
            "driver_hourly_rate": round(rng.uniform(20.0, 35.0), 2),
        })
    return scenarios


def write_scenarios(scenarios: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "scenario_id",
                "instance_id",
                "fleet_bus_ids",
                "max_time_limit",
                "diesel_price_per_liter",
                "driver_hourly_rate",
            ],
        )
        writer.writeheader()
        writer.writerows(scenarios)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate random scenarios.")
    parser.add_argument(
        "--num-scenarios", type=int, default=10, help="Number of scenarios to generate."
    )
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.num_scenarios <= 0:
        raise ValueError("--num-scenarios must be > 0")
    root = Path(__file__).resolve().parent.parent
    fleet_ids = read_fleet_ids(root / "fleet.csv")
    if not fleet_ids:
        raise ValueError("fleet.csv has no buses")
    instance_ids = read_instance_ids(root / "instances" / "index.csv")
    if not instance_ids:
        raise ValueError("instances/index.csv has no instances")
    scenarios = generate_scenarios(
        args.num_scenarios, fleet_ids, instance_ids, args.seed
    )
    output = root / "scenarios.csv"
    write_scenarios(scenarios, output)
    print(f"Wrote {len(scenarios)} scenarios to {output}")


if __name__ == "__main__":
    main()
