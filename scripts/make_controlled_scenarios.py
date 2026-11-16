"""Create the controlled scenario copy: a homogeneous fleet of the smallest bus.

The controlled copy keeps every scenario's instance, period, time limit, diesel
price, driver rate and origin/destination labels, and keeps the fleet SIZE, but
every bus is the same vehicle: the smallest-capacity bus of ``fleet.csv`` (lowest
id on ties). This removes the fleet heterogeneity from the comparison: all buses
have the same number of seats and the same fuel autonomy.

Outputs, next to the originals:

    fleet_control.csv            one row per original bus, all the reference model
    scenarios_control.csv        copy of ``scenarios.csv``
    scenarios_base_control.csv   copy of ``scenarios_base.csv``

In the scenario copies, ``fleet_bus_ids`` becomes ``1;2;...;N`` (N = the
original fleet size), so the rows point at the controlled fleet unambiguously.
Everything else is copied unchanged.

Usage:
  python scripts/make_controlled_scenarios.py
"""

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from utils.fleet import FLEET_FIELDNAMES, load_fleet

FLEET_PATH = ROOT / "fleet.csv"
CONTROLLED_FLEET_PATH = ROOT / "fleet_control.csv"

#: Source scenario file -> controlled copy.
CONTROLLED_FILES = {
    "scenarios.csv": "scenarios_control.csv",
    "scenarios_base.csv": "scenarios_base_control.csv",
}


def read_fleet_rows(path: Path) -> list[dict]:
    """The raw fleet rows, preserving the CSV's numeric formatting."""
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def reference_row(rows: list[dict]) -> dict:
    """The smallest-capacity bus; lowest id wins ties."""
    return min(rows, key=lambda row: (int(row["passenger_capacity"]), int(row["id"])))


def write_controlled_fleet(
    path: Path, reference: dict, count: int
) -> None:
    """`count` identical buses, ids 1..count, all the reference model."""
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=FLEET_FIELDNAMES, lineterminator="\n"
        )
        writer.writeheader()
        for bus_id in range(1, count + 1):
            writer.writerow(
                {
                    "id": bus_id,
                    "passenger_capacity": reference["passenger_capacity"],
                    "fuel_capacity": reference["fuel_capacity"],
                    "km_autonomy_per_liter": reference["km_autonomy_per_liter"],
                }
            )


def rewrite_scenarios(source: Path, target: Path, fleet_size: int) -> int:
    """Copy `source` to `target` pointing every row at ids 1..N.

    Returns the number of rows written.
    """
    with source.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    if fieldnames is None:
        raise ValueError(f"{source}: missing header")
    for row in rows:
        requested = [item for item in row["fleet_bus_ids"].split(";") if item]
        if not requested:
            raise ValueError(
                f"{source}: scenario {row['scenario_id']} has an empty fleet"
            )
        if len(requested) > fleet_size:
            raise ValueError(
                f"{source}: scenario {row['scenario_id']} asks for "
                f"{len(requested)} buses, but fleet.csv has only {fleet_size}"
            )
        row["fleet_bus_ids"] = ";".join(
            str(bus_id) for bus_id in range(1, len(requested) + 1)
        )
    with target.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=fieldnames, lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def main() -> None:
    fleet_rows = read_fleet_rows(FLEET_PATH)
    if not fleet_rows:
        raise ValueError(f"{FLEET_PATH}: no buses")
    reference = reference_row(fleet_rows)

    # Validate the source through the same loader the runners use.
    load_fleet(FLEET_PATH)

    write_controlled_fleet(
        CONTROLLED_FLEET_PATH, reference, len(fleet_rows)
    )
    print(
        f"Wrote {CONTROLLED_FLEET_PATH.name}: {len(fleet_rows)} buses, "
        f"all {reference['passenger_capacity']} seats / "
        f"{reference['km_autonomy_per_liter']} km/L "
        f"(reference: bus {reference['id']})"
    )

    for source_name, target_name in CONTROLLED_FILES.items():
        source = ROOT / source_name
        if not source.exists():
            print(f"skip {source_name}: not found")
            continue
        written = rewrite_scenarios(
            source, ROOT / target_name, len(fleet_rows)
        )
        print(f"Wrote {target_name}: {written} scenarios")


if __name__ == "__main__":
    main()
