"""Unit tests for the renderer shared by main.py and scripts/run_all.py."""

import numpy as np

import reporting
from algorithms.top_univasf import BusPlan, FleetSummary, InstanceData
from entities.bus import Bus


def make_plan(
    bus_id=1,
    origin=3,
    destination=7,
    stops=(3, 5, 7),
    served_passengers=4,
    travel_time_minutes=20,
    peak_load=2,
    score=0.2,
    served_pairs=((3, 7, 4),),
) -> BusPlan:
    """A plan with plausible defaults; override only what the test needs."""
    return BusPlan(
        bus_id=bus_id,
        origin=origin,
        destination=destination,
        stops=stops,
        served_passengers=served_passengers,
        travel_time_minutes=travel_time_minutes,
        peak_load=peak_load,
        score=score,
        served_pairs=served_pairs,
    )


def make_bus(bus_id=1, capacity=24) -> Bus:
    return Bus(
        id=bus_id,
        passenger_capacity=capacity,
        fuel_capacity=150.0,
        km_autonomy_per_liter=4.0,
    )


def make_data(demand: dict, size: int = 8) -> InstanceData:
    """Tiny instance whose demand matrix only carries the pairs given."""
    demands = np.zeros((size + 1, size + 1), dtype=int)
    for (origin, destination), quantity in demand.items():
        demands[origin, destination] = quantity
    return InstanceData(
        nodes=list(range(1, size + 1)),
        distance=np.zeros((size + 1, size + 1)),
        time=np.zeros((size + 1, size + 1), dtype=int),
        demand=demands,
    )


class TestPlanCells:
    def test_cells_follow_the_header_order(self):
        cells = reporting.plan_cells(make_plan(), time_limit_minutes=60)
        assert len(cells) == len(reporting.PLAN_HEADERS)
        assert cells == ("1", "3", "4", "20/60", "2", "0.20", "3", "7")

    def test_origin_is_the_first_stop_and_not_the_locked_origin(self):
        plan = make_plan(origin=3, destination=7, stops=(5, 3, 7))
        cells = reporting.plan_cells(plan, time_limit_minutes=60)
        assert cells[6] == "5"  # where the route actually starts
        assert cells[7] == "7"

    def test_capacity_turns_the_peak_into_used_over_total(self):
        plan = make_plan(peak_load=6)
        cells = reporting.plan_cells(plan, time_limit_minutes=45, capacity=24)
        assert cells[4] == "6/24"


class TestServedRatio:
    def test_counts_only_what_the_plans_served(self):
        data = make_data({(3, 7): 4, (1, 2): 6})
        plans = [make_plan(served_passengers=4), make_plan(bus_id=2, served_passengers=2)]
        assert reporting.served_ratio(data, plans) == (6, 10, 60.0)

    def test_empty_demand_does_not_divide_by_zero(self):
        assert reporting.served_ratio(make_data({}), []) == (0, 0, 0.0)


class TestTopServedPairs:
    def test_sums_the_same_pair_across_buses(self):
        plans = [
            make_plan(served_pairs=((3, 7, 4), (1, 2, 1))),
            make_plan(bus_id=2, served_pairs=((3, 7, 3),)),
        ]
        assert reporting.top_served_pairs(plans) == [(3, 7, 7), (1, 2, 1)]

    def test_limit_keeps_the_highest_quantities(self):
        plan = make_plan(served_pairs=((1, 2, 1), (3, 4, 5), (5, 6, 3)))
        assert reporting.top_served_pairs([plan], limit=2) == [(3, 4, 5), (5, 6, 3)]


class TestIdleBusIds:
    def test_reports_buses_without_a_plan_in_fleet_order(self):
        buses = [make_bus(1), make_bus(4), make_bus(10)]
        assert reporting.idle_bus_ids(buses, [make_plan(bus_id=10)]) == [1, 4]

    def test_no_idle_bus_when_every_one_formed_a_route(self):
        assert reporting.idle_bus_ids([make_bus(1)], [make_plan(bus_id=1)]) == []


class TestPairsPreview:
    def test_renders_every_pair_when_under_the_limit(self):
        pairs = [(1, 2, 3), (4, 5, 1)]
        assert reporting.pairs_preview(pairs) == "1→2=3, 4→5=1"

    def test_truncates_and_marks_the_overflow_on_request(self):
        pairs = [(index, index + 1, index) for index in range(1, 5)]
        assert reporting.pairs_preview(pairs, limit=2) == "1→2=1, 2→3=2"
        assert (
            reporting.pairs_preview(pairs, limit=2, overflow_suffix=True)
            == "1→2=1, 2→3=2 (+2 pairs)"
        )

    def test_overflow_suffix_stays_away_when_nothing_is_hidden(self):
        assert reporting.pairs_preview([(1, 2, 1)], overflow_suffix=True) == "1→2=1"


class TestRouteAndTotalsLines:
    def test_pair_label_shows_the_locked_pair(self):
        assert reporting.pair_label(make_plan(origin=3, destination=7)) == "3 → 7"

    def test_route_line_lists_the_stops_in_order(self):
        plan = make_plan(stops=(3, 5, 5, 7))
        assert reporting.route_line(plan) == "bus 1 (3 → 7): 3 -> 5 -> 5 -> 7"

    def test_fleet_totals_line_counts_buses_and_passengers(self):
        data = make_data({(3, 7): 4, (1, 2): 6})
        line = reporting.fleet_totals_line([make_plan()], [make_bus(1), make_bus(2)], data)
        assert line == "1 of 2 buses · 4/10 pax (40%)"


class TestUnservedAndServedLines:
    def test_unserved_line_previews_the_demand_left_over(self):
        summary = FleetSummary(
            rounds=3,
            wins_per_bus=((1, 3),),
            unserved_passengers=6,
            unserved_pairs=((5, 6, 4), (7, 8, 2)),
        )
        assert reporting.unserved_line(summary) == "Unserved (6 pax): 5→6=4, 7→8=2"

    def test_unserved_line_is_empty_when_everything_was_served(self):
        summary = FleetSummary(
            rounds=3, wins_per_bus=((1, 3),), unserved_passengers=0, unserved_pairs=()
        )
        assert reporting.unserved_line(summary) == ""

    def test_served_pairs_line_prints_every_aggregated_pair(self):
        pairs = tuple((index, index + 1, 2) for index in range(1, 6))
        plan = make_plan(served_pairs=pairs)
        assert reporting.served_pairs_line([plan]) == (
            "Most served pairs: 1→2=2, 2→3=2, 3→4=2, 4→5=2, 5→6=2"
        )

    def test_served_pairs_line_sums_the_same_pair_across_buses(self):
        plans = [
            make_plan(served_pairs=((1, 2, 3),)),
            make_plan(bus_id=2, served_pairs=((1, 2, 4),)),
        ]
        assert reporting.served_pairs_line(plans) == "Most served pairs: 1→2=7"

    def test_served_pairs_line_is_empty_when_nothing_was_served(self):
        assert reporting.served_pairs_line([make_plan(served_pairs=())]) == ""


def test_lines_return_empty_strings_instead_of_none():
    """Both front ends test the result for truthiness before printing."""
    summary = FleetSummary(
        rounds=0, wins_per_bus=(), unserved_passengers=0, unserved_pairs=()
    )
    assert reporting.unserved_line(summary) == ""
    assert reporting.served_pairs_line([]) == ""
    assert reporting.served_pairs_line([make_plan(served_pairs=())]) == ""
