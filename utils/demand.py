"""Loading helpers for demand CSVs (long OD format).

Demand files have one row per off-diagonal OD pair::

    origin,destination,morning_1,morning_2,afternoon_1,afternoon_2,night_1,night_2
    1,2,0,0,0,0,0,0
    ...

Demands are returned as numpy arrays indexed directly by node id,
i.e. ``demands[origin, destination]``. Index 0 is unused padding
(node ids start at 1) and the diagonal stays zero.
"""

import csv
from pathlib import Path

import numpy as np

DEMAND_PERIODS = (
    "morning_1",
    "morning_2",
    "afternoon_1",
    "afternoon_2",
    "night_1",
    "night_2",
)

#: Aggregated shifts: each sums its two sub-periods.
SHIFTS = {
    "morning": ("morning_1", "morning_2"),
    "afternoon": ("afternoon_1", "afternoon_2"),
    "night": ("night_1", "night_2"),
}

TOTAL = "total"

VALID_PERIODS = DEMAND_PERIODS + tuple(SHIFTS) + (TOTAL,)


def columns_for(period: str) -> tuple[str, ...]:
    """Return the CSV columns summed for `period`.

    Raises:
        ValueError: If `period` is not a sub-period, a shift, or "total".
    """
    if period in DEMAND_PERIODS:
        return (period,)
    if period in SHIFTS:
        return SHIFTS[period]
    if period == TOTAL:
        return DEMAND_PERIODS
    raise ValueError(f"Unknown period {period!r}. Valid: {', '.join(VALID_PERIODS)}")


def load_demand_matrix(path: str | Path, period: str = TOTAL) -> tuple[list[int], np.ndarray]:
    """Load demand for a single period, shift, or the total.

    Args:
        path: Path to a demand.csv file.
        period: One of the sub-periods (e.g. "morning_1"), an
            aggregated shift ("morning", "afternoon", "night" — sums
            the two sub-periods), or "total" (default, sums all six).

    Returns:
        (nodes, demands) where `nodes` is the sorted id list and
        `demands` is an int (max_id + 1) x (max_id + 1) array.
        Zero-demand pairs are 0; the diagonal is 0.
    """
    columns = columns_for(period)
    path = Path(path)
    cells = []
    nodes = set()
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in columns if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing columns {missing}")
        for row in reader:
            origin, destination = int(row["origin"]), int(row["destination"])
            nodes.add(origin)
            nodes.add(destination)
            cells.append((origin, destination, sum(int(row[c]) for c in columns)))
    nodes = sorted(nodes)
    demands = np.zeros((nodes[-1] + 1, nodes[-1] + 1), dtype=int)
    for origin, destination, value in cells:
        demands[origin, destination] = value
    return nodes, demands
