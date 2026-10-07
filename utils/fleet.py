"""Loading helpers for fleet.csv.

Fleet files have one row per bus::

    id,passenger_capacity,fuel_capacity,km_autonomy_per_liter
    1,24,148,4.11
    ...

Scenarios reference a subset via a semicolon-separated id list
(e.g. ``"8;9"`` in the ``fleet_bus_ids`` column of scenarios.csv).
"""

import csv
from collections.abc import Iterable
from pathlib import Path

from entities.bus import Bus

FLEET_FIELDNAMES = (
    "id",
    "passenger_capacity",
    "fuel_capacity",
    "km_autonomy_per_liter",
)


def parse_fleet_ids(value: str) -> list[int]:
    """Parse a ``"8;9"`` style id list into [8, 9]."""
    ids = [v.strip() for v in value.split(";")]
    return [int(v) for v in ids if v]


def load_fleet(
    path: str | Path, bus_ids: Iterable[int] | None = None
) -> list[Bus]:
    """Load buses from a fleet.csv file.

    Args:
        path: Path to a fleet.csv file.
        bus_ids: Optional ids to select. Order is preserved, so a
            scenario asking for ``[8, 9]`` gets them in that order.

    Returns:
        The selected buses, or every bus sorted by id when
        `bus_ids` is None.

    Raises:
        ValueError: If columns are missing, values are not positive,
            ids are duplicated, or a requested id is unknown.
    """
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        missing = [c for c in FLEET_FIELDNAMES if c not in (reader.fieldnames or [])]
        if missing:
            raise ValueError(f"{path}: missing columns {missing}")
        buses: dict[int, Bus] = {}
        for row in reader:
            bus = Bus(
                id=int(row["id"]),
                passenger_capacity=int(row["passenger_capacity"]),
                fuel_capacity=float(row["fuel_capacity"]),
                km_autonomy_per_liter=float(row["km_autonomy_per_liter"]),
            )
            if bus.id <= 0:
                raise ValueError(f"{path}: invalid bus id {bus.id}")
            if bus.passenger_capacity <= 0:
                raise ValueError(f"{path}: bus {bus.id} has no seats")
            if bus.fuel_capacity <= 0 or bus.km_autonomy_per_liter <= 0:
                raise ValueError(f"{path}: bus {bus.id} has invalid fuel data")
            if bus.id in buses:
                raise ValueError(f"{path}: duplicated bus id {bus.id}")
            buses[bus.id] = bus
    if bus_ids is None:
        return [buses[k] for k in sorted(buses)]
    selected = [buses.get(bus_id) for bus_id in bus_ids]
    unknown = [str(bus_id) for bus_id, bus in zip(bus_ids, selected) if bus is None]
    if unknown:
        raise ValueError(f"{path}: unknown bus ids {', '.join(unknown)}")
    return [bus for bus in selected if bus is not None]
