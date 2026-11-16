"""Reproducible synthetic generation: points, distance, time and demand.

Calibrated on ``instances/base`` (46 nodes):

    - points in a ~13 km box -> Euclidean distance (2 decimals), mean ~6.8 km;
    - time = ``max(1, round(km * 2.2 * U(0.9, 1.1)))`` (~2.2 min/km, mean
      ~14 min);
    - demand: ~0.2865 * n*(n-1) trips (base has 593) concentrated on ~11% of
      the OD pairs -- base has 166 pairs with a trip across 266 cells (mean 3.6
      trips per pair), so the demand is skewed and each pair is served in 1 or
      2 sub-periods.

Every function takes an already seeded ``random.Random``, so the same seed
reproduces the same files. The project root seed lives in ``utils/seed.py``.
"""

import csv
import math
import random
from pathlib import Path

from utils.demand import DEMAND_PERIODS

#: First cell of the square matrices (distance.csv / time.csv).
CORNER = "origin/destination"

#: Side of the box the points are sampled in, in km (base: mean 6.8 km).
DEFAULT_SPAN_KM = 13.0

#: Minutes per km in the travel time (base: ~2.23 min/km).
DEFAULT_MIN_PER_UNIT = 2.2

#: Trips per node pair over all 6 sub-periods (base: 593/2070).
DEFAULT_DEMAND_RATIO = 0.2865

#: Fraction of OD pairs that concentrate the demand (base: 166/2070).
DEFAULT_PAIR_RATIO = 0.11

#: Skew exponent between hot pairs (base: mean 3.6 trips per pair).
DEFAULT_DEMAND_SKEW = 2.5

#: Chance a hot pair is served across 2 sub-periods (base: 264/166).
DEFAULT_PERIOD_SPREAD = 0.8


def random_points(num_points: int, rng: random.Random, span: float = DEFAULT_SPAN_KM):
    """Sample `num_points` (x, y) coordinates in a [0, span] x [0, span] box."""
    return [(rng.uniform(0.0, span), rng.uniform(0.0, span)) for _ in range(num_points)]


def build_distance(points) -> list[list[float]]:
    """Euclidean distance matrix (km, 2 decimals) between the points."""
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
    """Travel time (min, >= 1) from the distance, with U(0.9, 1.1) noise."""
    n = len(distance)
    matrix = [[0] * n for _ in range(n)]
    for i in range(n):
        for j in range(n):
            if i != j:
                factor = min_per_unit * rng.uniform(0.9, 1.1)
                matrix[i][j] = max(1, round(distance[i][j] * factor))
    return matrix


def demand_budget(num_nodes: int, ratio: float = DEFAULT_DEMAND_RATIO) -> int:
    """Trip budget for `num_nodes` (calibrated: 593 for 46 nodes)."""
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
    """Spread `budget` trips over "hot" OD pairs, following the base profile.

    Calibrated on ``instances/base`` (46 nodes): ~11% of the pairs concentrate
    the demand (~166 pairs with a trip across 266 cells), the per-pair
    distribution is skewed (``U(0,1) ** 2.5``: a few pairs hold many trips) and
    each pair is served in 1 or 2 sub-periods (80% chance of two).

    Returns one row per off-diagonal OD pair, in the long demand.csv format
    (sub-period columns are zero when not sampled).
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
    """Header of demand.csv (origin, destination, 6 sub-periods)."""
    return ["origin", "destination", *DEMAND_PERIODS]


def summarize_demand(rows) -> tuple[int, int]:
    """(OD pairs, total trips over the 6 sub-periods) of demand rows."""
    total = sum(int(row[period]) for row in rows for period in DEMAND_PERIODS)
    return len(rows), total


def write_square(path, nodes: list[int], matrix, fmt=lambda v: v) -> None:
    """Write a square matrix (distance.csv / time.csv) in `nodes` order."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([CORNER] + [str(node) for node in nodes])
        for row_index, node in enumerate(nodes):
            writer.writerow([str(node)] + [fmt(value) for value in matrix[row_index]])


def read_square(path) -> tuple[list[int], list[list[float]]]:
    """Read a square matrix as (node ids, matrix aligned with those ids)."""
    with Path(path).open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        nodes = [int(cell) for cell in header[1:]]
        rows = list(reader)
    matrix = [[float(value) for value in row[1:]] for row in rows]
    return nodes, matrix


def write_demand(path, rows) -> None:
    """Write demand.csv in the long format (one OD pair per row)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=demand_fields())
        writer.writeheader()
        writer.writerows(rows)


def load_nodes(demand_path) -> list[int]:
    """Node ids appearing in demand.csv (empty when the file does not exist)."""
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
    """Format a time cell: int when integral, float otherwise."""
    number = float(value)
    return int(number) if number.is_integer() else number


def instance_rng(seed: int, instance_id: str) -> random.Random:
    """Deterministic per-instance RNG, derived from the root seed."""
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
    """Create missing distance.csv/time.csv with seeded random values.

    Used when a scenario points at an instance with no time (or distance)
    matrix: instead of failing, the data is generated on the spot from the
    known nodes. Returns the list of files created.
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
