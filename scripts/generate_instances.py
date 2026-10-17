"""Gerador de instâncias sintéticas (distância, tempo e demanda).

Duas formas, ambas reprodutíveis pela seed raiz (``utils/seed.py``):

    synth (padrão)
        Gera do zero, com valores aleatórios: n nós sorteados num box de
        ~13 km, distância euclidiana, tempo = distância * ~2.2 min/km com
        ruído U(0.9, 1.1) e demanda = ~0.2865 * n*(n-1) viagens espalhadas
        em (origem, destino != origem, sub-período).
    perturb
        Perturba ``instances/base``: distância/tempo * U(0.9, 1.1) e
        demanda * U(0.8, 1.2).

Grava ``instances/i001..i00N`` (reescrevendo os que já existirem, então rodar
de novo com a mesma seed é idempotente) e atualiza as linhas correspondentes
em ``instances/index.csv``. Instâncias ``i00N+k`` de execuções anteriores não
são removidas — só as N primeiras são reescritas.

Obs.: o experimento atual usa apenas as instâncias ``base`` + arqueti
(``p1_*``); rodar este gerador cria instâncias sintéticas à parte, que
passam a ser sorteadas por ``generate_scenarios.py``.

Usage:
  python scripts/generate_instances.py --num-instances 5 --seed 42
"""
import argparse
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.demand import DEMAND_PERIODS
from utils.seed import DEFAULT_SEED
from utils.synth import (
    DEFAULT_DEMAND_RATIO,
    DEFAULT_MIN_PER_UNIT,
    DEFAULT_PAIR_RATIO,
    DEFAULT_SPAN_KM,
    build_demand,
    build_distance,
    build_time,
    demand_budget,
    integer_cell,
    random_points,
    summarize_demand,
    write_demand,
    write_square,
)

INDEX_FIELDS = [
    "instance_id",
    "path",
    "seed",
    "kind",
    "num_nodes",
    "num_od_pairs",
    "total_demand",
]


