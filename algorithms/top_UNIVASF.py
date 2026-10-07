"""UNIVASF TOP heuristic (nearest neighbor / max demand)."""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from entities.bus import Bus
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
    """Load distance, time and demand matrices for one instance/period."""
    instance_dir = Path(instance_dir)
    nodes, distance = load_square_matrix(instance_dir / "distance.csv")
    _, time = load_square_matrix(instance_dir / "time.csv", dtype=int)
    _, demand = load_demand_matrix(instance_dir / "demand.csv", period=period)
    return InstanceData(nodes=nodes, distance=distance, time=time, demand=demand)


def run(scenario: dict, buses: list[Bus], root: str | Path) -> InstanceData:
    """Load everything the greedy heuristics need for one scenario."""
    instance_dir = Path(root) / "instances" / scenario["instance_id"]
    return load_instance_data(instance_dir, period=scenario["period"])
