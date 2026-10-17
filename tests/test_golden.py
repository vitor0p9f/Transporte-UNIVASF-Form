"""Golden-master regression: every scenario must keep the same outcome.

The fixture in ``tests/fixtures/results_baseline.json`` was generated from
the code before the refactor (``scripts/dump_results.py``). A diff here means
a refactor step changed the heuristic, not only its shape.
"""

import json
from pathlib import Path

import pytest

from scripts.dump_results import scenario_outcome
from utils.scenarios import load_scenarios

ROOT = Path(__file__).resolve().parent.parent
BASELINE_PATH = Path(__file__).resolve().parent / "fixtures" / "results_baseline.json"
BASELINE = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
SCENARIO_IDS = [entry["scenario_id"] for entry in BASELINE]


def test_fixture_covers_every_scenario(root):
    """The baseline must describe exactly the scenarios on disk."""
    assert set(SCENARIO_IDS) == {s["scenario_id"] for s in load_scenarios(root)}
    assert len(SCENARIO_IDS) == len(set(SCENARIO_IDS))


@pytest.mark.parametrize("scenario_id", SCENARIO_IDS)
def test_scenario_outcome_matches_baseline(scenario_id, root, baseline):
    scenario = next(s for s in load_scenarios(root) if s["scenario_id"] == scenario_id)
    assert scenario_outcome(scenario, root) == baseline[scenario_id]


def test_sweep_is_deterministic(root, baseline):
    """Two runs of the same scenario must produce identical data."""
    scenario = next(s for s in load_scenarios(root) if s["scenario_id"] == SCENARIO_IDS[0])
    assert scenario_outcome(scenario, root) == scenario_outcome(scenario, root)
