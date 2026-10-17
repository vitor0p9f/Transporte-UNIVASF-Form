"""Random scenarios generator.

Generates scenarios.csv with columns:
  scenario_id,instance_id,fleet_bus_ids,period,max_time_limit,diesel_price_per_liter,driver_hourly_rate,origin,destination_labels

fleet_bus_ids is a ";"-separated subset of the ids in fleet.csv.
instance_id references instances/index.csv — por padrão apenas as instâncias
de kind ``archeti`` (`--instance-kind` muda isso; a ``base`` é configuração
fixa de referência e não é sorteada).
period is one of the demand sub-periods
(morning_1, morning_2, afternoon_1, afternoon_2, night_1, night_2),
matching the columns of the instance demand.csv files and the
`period` argument of utils.demand.load_demand_matrix.

`origin` and `destination_labels` recebem 1..`--max-labels` nós sorteados
(campos "n1;n2;...") — são as origens e os destinos possíveis do cenário.
Se a instância sorteada não tiver matriz de tempo (ou de distância) no disco,
ela é gerada na hora com valores aleatórios semeados (utils.synth).

A seed padrão é `utils.seed.DEFAULT_SEED`, a mesma dos demais geradores.

Este script reescreve apenas `scenarios.csv`; os cenários fixos da instância
``base`` ficam em `scenarios_base.csv` (escrito à mão) e os executores
(`main.py`, `scripts/run_all.py`) somam os dois arquivos — ver
`utils/scenarios.py`.

Usage:
  python scripts/generate_scenarios.py --num-scenarios 60 --seed 42
"""
import argparse
import csv
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.demand import DEMAND_PERIODS
from utils.seed import DEFAULT_SEED
from utils.synth import (
    DEFAULT_MIN_PER_UNIT,
    DEFAULT_SPAN_KM,
    ensure_matrices,
    instance_rng,
    load_nodes,
)

SCENARIO_FIELDS = [
    "scenario_id",
    "instance_id",
    "fleet_bus_ids",
    "period",
    "max_time_limit",
    "diesel_price_per_liter",
    "driver_hourly_rate",
    "origin",
    "destination_labels",
]


def read_fleet_ids(fleet_path: Path) -> list[int]:
    with fleet_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return [int(row["id"]) for row in reader]


def read_index(index_path: Path) -> list[dict]:
    with index_path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def filter_by_kind(instances: list[dict], kinds: set[str] | None) -> list[dict]:
    """Filtra as instâncias do índice pelos `kind`s pedidos (None = todas)."""
    if kinds is None:
        return instances
    kept = [row for row in instances if row.get("kind") in kinds]
    available = sorted({row.get("kind", "") for row in instances})
    if not kept:
        raise ValueError(
            f"nenhuma instância com kind em {sorted(kinds)}; o índice tem {available}"
        )
    return kept


def instance_nodes(instance_dir: Path, index_row: dict) -> list[int]:
    """Nós válidos da instância: do demand.csv ou, na falta, de num_nodes."""
    nodes = load_nodes(instance_dir / "demand.csv")
    if nodes:
        return nodes
    num_nodes = int(index_row.get("num_nodes") or 0)
    return list(range(1, num_nodes + 1)) if num_nodes else []


def node_labels(nodes: list[int], rng: random.Random, max_labels: int) -> str:
    """Sorteia 1..max_labels nós e devolve como "n1;n2;..."."""
    size = rng.randint(1, max(1, min(max_labels, len(nodes))))
    return ";".join(str(node) for node in sorted(rng.sample(nodes, size)))


