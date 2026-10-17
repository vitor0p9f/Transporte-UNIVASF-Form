"""Archeti TOP (.txt) -> Transporte instance converter.

Reads one Archeti data file (or every ``*.txt`` in a folder) in the format
described by ``readme.txt``::

    n <num_points>
    m <num_vehicles>
    tmax <max_route_duration>
    X Y P   (repeated n times; first/last points are start/end depots)

and writes a Transporte instance triple to ``instances/<id>/``:

    - distance.csv : symmetric euclidean matrix, 2 decimals (km)
    - time.csv     : derived travel time, int (min)
    - demand.csv   : synthetic sparse OD demand over the 6 sub-periods
    - meta.json    : provenance + Archeti parameters

Plus, for each converted file it picks ``k = min(m, len(fleet))`` random
bus ids from the existing ``fleet.csv`` and appends one row to
``scenarios.csv`` with ``max_time_limit = round(tmax * tmax_to_minutes)``.

Conventions (calibrated on ``instances/base``):

    - time  = max(1, round(dist * min_per_unit * U(0.9, 1.1))),
      default min_per_unit = 2.2 (base median time/dist ~= 2.2 min/km).
    - demand budget = sum(P) units, scattered one by one: origin uniform,
      destination weighted by P, sub-period uniform, i != j. This keeps the
      Archeti profit scale while fitting the OD format (base density ~8%).

Usage:
    python convert_archeti.py --input p1.2.a.txt --seed 42
    python convert_archeti.py --input archeti_txt/ --seed 42 --clean
"""

import argparse
import csv
import json
import math
import random
import re
import shutil
from pathlib import Path

DEMAND_PERIODS = [
    "morning_1",
    "morning_2",
    "afternoon_1",
    "afternoon_2",
    "night_1",
    "night_2",
]

INDEX_FIELDS = [
    "instance_id",
    "path",
    "seed",
    "kind",
    "num_nodes",
    "num_od_pairs",
    "total_demand",
]

SCENARIO_FIELDS = [
    "scenario_id",
    "instance_id",
    "fleet_bus_ids",
    "period",
    "max_time_limit",
    "diesel_price_per_liter",
    "driver_hourly_rate",
    # Kept (empty) so rows of scenarios.csv do not drift out of alignment: that
    # file now also carries the possible origins/destinations sampled by
    # generate_scenarios.py.
    "origin",
    "destination_labels",
]


def parse_archeti(path: Path) -> dict:
    lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines()]
    lines = [ln for ln in lines if ln]
    if len(lines) < 4:
        raise ValueError(f"{path}: too few lines for a Archeti file")
    m_n = re.match(r"n\s+(\d+)", lines[0])
    m_m = re.match(r"m\s+(\d+)", lines[1])
    m_t = re.match(r"tmax\s+([0-9.]+)", lines[2])
    if not (m_n and m_m and m_t):
        raise ValueError(f"{path}: header must be 'n ..', 'm ..', 'tmax ..'")
    n, m, tmax = int(m_n.group(1)), int(m_m.group(1)), float(m_t.group(1))
    pts = []
    for ln in lines[3:]:
        parts = ln.replace(",", " ").split()
        if len(parts) != 3:
            raise ValueError(f"{path}: bad point line {ln!r}")
        pts.append((float(parts[0]), float(parts[1]), int(float(parts[2]))))
    if len(pts) != n:
        raise ValueError(f"{path}: header n={n} but found {len(pts)} points")
    return {"n": n, "m": m, "tmax": tmax, "points": pts}


def sanitize_id(stem: str) -> str:
    slug = re.sub(r"[^0-9a-zA-Z]+", "_", stem.strip().lower()).strip("_")
    return slug or "archeti"


def build_distance(points) -> list[list[float]]:
    n = len(points)
    mat = [[0.0] * n for _ in range(n)]
    for i in range(n):
        xi, yi, _ = points[i]
        for j in range(n):
            if i == j:
                continue
            xj, yj, _ = points[j]
            mat[i][j] = round(math.dist((xi, yi), (xj, yj)), 2)
    return mat


def build_time(dist, rng: random.Random, min_per_unit: float) -> list[list[int]]:
    n = len(dist)
    mat = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            mat[i][j] = max(1, round(dist[i][j] * min_per_unit * rng.uniform(0.9, 1.1)))
    return mat