def read_base(base: Path):
    """Lê o triplo do base uma única vez (usado no modo perturb)."""
    nodes: list[int] | None = None
    values = {}
    for name in ("distance.csv", "time.csv"):
        with (base / name).open(newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            if nodes is None:
                nodes = [int(cell) for cell in header[1:]]
            values[name] = [[float(cell) for cell in row[1:]] for row in reader]
    with (base / "demand.csv").open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    return nodes, values["distance.csv"], values["time.csv"], rows


def perturb_values(values, rng: random.Random, low: float, high: float, fmt):
    """Perturba uma matriz (diagonal e zeros preservados)."""
    out = []
    for i, row in enumerate(values):
        out_row = []
        for j, value in enumerate(row):
            if i == j or value == 0:
                out_row.append(0)
                continue
            out_row.append(fmt(value * rng.uniform(low, high)))
        out.append(out_row)
    return out


def perturb_demand(rows, rng: random.Random):
    """Perturba as contagens de demanda (zeros continuam zero)."""
    out = []
    for row in rows:
        new_row = dict(row)
        for period in DEMAND_PERIODS:
            value = int(row[period])
            if value == 0:
                new_row[period] = 0
            else:
                new_row[period] = max(0, int(round(value * rng.uniform(0.8, 1.2))))
        out.append(new_row)
    return out


def instance_ids(num_instances: int) -> list[str]:
    """Ids determinísticos i001..i00N (reexecutar com a mesma seed reescreve)."""
    return [f"i{k:03d}" for k in range(1, num_instances + 1)]


def update_index(index_path: Path, new_rows: list[dict]) -> None:
    """Substitui (ou acrescenta) linhas por instance_id, preservando a ordem."""
    rows = []
    if index_path.exists():
        with index_path.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    by_id = {row["instance_id"]: row for row in rows}
    order = [row["instance_id"] for row in rows]
    for row in new_rows:
        if row["instance_id"] not in by_id:
            order.append(row["instance_id"])
        by_id[row["instance_id"]] = row
    with index_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=INDEX_FIELDS)
        writer.writeheader()
        for item in order:
            writer.writerow(by_id[item])


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Gera instâncias sintéticas.")
    parser.add_argument(
        "--num-instances", type=int, default=5, help="Número de instâncias a gerar."
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help="Seed raiz (utils/seed.py)."
    )
    parser.add_argument(
        "--mode",
        choices=("synth", "perturb"),
        default="synth",
        help="synth: gera do zero; perturb: perturba instances/base (padrão: synth).",
    )
    parser.add_argument("--num-nodes", type=int, default=46, help="Nós por instância (synth).")
    parser.add_argument("--span-km", type=float, default=DEFAULT_SPAN_KM, help="Lado do box em km.")
    parser.add_argument(
        "--min-per-unit",
        type=float,
        default=DEFAULT_MIN_PER_UNIT,
        help="Minutos por km no tempo de viagem.",
    )
    parser.add_argument(
        "--demand-ratio",
        type=float,
        default=DEFAULT_DEMAND_RATIO,
        help="Viagens por par de nós no total dos 6 sub-períodos.",
    )
    parser.add_argument(
        "--pair-ratio",
        type=float,
        default=DEFAULT_PAIR_RATIO,
        help="Fração dos pares OD que concentram a demanda (base: 11%%).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.num_instances <= 0:
        raise ValueError("--num-instances must be > 0")
    if args.mode == "synth" and args.num_nodes <= 0:
        raise ValueError("--num-nodes must be > 0")

    instances_dir = ROOT / "instances"
    ids = instance_ids(args.num_instances)
    rng = random.Random(args.seed)
    base = read_base(instances_dir / "base") if args.mode == "perturb" else None

    index_rows = []
    for instance_id in ids:
        seed = rng.randint(0, 2**31 - 1)
        irng = random.Random(seed)
        out_dir = instances_dir / instance_id

        if args.mode == "synth":
            nodes = list(range(1, args.num_nodes + 1))
            distance = build_distance(random_points(len(nodes), irng, args.span_km))
            time = build_time(distance, irng, args.min_per_unit)
            demand_rows = build_demand(
                nodes,
                demand_budget(len(nodes), args.demand_ratio),
                irng,
                pair_ratio=args.pair_ratio,
            )
            write_square(out_dir / "distance.csv", nodes, distance)
            write_square(out_dir / "time.csv", nodes, time, integer_cell)
            write_demand(out_dir / "demand.csv", demand_rows)
            meta = {
                "instance_id": instance_id,
                "kind": "synthetic",
                "seed": seed,
                "source": "utils.synth (pontos, distância, tempo, demanda)",
                "generator": {
                    "num_nodes": len(nodes),
                    "span_km": args.span_km,
                    "min_per_unit": args.min_per_unit,
                    "demand_ratio": args.demand_ratio,
                    "pair_ratio": args.pair_ratio,
                },
            }
            kind = "synthetic"
        else:
            base_nodes, base_distance, base_time, base_demand = base
            nodes = base_nodes
            distance = perturb_values(base_distance, irng, 0.9, 1.1, lambda v: round(v, 2))
            time = perturb_values(base_time, irng, 0.9, 1.1, lambda v: max(1, int(round(v))))
            demand_rows = perturb_demand(base_demand, irng)
            write_square(out_dir / "distance.csv", nodes, distance)
            write_square(out_dir / "time.csv", nodes, time, integer_cell)
            write_demand(out_dir / "demand.csv", demand_rows)
            meta = {
                "instance_id": instance_id,
                "kind": "perturbed",
                "seed": seed,
                "base": "instances/base",
                "perturbation": {
                    "distance_factor": [0.9, 1.1],
                    "time_factor": [0.9, 1.1],
                    "demand_factor": [0.8, 1.2],
                },
            }
            kind = "perturbed"

        pairs, total = summarize_demand(demand_rows)
        meta.update(
            {"num_nodes": len(nodes), "num_od_pairs": pairs, "total_demand": total}
        )
        (out_dir / "meta.json").write_text(
            json.dumps(meta, indent=2), encoding="utf-8"
        )
        index_rows.append({
            "instance_id": instance_id,
            "path": f"instances/{instance_id}",
            "seed": seed,
            "kind": kind,
            "num_nodes": len(nodes),
            "num_od_pairs": pairs,
            "total_demand": total,
        })

    update_index(instances_dir / "index.csv", index_rows)
    print(
        f"Wrote {len(ids)} {args.mode} instances (seed {args.seed}): {', '.join(ids)}"
    )


if __name__ == "__main__":
    main()