def generate_scenarios(
    num_scenarios: int,
    fleet_ids: list[int],
    instances: list[dict],
    seed: int,
    *,
    max_labels: int = 3,
    span_km: float = DEFAULT_SPAN_KM,
    min_per_unit: float = DEFAULT_MIN_PER_UNIT,
) -> tuple[list[dict], dict[str, list[str]]]:
    rng = random.Random(seed)
    n = len(fleet_ids)
    low = max(1, min(3, n))
    created: dict[str, list[str]] = {}
    scenarios = []
    for scenario_id in range(1, num_scenarios + 1):
        instance = rng.choice(instances)
        instance_id = instance["instance_id"]
        instance_dir = ROOT / "instances" / instance_id
        nodes = instance_nodes(instance_dir, instance)
        if not nodes:
            raise ValueError(f"instância {instance_id!r} sem nós conhecidos")
        fresh = ensure_matrices(
            instance_dir,
            nodes,
            instance_rng(seed, instance_id),
            span=span_km,
            min_per_unit=min_per_unit,
        )
        if fresh:
            created.setdefault(instance_id, []).extend(fresh)
        k = rng.randint(low, n)
        subset = sorted(rng.sample(fleet_ids, k))
        scenarios.append({
            "scenario_id": scenario_id,
            "instance_id": instance_id,
            "fleet_bus_ids": ";".join(str(i) for i in subset),
            "period": rng.choice(DEMAND_PERIODS),
            "max_time_limit": rng.randint(30, 180),
            "diesel_price_per_liter": round(rng.uniform(5.0, 7.0), 2),
            "driver_hourly_rate": round(rng.uniform(20.0, 35.0), 2),
            "origin": node_labels(nodes, rng, max_labels),
            "destination_labels": node_labels(nodes, rng, max_labels),
        })
    return scenarios, created


def write_scenarios(scenarios: list[dict], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=SCENARIO_FIELDS)
        writer.writeheader()
        for row in scenarios:
            row.setdefault("origin", "")
            row.setdefault("destination_labels", "")
        writer.writerows(scenarios)


def parse_kinds(value: str) -> set[str] | None:
    """'all' (ou vazio) = todas as instâncias; senão, lista separada por vírgula."""
    text = value.strip().lower()
    if text in ("", "all", "*"):
        return None
    return {item.strip() for item in text.split(",") if item.strip()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate random scenarios.")
    parser.add_argument(
        "--num-scenarios", type=int, default=10, help="Number of scenarios to generate."
    )
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help="Seed raiz (utils/seed.py)."
    )
    parser.add_argument(
        "--instance-kind",
        default="archeti",
        help="Kinds de instância usados nos cenários (padrão: archeti; "
        "'all' = todas; aceita lista, ex.: 'archeti,base').",
    )
    parser.add_argument(
        "--max-labels",
        type=int,
        default=3,
        help="Máximo de nós sorteados por campo origin/destination_labels.",
    )
    parser.add_argument(
        "--span-km",
        type=float,
        default=DEFAULT_SPAN_KM,
        help="Lado do box (km) para matrizes ausentes.",
    )
    parser.add_argument(
        "--min-per-unit",
        type=float,
        default=DEFAULT_MIN_PER_UNIT,
        help="Minutos por km para matrizes ausentes.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.num_scenarios <= 0:
        raise ValueError("--num-scenarios must be > 0")
    fleet_ids = read_fleet_ids(ROOT / "fleet.csv")
    if not fleet_ids:
        raise ValueError("fleet.csv has no buses")
    instances = filter_by_kind(
        read_index(ROOT / "instances" / "index.csv"), parse_kinds(args.instance_kind)
    )
    if not instances:
        raise ValueError("instances/index.csv has no instances")
    scenarios, created = generate_scenarios(
        args.num_scenarios,
        fleet_ids,
        instances,
        args.seed,
        max_labels=args.max_labels,
        span_km=args.span_km,
        min_per_unit=args.min_per_unit,
    )
    output = ROOT / "scenarios.csv"
    write_scenarios(scenarios, output)
    print(
        f"Wrote {len(scenarios)} scenarios to {output} "
        f"(seed {args.seed}; {len(instances)} instâncias kind={args.instance_kind})"
    )
    for instance_id, files in sorted(created.items()):
        print(f"  matriz(es) gerada(s) para {instance_id}: {', '.join(sorted(set(files)))}")


if __name__ == "__main__":
    main()