def build_demand(n: int, profits: list[int], rng: random.Random) -> list[dict]:
    """Scatter sum(profits) unit-trips over (origin, destination, period)."""
    counts: dict[tuple[int, int, str], int] = {}
    budget = sum(p for p in profits if p > 0)
    nodes = list(range(1, n + 1))
    for _ in range(budget):
        origin = rng.choice(nodes)
        dest_weights = [
            (profits[j] if (j + 1) != origin and profits[j] > 0 else 0.0)
            for j in range(n)
        ]
        if sum(dest_weights) <= 0:
            cands = [v for v in nodes if v != origin]
            dest = rng.choice(cands)
        else:
            cands = [v for v in nodes if v != origin]
            w = [dest_weights[v - 1] for v in cands]
            dest = rng.choices(cands, weights=w, k=1)[0]
        period = rng.choice(DEMAND_PERIODS)
        counts[(origin, dest, period)] = counts.get((origin, dest, period), 0) + 1
    rows = []
    for o in nodes:
        for d in nodes:
            if o == d:
                continue
            row = {"origin": o, "destination": d}
            for p in DEMAND_PERIODS:
                row[p] = counts.get((o, d, p), 0)
            rows.append(row)
    return rows


def write_square(path: Path, mat, fmt) -> None:
    n = len(mat)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["origin/destination"] + [str(i + 1) for i in range(n)])
        for i, row in enumerate(mat):
            w.writerow([str(i + 1)] + [fmt(v) for v in row])


def write_demand(path: Path, rows) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["origin", "destination"] + DEMAND_PERIODS)
        w.writeheader()
        w.writerows(rows)


def read_fleet_ids(fleet_path: Path) -> list[int]:
    with fleet_path.open(newline="", encoding="utf-8") as f:
        return [int(r["id"]) for r in csv.DictReader(f)]


def next_scenario_id(scen_path: Path) -> int:
    if not scen_path.exists():
        return 1
    with scen_path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    ids = [int(r["scenario_id"]) for r in rows if r.get("scenario_id")]
    return (max(ids) + 1) if ids else 1


def append_index(index_path: Path, row: dict) -> None:
    exists = index_path.exists()
    current = []
    if exists:
        with index_path.open(newline="", encoding="utf-8") as f:
            current = list(csv.DictReader(f))
    current = [r for r in current if r["instance_id"] != row["instance_id"]]
    current.append(row)
    with index_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        w.writeheader()
        w.writerows(current)


