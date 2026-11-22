"""Default scenario selection shared by the report runners."""

import pytest

import reporting
from scripts.run_controlled_reports import occupancy_cells
from scripts.run_all import select_scenarios as select_top
from scripts.run_controlled_reports import select_scenarios as select_controlled
from scripts.run_top_real_fleet import select_scenarios as select_real
from utils.scenarios import DEFAULT_REPORT_SCENARIOS, pick_scenarios

EXPECTED = ("16", "19", "32", "65", "69")


def test_default_scenarios_are_the_five_report_scenarios():
    assert DEFAULT_REPORT_SCENARIOS == EXPECTED


@pytest.mark.parametrize(
    "selector",
    [select_top, select_controlled, select_real],
    ids=["top", "controlled", "real_fleet"],
)
def test_runner_uses_the_default_order(selector, root):
    scenarios = selector(root=root)
    assert [scenario["scenario_id"] for scenario in scenarios] == list(EXPECTED)


def test_pick_scenarios_rejects_unknown_id():
    with pytest.raises(ValueError, match="999"):
        pick_scenarios([{"scenario_id": "16"}], ("16", "999"))


def test_controlled_occupancy_row_uses_the_physical_audit():
    audit = reporting.OccupancyAudit(
        peak=112,
        bus_id=2,
        route=(43, 10, 7, 45),
        capacity=24,
        violating_routes=2,
        max_excess=88,
        max_excess_bus_id=2,
        max_excess_route=(43, 10, 7, 45),
    )

    cells = occupancy_cells({"scenario_id": "69"}, "Clarke-Wright", audit)

    assert cells == (
        "69",
        "Clarke-Wright",
        "112/24",
        "2",
        "43 -> 10 -> 7 -> 45",
        "2",
        "88",
        "2: 43 -> 10 -> 7 -> 45",
    )
