"""Random distance/time/demand instance generator.

Reads the base triple (instances/base/distance.csv, time.csv, demand.csv)
and writes perturbed copies to instances/i001, i002, ...

Perturbation (per instance, reproducible via seed):
  - distance: each off-diagonal * U(0.9, 1.1), rounded to 2 decimals
  - time: each off-diagonal * U(0.9, 1.1), rounded to nearest int (min 1)
  - demand: each count * U(0.8, 1.2), rounded to int (zeros stay zero)

Usage:
  python generate_instances.py --num-instances 5 --seed 42
"""
import argparse
import csv
import json
import random
from pathlib import Path

DEMAND_PERIODS = [
    "morning_1",
    "morning_2",
    "afternoon_1",
    "afternoon_2",
    "night_1",
    "night_2",
]


def read_matrix(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        rows = list(reader)
    corner, columns = header[0], header[1:]
    index = [row[0] for row in rows]
    values = [[float(x) for x in row[1:]] for row in rows]
    return corner, columns, index, values


def write_matrix(path: Path, corner, columns, index, values, fmt):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([corner] + columns)
        for label, row in zip(index, values):
            writer.writerow([label] + [fmt(v) for v in row])


def perturb_matrix(values, rng, low, high, round_fn, keep_zero=True):
    out = []
    for i, row in enumerate(values):
        out_row = []
        for j, v in enumerate(row):
            if i == j:
                out_row.append(0 if isinstance(v, float) else 0)
                continue
            if keep_zero and v == 0:
                out_row.append(v)
                continue
            out_row.append(round_fn(v * rng.uniform(low, high)))
        out.append(out_row)
    return out


def read_demand(path: Path):
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    return fieldnames, rows


def perturb_demand(rows, rng):
    out = []
    for row in rows:
        new_row = dict(row)
        for p in DEMAND_PERIODS:
            v = int(row[p])
            if v == 0:
                new_row[p] = 0
            else:
                new_row[p] = max(0, int(round(v * rng.uniform(0.8, 1.2))))
        out.append(new_row)
    return out


def write_demand(path: Path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def summarize_demand(rows):
    pairs = len(rows)
    total = sum(int(row[p]) for row in rows for p in DEMAND_PERIODS)
    return pairs, total


def next_instance_ids(instances_dir: Path, n: int):
    existing = {
        p.name
        for p in instances_dir.iterdir()
        if p.is_dir() and p.name.startswith("i") and p.name[1:].isdigit()
    }
    ids = []
    k = 1
    while len(ids) < n:
        candidate = f"i{k:03d}"
        if candidate not in existing:
            ids.append(candidate)
        k += 1
    return ids


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate perturbed test instances.")
    parser.add_argument(
        "--num-instances", type=int, default=5, help="Number of instances to generate."
    )
    parser.add_argument("--seed", type=int, default=None, help="Master seed.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.num_instances <= 0:
        raise ValueError("--num-instances must be > 0")
    rng = random.Random(args.seed)
    root = Path(__file__).resolve().parent.parent
    base = root / "instances" / "base"
    instances_dir = root / "instances"
    instance_ids = next_instance_ids(instances_dir, args.num_instances)

    # Base triple is read once; each instance gets its own derived seed.
    corner_d, cols_d, idx_d, dist = read_matrix(base / "distance.csv")
    corner_t, cols_t, idx_t, time = read_matrix(base / "time.csv")
    demand_fields, demand_rows = read_demand(base / "demand.csv")

    index_path = instances_dir / "index.csv"
    index_exists = index_path.exists()

    with index_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "instance_id",
                "path",
                "seed",
                "kind",
                "num_nodes",
                "num_od_pairs",
                "total_demand",
            ],
        )
        if not index_exists:
            writer.writeheader()
        for instance_id in instance_ids:
            seed = rng.randint(0, 2**31 - 1)
            irng = random.Random(seed)
            new_dist = perturb_matrix(dist, irng, 0.9, 1.1, lambda v: round(v, 2))
            new_time = perturb_matrix(
                time, irng, 0.9, 1.1, lambda v: max(1, int(round(v)))
            )
            new_demand = perturb_demand(demand_rows, irng)
            pairs, total = summarize_demand(new_demand)

            out_dir = instances_dir / instance_id
            write_matrix(
                out_dir / "distance.csv", corner_d, cols_d, idx_d, new_dist, lambda v: v
            )
            write_matrix(
                out_dir / "time.csv", corner_t, cols_t, idx_t, new_time,
                lambda v: int(v) if float(v).is_integer() else v,
            )
            write_demand(out_dir / "demand.csv", demand_fields, new_demand)
            (out_dir / "meta.json").write_text(
                json.dumps(
                    {
                        "instance_id": instance_id,
                        "kind": "perturbed",
                        "seed": seed,
                        "base": "instances/base",
                        "perturbation": {
                            "distance_factor": [0.9, 1.1],
                            "time_factor": [0.9, 1.1],
                            "demand_factor": [0.8, 1.2],
                        },
                        "num_nodes": len(idx_d),
                        "num_od_pairs": pairs,
                        "total_demand": total,
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            writer.writerow({
                "instance_id": instance_id,
                "path": f"instances/{instance_id}",
                "seed": seed,
                "kind": "perturbed",
                "num_nodes": len(idx_d),
                "num_od_pairs": pairs,
                "total_demand": total,
            })
    print(f"Wrote {len(instance_ids)} instances: {', '.join(instance_ids)}")


if __name__ == "__main__":
    main()