def append_scenario(scen_path: Path, row: dict) -> None:
    exists = scen_path.exists()
    with scen_path.open("a" if exists else "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SCENARIO_FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)


def convert_one(
    txt: Path,
    root: Path,
    rng: random.Random,
    fleet_ids: list[int],
    args,
) -> dict:
    data = parse_archeti(txt)
    n, m, tmax = data["n"], data["m"], data["tmax"]
    points = data["points"]
    profits = [p for _, _, p in points]

    file_seed = rng.randint(0, 2**31 - 1)
    frng = random.Random(file_seed)

    instance_id = sanitize_id(txt.stem)
    out_dir = root / "instances" / instance_id
    if out_dir.exists() and not args.overwrite:
        raise FileExistsError(f"{out_dir} exists (use --overwrite)")
    out_dir.mkdir(parents=True, exist_ok=True)

    dist = build_distance(points)
    time = build_time(dist, frng, args.min_per_unit)
    demand_rows = build_demand(n, profits, frng)
    total_demand = sum(r[p] for r in demand_rows for p in DEMAND_PERIODS)

    write_square(out_dir / "distance.csv", dist, lambda v: v)
    write_square(
        out_dir / "time.csv", time,
        lambda v: int(v) if float(v).is_integer() else v,
    )
    write_demand(out_dir / "demand.csv", demand_rows)
    (out_dir / "meta.json").write_text(
        json.dumps(
            {
                "instance_id": instance_id,
                "kind": "archeti",
                "seed": file_seed,
                "archeti": {"n": n, "m": m, "tmax": tmax, "profit_sum": sum(profits)},
                "conversion": {
                    "min_per_unit": args.min_per_unit,
                    "time_noise": [0.9, 1.1],
                    "tmax_to_minutes": args.tmax_to_minutes,
                    "demand": "sparse OD, budget=sum(P), origin uniform, "
                    "destination weighted by P, period uniform",
                },
                "num_nodes": n,
                "num_od_pairs": n * (n - 1),
                "total_demand": total_demand,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    append_index(root / "instances" / "index.csv", {
        "instance_id": instance_id,
        "path": f"instances/{instance_id}",
        "seed": file_seed,
        "kind": "archeti",
        "num_nodes": n,
        "num_od_pairs": n * (n - 1),
        "total_demand": total_demand,
    })

    k = min(max(m, 1), len(fleet_ids))
    buses = sorted(frng.sample(fleet_ids, k))
    scen_id = next_scenario_id(root / "scenarios.csv")
    scenario = {
        "scenario_id": scen_id,
        "instance_id": instance_id,
        "fleet_bus_ids": ";".join(str(i) for i in buses),
        "period": args.period or frng.choice(DEMAND_PERIODS),
        "max_time_limit": round(tmax * args.tmax_to_minutes),
        "diesel_price_per_liter": round(frng.uniform(5.0, 7.0), 2),
        "driver_hourly_rate": round(frng.uniform(20.0, 35.0), 2),
    }
    append_scenario(root / "scenarios.csv", scenario)
    return {"instance_id": instance_id, "scenario_id": scen_id,
            "buses": buses, "total_demand": total_demand}


def clean_previous(root: Path, instance_ids: set[str]) -> None:
    """Drop stale dirs + index/scenario rows for the ids about to convert."""
    for iid in instance_ids:
        d = root / "instances" / iid
        if d.exists():
            shutil.rmtree(d)
    idx = root / "instances" / "index.csv"
    if idx.exists():
        with idx.open(newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["instance_id"] not in instance_ids]
        with idx.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
            w.writeheader()
            w.writerows(rows)
    sc = root / "scenarios.csv"
    if sc.exists():
        with sc.open(newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r["instance_id"] not in instance_ids]
        with sc.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=SCENARIO_FIELDS)
            w.writeheader()
            w.writerows(rows)


def collect_inputs(inp: Path) -> list[Path]:
    if inp.is_file():
        return [inp]
    files = sorted(inp.glob("*.txt"))
    if not files:
        raise FileNotFoundError(f"no *.txt in {inp}")
    return files


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Convert Archeti TOP .txt files.")
    p.add_argument("--input", required=True,
                   help="Archeti .txt file or folder with *.txt files.")
    p.add_argument("--seed", type=int, default=None)
    p.add_argument("--min-per-unit", type=float, default=2.2,
                   help="Minutes per Archeti distance unit (base median ~= 2.2).")
    p.add_argument("--tmax-to-minutes", type=float, default=60.0,
                   help="tmax (hours) -> max_time_limit (min).")
    p.add_argument("--period", default=None, choices=DEMAND_PERIODS,
                   help="Fix scenario period; default sorts one at random.")
    p.add_argument("--overwrite", action="store_true")
    p.add_argument("--clean", action="store_true",
                   help="Remove previous dirs/index/scenario rows for these ids first.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    root = Path(__file__).resolve().parent.parent
    rng = random.Random(args.seed)
    fleet_ids = read_fleet_ids(root / "fleet.csv")
    if not fleet_ids:
        raise ValueError("fleet.csv has no buses")
    inputs = collect_inputs((root / args.input) if not Path(args.input).is_absolute() else Path(args.input))
    # Allow --input relative to CWD as well.
    if not inputs[0].exists():
        alt = Path(args.input)
        inputs = collect_inputs(alt)
    if args.clean:
        clean_previous(root, {sanitize_id(t.stem) for t in inputs})
    done, skipped = [], []
    for txt in inputs:
        try:
            info = convert_one(txt, root, rng, fleet_ids, args)
            done.append(f"{txt.name} -> {info['instance_id']} "
                        f"(scen {info['scenario_id']}, bus {info['buses']})")
        except ValueError as e:
            skipped.append(f"{txt.name}: {e}")
    print("\n".join(done) if done else "nothing converted")
    if skipped:
        print("skipped:")
        print("\n".join(skipped))


if __name__ == "__main__":
    main()
