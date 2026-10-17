"""Geração sintética reprodutível: pontos, distância, tempo e demanda.

Calibrado em ``instances/base`` (46 nós):

    - pontos num box de ~13 km -> distância euclidiana (2 casas),
      média ~6.8 km;
    - tempo = ``max(1, round(km * 2.2 * U(0.9, 1.1)))`` (~2.2 min/km,
      média ~14 min);
    - demanda: ~0.2865 * n*(n-1) viagens (o base tem 593) concentradas em
      ~11% dos pares OD — o base tem 166 pares com viagem em 266 células
      (média 3.6 viagens por par), então a demanda é enviesada e cada par
      é atendido em 1 ou 2 sub-períodos.

Todas as funções recebem um ``random.Random`` já semeado, então a mesma
seed reproduz os mesmos arquivos. A seed raiz do projeto fica em
``utils/seed.py``.
"""

import csv
import math
import random
from pathlib import Path

from utils.demand import DEMAND_PERIODS

#: Primeira célula das matrizes quadradas (distance.csv / time.csv).
CORNER = "origin/destination"

#: Lado do box onde os pontos são sorteados, em km (base: média 6.8 km).
DEFAULT_SPAN_KM = 13.0

#: Minutos por km no tempo de viagem (base: ~2.23 min/km).
DEFAULT_MIN_PER_UNIT = 2.2

#: Viagens por par de nós no total dos 6 sub-períodos (base: 593/2070).
DEFAULT_DEMAND_RATIO = 0.2865

#: Fração de pares OD que concentram a demanda (base: 166/2070).
DEFAULT_PAIR_RATIO = 0.11

#: Expoente do viés entre pares quentes (base: média 3.6 viagens/par).
DEFAULT_DEMAND_SKEW = 2.5

#: Chance de um par quente ser atendido em 2 sub-períodos (base: 264/166).
DEFAULT_PERIOD_SPREAD = 0.8


def random_points(num_points: int, rng: random.Random, span: float = DEFAULT_SPAN_KM):
    """Sorteia `num_points` coordenadas (x, y) num box [0, span] x [0, span]."""
    return [(rng.uniform(0.0, span), rng.uniform(0.0, span)) for _ in range(num_points)]


def build_distance(points) -> list[list[float]]:
    """Matriz de distância euclidiana (km, 2 casas) entre os pontos."""
    n = len(points)
    matrix = [[0.0] * n for _ in range(n)]
    for i in range(n):
        xi, yi = points[i]
        for j in range(n):
            if i != j:
                xj, yj = points[j]
                matrix[i][j] = round(math.dist((xi, yi), (xj, yj)), 2)
    return matrix


def build_time(
    distance, rng: random.Random, min_per_unit: float = DEFAULT_MIN_PER_UNIT
) -> list[list[int]]:
    """Tempo de viagem (min, >= 1) a partir da distância, com ruído U(0.9, 1.1)."""
    n = len(distance)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                factor = min_per_unit * rng.uniform(0.9, 1.1)
                matrix[i][j] = max(1, int(round(distance[i][j] * factor)))
    return matrix


def demand_budget(num_nodes: int, ratio: float = DEFAULT_DEMAND_RATIO) -> int:
    """Orçamento de viagens para `num_nodes` (calibrado: 593 para 46 nós)."""
    return max(num_nodes, round(ratio * num_nodes * (num_nodes - 1)))


