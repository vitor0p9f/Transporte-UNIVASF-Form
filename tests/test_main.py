"""Tests for the report scenarios that main.py renders and writes."""

import main
import reporting
from algorithms.top_univasf import BusPlan
from tests import factories
from tests.factories import make_bus, make_data, make_summary

SCENARIO = {
    "scenario_id": "1",
    "instance_id": "p1_4_e",
    "period": "morning_2",
    "fleet_bus_ids": "1;4;5;10",
    "max_time_limit": 56,
}


def make_plan(served: int = 4, peak: int = 2, travel: int = 15) -> BusPlan:
    return factories.make_plan(
        bus_id=1,
        origin=1,
        destination=3,
        stops=(1, 2, 3),
        served_passengers=served,
        travel_time_minutes=travel,
        peak_load=peak,
        score=served / travel if travel else 0.0,
        served_pairs=((1, 3, served),) if served else (),
    )


def make_run(
    heuristic: str,
    *,
    served: int,
    unserved: int,
    elapsed: float = 0.0,
    scenario: dict | None = None,
) -> reporting.ScenarioRun:
    return reporting.ScenarioRun(
        scenario=scenario or SCENARIO,
        buses=[make_bus(1, capacity=24, fuel_capacity=121.0, km_per_liter=4.61)],
        elapsed=elapsed,
        data=make_data({(1, 3): served} if served else {}),
        plans=[make_plan(served=served)],
        summary=make_summary(unserved=unserved),
        heuristic=heuristic,
    )


def make_outcome(heuristic: str, *, served: int, unserved: int) -> list[reporting.ScenarioRun]:
    return [
        make_run(heuristic, served=served, unserved=unserved),
        make_run("Clarke-Wright", served=served, unserved=unserved, elapsed=12.5),
    ]


class TestRenderMarkdown:
    def test_one_row_per_heuristic_per_scenario(self):
        md = main.render_markdown(
            make_outcome("TOP (Greedy OD)", served=4, unserved=0),
            "2026-11-01 12:00 UTC",
        )

        assert md.startswith("# Results")
        assert md.count("| 1 | p1_4_e | morning_2 | [1;4;5;10] | 56 |") == 2
        assert (
            "| 1 | p1_4_e | morning_2 | [1;4;5;10] | 56 | TOP (Greedy OD) | 1/1 | 4/4 | 0 | 100% | 3 | 0.0 |"
            in md
        )
        assert (
            "| 1 | p1_4_e | morning_2 | [1;4;5;10] | 56 | Clarke-Wright | 1/1 | 4/4 | 0 | 100% | 3 | 12.5 |"
            in md
        )

    def test_each_scenario_gets_its_own_heading_and_detail(self):
        runs = make_outcome("TOP (Greedy OD)", served=4, unserved=0)
        runs.append(
            make_run(
                "Clarke-Wright",
                served=4,
                unserved=0,
                elapsed=3.0,
                scenario={**SCENARIO, "scenario_id": "2", "instance_id": "base", "period": "night_1"},
            )
        )
        md = main.render_markdown(runs, "2026-11-01 12:00 UTC")

        assert "## Scenario 1 — p1_4_e / morning_2" in md
        assert "## Scenario 2 — base / night_1" in md
        assert md.count("### ") == 3

    def test_unserved_pax_go_into_the_row(self):
        md = main.render_markdown(
            [make_run("Clarke-Wright", served=1, unserved=3, elapsed=12.5)],
            "2026-11-01 12:00 UTC",
        )

        assert (
            "| 1 | p1_4_e | morning_2 | [1;4;5;10] | 56 | Clarke-Wright | 1/1 | 1/1 | 3 | 100% | 3 | 12.5 |"
            in md
        )
        assert "Unserved (3 pax):" in md


class TestWriteMarkdown:
    def test_writes_the_report_to_the_given_path(self, tmp_path):
        runs = make_outcome("TOP (Greedy OD)", served=4, unserved=0)
        path = tmp_path / "results.md"

        written = main.write_markdown(runs, path)

        assert path.exists()
        assert written == path.read_text(encoding="utf-8")
        assert written.startswith("# Results")
