"""The CSV column layouts are a contract; these tests hold the files to it.

`utils.schemas` is the single source of the columns the generators write and
`utils/scenarios.py` / `utils/instances.py` read, so the committed files and
the writers cannot drift apart unnoticed.
"""

import csv

import pytest

from utils.fleet import FLEET_FIELDNAMES
from utils.schemas import INSTANCE_INDEX_FIELDS, SCENARIO_FIELDS
from utils.synth import demand_fields

SCENARIO_CSVS = (
    "scenarios.csv",
    "scenarios_base.csv",
    "scenarios_control.csv",
    "scenarios_base_control.csv",
)


def header(path) -> tuple[str, ...]:
    with path.open(newline="", encoding="utf-8") as f:
        return tuple(next(csv.reader(f)))


@pytest.mark.parametrize("name", SCENARIO_CSVS)
def test_every_scenario_file_has_the_scenario_columns(root, name):
    assert header(root / name) == SCENARIO_FIELDS


def test_instance_index_has_the_index_columns(root):
    assert header(root / "instances" / "index.csv") == INSTANCE_INDEX_FIELDS


def test_fleet_file_has_the_fleet_columns(root):
    assert header(root / "fleet.csv") == FLEET_FIELDNAMES


def test_demand_file_has_the_demand_columns(root):
    assert header(root / "instances" / "base" / "demand.csv") == tuple(
        demand_fields()
    )
