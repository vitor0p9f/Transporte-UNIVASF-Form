"""Shared pytest fixtures: project root and the frozen sweep baseline."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASELINE_PATH = Path(__file__).resolve().parent / "fixtures" / "results_baseline.json"


@pytest.fixture(scope="session")
def root() -> Path:
    """Project root, the directory holding fleet.csv and scenarios.csv."""
    return ROOT


@pytest.fixture(scope="session")
def baseline() -> dict[str, dict]:
    """Frozen outcome of every scenario, keyed by scenario_id."""
    payload = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
    return {entry["scenario_id"]: entry for entry in payload}
