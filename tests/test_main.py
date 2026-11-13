"""Tests for the report scenarios that main.py renders and writes."""

import main
from algorithms.top_univasf import BusPlan
from tests import factories
from tests.factories import make_bus, make_data, make_summary


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


def make_outcome(heuristic: str, *, served: int, unserved: int) -> main.ScenarioOutcome:
    data = make_data({(1, 3): served} if served else {})
    plans = [make_plan(served=served)]
    summary = make_summary(unserved=unserved)
    return main.ScenarioOutcome(
        scenario={
            "scenario_id": "1",
            "instance_id": "p1_4_e",
            "period": "morning_2",
            "fleet_bus_ids": "1;4;5;10",
            "max_time_limit": 56,
        },
        buses=[make_bus(1, capacity=24, fuel_capacity=121.0, km_per_liter=4.61)],
        runs=[
            main.Result(heuristic=heuristic, data=data, plans=plans, summary=summary, elapsed=0.0),
            main.Result(
                heuristic="Clarke-Wright",
                data=data,
                plans=plans,
                summary=summary,
                elapsed=12.5,
            ),
        ],
    )


class TestRenderMarkdown:
    def test_one_row_per_heuristic_per_scenario(self):
        md = main.render_markdown([make_outcome("TOP (Greedy OD)", served=4, unserved=0)], "2026-11-01 12:00 UTC")

        assert md.startswith("# Results")
        assert md.count("| 1 | p1_4_e | morning_2 | [1;4;5;10] | 56 |") == 2
        assert (
            "| 1 | p1_4_e | morning_2 | [1;4;5;10] | 56 | TOP (Greedy OD) | 1/1 | 4/4 | 4 | 0 | 100% | 3 | 0.0 |"
            in md
        )
        assert (
            "| 1 | p1_4_e | morning_2 | [1;4;5;10] | 56 | Clarke-Wright | 1/1 | 4/4 | 4 | 0 | 100% | 3 | 12.5 |"
            in md
        )

    def test_each_scenario_gets_its_own_heading_and_detail(self):
        outcomes = [
            make_outcome("TOP (Greedy OD)", served=4, unserved=0),
            main.ScenarioOutcome(
                scenario={
                    "scenario_id": "2",
                    "instance_id": "base",
                    "period": "night_1",
                    "fleet_bus_ids": "1;2",
                    "max_time_limit": 120,
                },
                buses=[make_bus(1, capacity=24, fuel_capacity=121.0, km_per_liter=4.61)],
                runs=[
                    main.Result(
                        heuristic="Clarke-Wright",
                        data=make_data({(1, 3): 4}),
                        plans=[make_plan(served=4)],
                        summary=make_summary(),
                        elapsed=3.0,
                    )
                ],
            ),
        ]
        md = main.render_markdown(outcomes, "2026-11-01 12:00 UTC")

        assert "## Scenario 1 — p1_4_e / morning_2" in md
        assert "## Scenario 2 — base / night_1" in md
        assert md.count("### ") == 3

    def test_unserved_pax_go_into_the_row(self):
        md = main.render_markdown(
            [make_outcome("Clarke-Wright", served=1, unserved=3)], "2026-11-01 12:00 UTC"
        )

        assert (
            "| 1 | p1_4_e | morning_2 | [1;4;5;10] | 56 | Clarke-Wright | 1/1 | 1/1 | 1 | 3 | 100% | 3 | 12.5 |"
            in md
        )
        assert "Unserved (3 pax):" in md


class TestWriteMarkdown:
    def test_writes_the_report_to_the_given_path(self, tmp_path):
        outcomes = [make_outcome("TOP (Greedy OD)", served=4, unserved=0)]
        path = tmp_path / "results.md"

        written = main.write_markdown(outcomes, path)

        assert path.exists()
        assert written == path.read_text(encoding="utf-8")
        assert written.startswith("# Results")
