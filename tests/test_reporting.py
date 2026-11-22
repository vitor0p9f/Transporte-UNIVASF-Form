"""Unit tests for the renderer shared by main.py and scripts/run_all.py."""

from types import SimpleNamespace

import numpy as np
import pytest

import reporting
from tests.factories import make_bus, make_data, make_plan, make_summary


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
        summary = make_summary(
            unserved=6,
            wins_per_bus=((1, 3),),
            unserved_pairs=((5, 6, 4), (7, 8, 2)),
        )
        assert reporting.unserved_line(summary) == "Unserved (6 pax): 5→6=4, 7→8=2"

    def test_unserved_line_is_empty_when_everything_was_served(self):
        summary = make_summary(unserved=0, wins_per_bus=((1, 3),))
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


class TestRotaDeReferencia:
    """All route-level columns of a report row come from one route."""

    def test_is_the_longest_route_that_served_someone(self):
        plans = [
            make_plan(bus_id=1, travel_time_minutes=20),
            make_plan(
                bus_id=2, served_passengers=0, travel_time_minutes=50,
                peak_load=0,
            ),
            make_plan(bus_id=3, travel_time_minutes=35, peak_load=5),
        ]
        reference = reporting.reference_plan(plans)
        assert reference is not None
        assert reference.bus_id == 3
        assert (reference.travel_time_minutes, reference.peak_load) == (35, 5)

    def test_falls_back_to_the_longest_route_without_passengers(self):
        plans = [
            make_plan(bus_id=1, served_passengers=0, travel_time_minutes=10),
            make_plan(bus_id=2, served_passengers=0, travel_time_minutes=30),
        ]
        reference = reporting.reference_plan(plans)
        assert reference is not None
        assert reference.bus_id == 2

    def test_empty_fleet_has_no_reference(self):
        assert reporting.reference_plan([]) is None


class TestOccupancyAudit:
    def test_finds_global_peak_even_when_it_is_not_on_longest_route(self):
        plans = [
            make_plan(bus_id=1, travel_time_minutes=60, peak_load=8),
            make_plan(
                bus_id=2,
                stops=(4, 5, 6),
                travel_time_minutes=30,
                peak_load=19,
            ),
        ]

        audit = reporting.occupancy_audit(
            plans,
            [make_bus(1, capacity=24), make_bus(2, capacity=24)],
        )

        assert reporting.reference_plan(plans).bus_id == 1
        assert (audit.peak, audit.bus_id, audit.route, audit.capacity) == (
            19,
            2,
            (4, 5, 6),
            24,
        )
        assert not audit.has_violation

    def test_uses_physical_capacity_and_reports_worst_excess(self):
        plans = [
            make_plan(bus_id=1, stops=(1, 2), peak_load=40),
            make_plan(bus_id=2, stops=(3, 4), peak_load=35),
        ]

        audit = reporting.occupancy_audit(
            plans,
            [make_bus(1, capacity=50), make_bus(2, capacity=24)],
        )

        # The route with the largest absolute peak is not the violating route.
        assert (audit.peak, audit.bus_id, audit.capacity) == (40, 1, 50)
        assert audit.has_violation
        assert audit.violating_routes == 1
        assert audit.max_excess == 11
        assert audit.max_excess_bus_id == 2
        assert audit.max_excess_route == (3, 4)

    def test_empty_run_has_a_zero_audit(self):
        audit = reporting.occupancy_audit([], [make_bus(1, capacity=24)])
        assert (audit.peak, audit.capacity, audit.violating_routes) == (0, 0, 0)
        assert audit.bus_id is None
        assert audit.route == ()

    def test_rejects_a_plan_without_a_physical_bus(self):
        with pytest.raises(ValueError, match="bus.*2"):
            reporting.occupancy_audit(
                [make_plan(bus_id=2)],
                [make_bus(1, capacity=24)],
            )


def test_lines_return_empty_strings_instead_of_none():
    """Both front ends test the result for truthiness before printing."""
    summary = make_summary(rounds=0, wins_per_bus=())
    assert reporting.unserved_line(summary) == ""
    assert reporting.served_pairs_line([]) == ""
    assert reporting.served_pairs_line([make_plan(served_pairs=())]) == ""


class TestCustoOperacional:
    """Fuel + driver cost under one vehicle model, the same for both methods."""

    def test_distance_sums_consecutive_legs_including_the_depot(self):
        data = SimpleNamespace(distance=np.zeros((8, 8)))
        data.distance[1, 3] = 4.0
        data.distance[3, 7] = 6.0
        plan = make_plan(stops=(1, 3, 7))
        assert reporting.plan_distance_km(plan, data) == 10.0

    def test_distance_is_zero_for_a_route_without_a_leg(self):
        data = SimpleNamespace(distance=np.zeros((8, 8)))
        assert reporting.plan_distance_km(make_plan(stops=(1,)), data) == 0.0

    def test_cost_formula(self):
        """10 km / 4 km per liter * R$ 6 + 60 min / 60 * R$ 30 = R$ 45."""
        data = SimpleNamespace(distance=np.zeros((8, 8)))
        data.distance[1, 4] = 10.0
        plan = make_plan(stops=(1, 4), travel_time_minutes=60)
        cost = reporting.operational_cost(
            [plan],
            data,
            km_per_liter=4.0,
            diesel_price=6.0,
            driver_hourly_rate=30.0,
        )
        assert cost.distance_km == 10.0
        assert cost.liters == 2.5
        assert cost.fuel == 15.0
        assert cost.driver == 30.0
        assert cost.total == 45.0
        assert cost.per_passenger(4) == 11.25

    def test_routes_without_passengers_are_not_charged(self):
        """The CW can return a route that serves nobody; it is not operated."""
        data = SimpleNamespace(distance=np.zeros((8, 8)))
        data.distance[1, 3] = 4.0
        data.distance[3, 7] = 6.0
        empty = make_plan(
            bus_id=2,
            stops=(1, 3),
            served_passengers=0,
            travel_time_minutes=30,
        )
        loaded = make_plan(
            bus_id=1,
            stops=(1, 3, 7),
            served_passengers=4,
            travel_time_minutes=60,
        )
        cost = reporting.operational_cost(
            [empty, loaded],
            data,
            km_per_liter=4.0,
            diesel_price=6.0,
            driver_hourly_rate=30.0,
        )
        assert cost.distance_km == 10.0
        assert cost.liters == 2.5
        assert cost.driver == 30.0
        assert cost.total == 45.0

    def test_cost_per_passenger_is_zero_without_passengers(self):
        cost = reporting.OperationalCost(
            distance_km=0.0,
            liters=0.0,
            fuel=0.0,
            driver=0.0,
            diesel_price=6.0,
            driver_hourly_rate=30.0,
        )
        assert cost.per_passenger(0) == 0.0

    def test_distance_counts_repeated_nodes(self):
        """A route that revisits the depot (dobradinha) pays the leg again."""
        data = SimpleNamespace(distance=np.zeros((8, 8)))
        data.distance[1, 3] = 2.0
        data.distance[3, 1] = 2.0
        data.distance[1, 7] = 5.0
        plan = make_plan(stops=(1, 3, 1, 7))
        assert reporting.plan_distance_km(plan, data) == 9.0
