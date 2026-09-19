"""Random fleet generator.

Generates fleet.csv with columns:
  id,passenger_capacity,fuel_capacity,km_autonomy_per_liter

Usage:
  python generate_fleet.py --num-buses 12 --seed 42
"""
import argparse
import csv
import random
from pathlib import Path


DEFAULT_CAPACITIES = [24, 32, 40, 45, 50]


def sample_fuel_capacity(passenger_capacity: int, rng: random.Random) -> int:
    if passenger_capacity <= 24:
        return rng.randint(120, 180)
    if passenger_capacity <= 32:
        return rng.randint(180, 250)
    if passenger_capacity <= 40:
        return rng.randint(220, 300)
    return rng.randint(280, 350)


def sample_autonomy(passenger_capacity: int, rng: random.Random) -> float:
    # Larger buses consume more (lower km/l).
    if passenger_capacity <= 24:
        return round(rng.uniform(3.5, 5.0), 2)
    if passenger_capacity <= 32:
        return round(rng.uniform(3.0, 4.2), 2)
    if passenger_capacity <= 40:
        return round(rng.uniform(2.5, 3.5), 2)
    return round(rng.uniform(2.0, 3.0), 2)


def generate_fleet(num_buses: int, capacities: list[int], seed: int | None) -> list[dict]:
    rng = random.Random(seed)
    fleet = []
    for bus_id in range(1, num_buses + 1):
        cap = rng.choice(capacities)
        fleet.append({
            "id": bus_id,
            "passenger_capacity": cap,
            "fuel_capacity": sample_fuel_capacity(cap, rng),
            "km_autonomy_per_liter": sample_autonomy(cap, rng),
        })
    return fleet


def write_fleet(fleet: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["id", "passenger_capacity", "fuel_capacity", "km_autonomy_per_liter"],
        )
        writer.writeheader()
        writer.writerows(fleet)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a random bus fleet.")
    parser.add_argument("--num-buses", type=int, default=12, help="Number of buses to generate.")
    parser.add_argument("--seed", type=int, default=None, help="Random seed for reproducibility.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.num_buses <= 0:
        raise ValueError("--num-buses must be > 0")
    fleet = generate_fleet(args.num_buses, DEFAULT_CAPACITIES, args.seed)
    output = Path(__file__).resolve().parent.parent / "fleet.csv"
    write_fleet(fleet, output)
    print(f"Wrote {len(fleet)} buses to {output}")


if __name__ == "__main__":
    main()
