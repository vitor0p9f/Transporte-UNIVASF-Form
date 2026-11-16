"""Loading helpers for square OD matrices (distance.csv, time.csv).

Square files share one layout: a corner cell, a header row with
destination ids, and one row per origin with the origin id first::

    origin/destination,1,2,3,...
    1,0.0,0.65,...
    ...

Matrices are returned as numpy arrays indexed directly by node id,
i.e. ``matrix[origin, destination]``. Index 0 is unused padding
(node ids start at 1).
"""

import csv
from pathlib import Path

import numpy as np


def load_square_matrix(path: str | Path, dtype=float) -> tuple[list[int], np.ndarray]:
    """Load a square matrix CSV as a numpy array.

    Args:
        path: Path to a distance.csv / time.csv file.
        dtype: Numpy dtype of the array (float or int).

    Returns:
        (nodes, matrix) where `nodes` is the sorted id list and
        `matrix` is a (max_id + 1) x (max_id + 1) array with the
        zero diagonal included. Use node ids straight as indices.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)
        columns = [int(c) for c in header[1:]]
        cells = []
        origins = []
        for row in reader:
            origin = int(row[0])
            origins.append(origin)
            for dest, value in zip(columns, row[1:]):
                cells.append((origin, dest, dtype(value)))
    nodes = sorted(set(origins) | set(columns))
    matrix = np.zeros((nodes[-1] + 1, nodes[-1] + 1), dtype=dtype)
    for origin, dest, value in cells:
        matrix[origin, dest] = value
    return nodes, matrix
