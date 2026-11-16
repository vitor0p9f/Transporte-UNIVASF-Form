"""Loading helper for one instance's matrices.

An instance directory holds the three matrices the heuristic reads, all
indexed directly by node id (see ``utils.matrices`` and ``utils.demand``)::

    instances/<instance_id>/distance.csv   distance between nodes (km)
    instances/<instance_id>/time.csv       travel time between nodes (min)
    instances/<instance_id>/demand.csv     OD demand per period

Only ``time`` and ``demand`` feed the heuristic; ``distance`` is loaded
because it is part of the instance and feeds the operational cost
calculation.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from utils.demand import load_demand_matrix
from utils.matrices import load_square_matrix


@dataclass
class InstanceData:
    """Matrices of one instance, indexed directly by node id."""

    nodes: list[int]
    distance: np.ndarray
    time: np.ndarray
    demand: np.ndarray


def load_instance_data(instance_dir: str | Path, period: str) -> InstanceData:
    """Load distance, time and demand matrices for one instance/period.

    Args:
        instance_dir: Directory holding the instance CSV files.
        period: Demand period, shift or "total" (see ``utils.demand``).
    """
    instance_dir = Path(instance_dir)
    nodes, distance = load_square_matrix(instance_dir / "distance.csv")
    _, time = load_square_matrix(instance_dir / "time.csv", dtype=int)
    _, demand = load_demand_matrix(instance_dir / "demand.csv", period=period)
    return InstanceData(nodes=nodes, distance=distance, time=time, demand=demand)