def build_demand(
    nodes: list[int],
    budget: int,
    rng: random.Random,
    *,
    pair_ratio: float = DEFAULT_PAIR_RATIO,
    skew: float = DEFAULT_DEMAND_SKEW,
    period_spread: float = DEFAULT_PERIOD_SPREAD,
) -> list[dict]:
    """Espalha `budget` viagens em pares OD "quentes", no perfil do base.

    Calibrado em ``instances/base`` (46 nós): ~11% dos pares concentram a
    demanda (~166 pares com viagem em 266 células), a distribuição por par
    é enviesada (``U(0,1) ** 2.5``: poucos pares têm muitas viagens) e cada
    par é atendido em 1 ou 2 sub-períodos (80% de chance de dois).

    Devolve uma linha por par OD fora da diagonal, no formato longo de
    demand.csv (colunas de sub-período zeradas quando não sorteadas).
    """
    nodes = sorted(nodes)
    pairs = [(origin, destination) for origin in nodes for destination in nodes
             if origin != destination]
    num_hot = max(1, min(len(pairs), round(pair_ratio * len(pairs))))
    hot = rng.sample(pairs, num_hot)
    weights = [rng.random() ** skew + 0.05 for _ in hot]

    counts: dict[tuple[int, int], int] = {}
    for _ in range(budget):
        pair = rng.choices(hot, weights=weights, k=1)[0]
        counts[pair] = counts.get(pair, 0) + 1

    cells: dict[tuple[int, int, str], int] = {}
    for (origin, destination), total in counts.items():
        size = min(1 + int(rng.random() < period_spread), total)
        periods = rng.sample(DEMAND_PERIODS, size)
        remaining = total
        for index, period in enumerate(periods):
            if index == size - 1:
                take = remaining
            else:
                take = rng.randint(1, remaining - (size - index - 1))
            cells[(origin, destination, period)] = take
            remaining -= take

    rows = []
    for origin in nodes:
        for destination in nodes:
            if origin == destination:
                continue
            row: dict = {"origin": origin, "destination": destination}
            for period in DEMAND_PERIODS:
                row[period] = cells.get((origin, destination, period), 0)
            rows.append(row)
    return rows


def demand_fields() -> list[str]:
    """Cabeçalho de demand.csv (origin, destination, 6 sub-períodos)."""
    return ["origin", "destination", *DEMAND_PERIODS]


def summarize_demand(rows) -> tuple[int, int]:
    """(pares OD, total de viagens nos 6 sub-períodos) de linhas de demanda."""
    total = sum(int(row[period]) for row in rows for period in DEMAND_PERIODS)
    return len(rows), total


def write_square(path, nodes: list[int], matrix, fmt=lambda v: v) -> None:
    """Grava uma matriz quadrada (distance.csv / time.csv) na ordem de `nodes`."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([CORNER] + [str(node) for node in nodes])
        for row_index, node in enumerate(nodes):
            writer.writerow([str(node)] + [fmt(value) for value in matrix[row_index]])


def read_square(path) -> tuple[list[int], list[list[float]]]:
    """Lê uma matriz quadrada como (ids dos nós, matriz alinhada aos ids)."""
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        nodes = [int(cell) for cell in header[1:]]
        rows = list(reader)
    matrix = [[float(value) for value in row[1:]] for row in rows]
    return nodes, matrix


def write_demand(path, rows) -> None:
    """Grava demand.csv no formato longo (um par OD por linha)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=demand_fields())
        writer.writeheader()
        writer.writerows(rows)


def load_nodes(demand_path) -> list[int]:
    """Ids de nós que aparecem em demand.csv (vazio se o arquivo não existe)."""
    demand_path = Path(demand_path)
    if not demand_path.exists():
        return []
    nodes: set[int] = set()
    with demand_path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            nodes.add(int(row["origin"]))
            nodes.add(int(row["destination"]))
    return sorted(nodes)


def integer_cell(value) -> int | float:
    """Formata uma célula de tempo: int quando inteiro, float caso contrário."""
    number = float(value)
    return int(number) if number.is_integer() else number


def instance_rng(seed: int, instance_id: str) -> random.Random:
    """RNG determinístico por instância, derivado da seed raiz."""
    return random.Random(f"{seed}:{instance_id}")


def ensure_matrices(
    instance_dir,
    nodes: list[int],
    rng: random.Random,
    *,
    span: float = DEFAULT_SPAN_KM,
    min_per_unit: float = DEFAULT_MIN_PER_UNIT,
    force: bool = False,
) -> list[str]:
    """Cria distance.csv/time.csv ausentes com valores aleatórios semeados.

    Usado quando um cenário aponta para uma instância sem matriz de tempo
    (ou de distância): em vez de falhar, o dado é gerado na hora a partir
    dos nós conhecidos. Devolve a lista de arquivos criados.
    """
    instance_dir = Path(instance_dir)
    nodes = sorted(nodes)
    distance_path = instance_dir / "distance.csv"
    time_path = instance_dir / "time.csv"
    created = []

    if force or not distance_path.exists():
        points = random_points(len(nodes), rng, span)
        write_square(distance_path, nodes, build_distance(points))
        created.append("distance.csv")

    if force or not time_path.exists():
        _, distance = read_square(distance_path)
        write_square(time_path, nodes, build_time(distance, rng, min_per_unit), integer_cell)
        created.append("time.csv")

    return created
