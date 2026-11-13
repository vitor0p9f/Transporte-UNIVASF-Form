"""Default scenario selection shared by the report runners."""

import pytest

from scripts.run_all import select_scenarios as select_top
from scripts.run_controlled_reports import select_scenarios as select_controlled
from scripts.run_top_real_fleet import select_scenarios as select_real
from utils.scenarios import DEFAULT_REPORT_SCENARIOS, pick_scenarios

EXPECTED = ("17", "19", "32", "65", "69")


def test_default_scenarios_are_the_five_report_scenarios():
    assert DEFAULT_REPORT_SCENARIOS == EXPECTED


def test_top_runner_uses_the_default_order(root):
    scenarios = select_top(root=root)
    assert [scenario["scenario_id"] for scenario in scenarios] == list(EXPECTED)


def test_controlled_runner_uses_the_default_order(root):
    scenarios = select_controlled(root=root)
    assert [scenario["scenario_id"] for scenario in scenarios] == list(EXPECTED)


def test_real_fleet_runner_uses_the_default_order(root):
    scenarios = select_real(root=root)
    assert [scenario["scenario_id"] for scenario in scenarios] == list(EXPECTED)


def test_pick_scenarios_rejects_unknown_id():
    with pytest.raises(ValueError, match="999"):
        pick_scenarios([{"scenario_id": "16"}], ("16", "999"))
