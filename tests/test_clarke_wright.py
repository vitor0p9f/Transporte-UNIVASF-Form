"""Clarke-Wright OVRP tests: route measures, restriction keys and evaluation."""

import numpy as np
import pytest

from algorithms.clarke_wright import (
    Attendance,
    BusModel,
    Context,
    Restrictions,
    Route,
    Saving,
    _best_direction,
    _merge,
    _route_distance,
    _route_time,
    _shift_10,
    _swap_11,
    _update_cost,
    build_context,
    build_stop_loads,
    clarke_wright_ovrp,
    compute_savings_ovrp,
    detect_sense,
    evaluate_attendance,
    limit_fleet,
    plans_and_summary,
    solve_scenario,
)
from tests import factories
from utils.fleet import load_fleet, parse_fleet_ids
from utils.instances import InstanceData
from utils.scenarios import load_scenarios

DEPOT = 1


def linear_data(demand: dict | None = None, size: int = 6) -> InstanceData:
    """Straight line 1-2-...-size: distance = |a-b| km, time = 10 min per km."""
    nodes = list(range(1, size + 1))
    distance = np.zeros((size + 1, size + 1), dtype=float)
    time = np.zeros((size + 1, size + 1), dtype=int)
    for a in nodes:
        for b in nodes:
            if a != b:
                distance[a, b] = abs(a - b)
                time[a, b] = 10 * abs(a - b)
    demand_matrix = np.zeros((size + 1, size + 1), dtype=int)
    for (origin, destination), quantity in (demand or {}).items():
        demand_matrix[origin, destination] = quantity
    return InstanceData(nodes=nodes, distance=distance, time=time, demand=demand_matrix)


def manual_data(
    distance: dict, time: dict, size: int = 6
) -> InstanceData:
    """Instance with the edges exactly as given (asymmetric matrices)."""
    return factories.make_data(time=time, distance=distance, size=size)


def bus_model(capacity=10) -> BusModel:
    return BusModel(
        name="test", capacity=capacity, km_per_liter=4.0, diesel_price=8.0
    )


def make_context(
    data: InstanceData,
    *,
    capacity: int = 10,
    max_time: float = float("inf"),
    restrictions: str = "ambas",
    stop_loads: dict | None = None,
    depot: int = DEPOT,
    max_routes: int | None = None,
) -> Context:
    if stop_loads is None:
        stop_loads, _ = build_stop_loads(data.demand, depot)
    return Context(
        distance=data.distance.astype(float, copy=False),
        time=data.time,
        depot=depot,
        capacity=capacity,
        max_time=max_time,
        bus_model=bus_model(capacity),
        stop_loads=stop_loads,
        demand=data.demand,
        restrictions=Restrictions.from_key(restrictions),
        max_routes=max_routes,
    )


class TestRestrictionKeys:
    def test_all_four_keys(self):
        assert Restrictions.from_key("capacidade") == Restrictions(True, False)
        assert Restrictions.from_key("tempo") == Restrictions(False, True)
        assert Restrictions.from_key("ambas") == Restrictions(True, True)
        assert Restrictions.from_key("nenhuma") == Restrictions(False, False)

    @pytest.mark.parametrize("key", ["capacidade", "tempo", "ambas", "nenhuma"])
    def test_key_round_trip(self, key):
        assert Restrictions.from_key(key).key == key

    def test_unknown_key_lists_the_options(self):
        with pytest.raises(ValueError, match="capacidade"):
            Restrictions.from_key("distancia")

    @pytest.mark.parametrize(
        "key,capacity,max_time,passengers,minutes,expected",
        [
            ("capacidade", 10, 5, 99, 999, False),
            ("capacidade", 100, 5, 99, 999, True),
            ("tempo", 10, 5, 99, 999, False),
            ("tempo", 10, 1000, 99, 999, True),
            ("ambas", 10, 5, 1, 1, True),
            ("nenhuma", 1, 1, 99, 999, True),
        ],
    )
    def test_fits_only_checks_the_active_restriction(
        self, key, capacity, max_time, passengers, minutes, expected
    ):
        # load 99 and time 999 break both limits, so only the active key matters
        ctx = make_context(
            linear_data(), restrictions=key, capacity=capacity, max_time=max_time
        )
        assert ctx.fits(passengers, minutes) is expected

    def test_no_time_limit_makes_the_time_restriction_inert(self):
        data = linear_data()
        ctx = make_context(data, restrictions="tempo", max_time=float("inf"))
        assert ctx.fits(999, 10_000) is True


class TestRouteMeasures:
    def test_distance_and_time_sum_the_legs_from_the_depot(self):
        ctx = make_context(linear_data())
        assert _route_distance([2, 4, 5], ctx) == 1 + 2 + 1
        assert _route_time([2, 4, 5], ctx) == 10 + 20 + 10

    def test_empty_route_measures_zero(self):
        ctx = make_context(linear_data())
        assert _route_distance([], ctx) == 0.0
        assert _route_time([], ctx) == 0

    def test_update_cost_fills_the_time(self):
        ctx = make_context(linear_data())
        route = _update_cost(Route(stops=[2, 4]), ctx)
        assert route.time_minutes == 30
        assert route.distance_km == 3.0
        assert route.cost_brl == pytest.approx(3.0 * 2.0)

    def test_best_direction_picks_the_shortest_without_restriction(self):
        ctx = make_context(linear_data(), restrictions="capacidade")
        assert _best_direction([5, 2], ctx) == [2, 5]

    def test_best_direction_ignores_time_when_the_key_does_not_ask(self):
        # forward is shorter (11 km) and slower (120 min); reverse is the opposite
        data = manual_data(
            distance={(1, 4): 10, (4, 2): 1, (1, 2): 1, (2, 4): 40},
            time={(1, 4): 60, (4, 2): 60, (1, 2): 1, (2, 4): 1},
        )
        ctx = make_context(data, restrictions="capacidade")
        assert _best_direction([4, 2], ctx) == [4, 2]

    def test_best_direction_prefers_the_direction_that_fits_the_time(self):
        data = manual_data(
            distance={(1, 4): 10, (4, 2): 1, (1, 2): 1, (2, 4): 40},
            time={(1, 4): 60, (4, 2): 60, (1, 2): 1, (2, 4): 1},
        )
        ctx = make_context(data, restrictions="tempo", max_time=10)
        assert _best_direction([4, 2], ctx) == [2, 4]


class TestStopLoads:
    def test_static_load_includes_pickups_and_dropoffs_in_both_senses(self):
        data = linear_data({(2, 3): 4, (4, 3): 2, (1, 5): 9})
        outbound, _ = build_stop_loads(data.demand, DEPOT, sense="ida")
        inbound, _ = build_stop_loads(data.demand, DEPOT, sense="volta")
        assert outbound == {1: 9, 2: 4, 3: 6, 4: 2, 5: 9}
        assert inbound == outbound

    def test_campus_nodes_are_active_when_they_have_demand(self):
        data = linear_data({(1, 5): 3})
        load, _ = build_stop_loads(data.demand, DEPOT, sense="ida")
        assert load == {1: 3, 5: 3}

    def test_auto_detects_inbound_when_the_depot_concentrates_boardings(self):
        data = linear_data({(DEPOT, 3): 10, (3, DEPOT): 1})
        assert detect_sense(data.demand, DEPOT) == "volta"

    def test_auto_detects_outbound_when_the_depot_concentrates_alightings(self):
        data = linear_data({(3, DEPOT): 10, (DEPOT, 3): 1})
        assert detect_sense(data.demand, DEPOT) == "ida"

    def test_invalid_sense_fails(self):
        data = linear_data()
        with pytest.raises(ValueError, match="sentido"):
            build_stop_loads(data.demand, DEPOT, sense="lado")


class TestMergeUnderRestrictions:
    """`_merge` only blocks the merge when the requested restriction is active."""

    def make(self, restrictions: str, capacity=10, max_time=float("inf")):
        data = linear_data()
        return make_context(
            data,
            capacity=capacity,
            max_time=max_time,
            restrictions=restrictions,
            stop_loads={2: 6, 3: 3},
        )

    @staticmethod
    def merge(ctx: Context) -> list[list[int]]:
        merged = _merge([Saving(2, 3, 10.0)], {2, 3}, ctx)
        return sorted(route.stops for route in merged)

    def test_active_capacity_blocks_it(self):
        ctx = self.make("capacidade", capacity=8)  # 6 + 3 > 8
        assert self.merge(ctx) == [[2], [3]]

    def test_capacity_off_allows_it(self):
        ctx = self.make("tempo", capacity=8)  # 1 -> 2 -> 3 = 20 min
        assert self.merge(ctx) == [[2, 3]]

    def test_active_time_blocks_it(self):
        ctx = self.make("tempo", max_time=15)  # 1 -> 2 -> 3 = 20 min
        assert self.merge(ctx) == [[2], [3]]

    def test_time_off_allows_it(self):
        ctx = self.make("capacidade", max_time=5)
        assert self.merge(ctx) == [[2, 3]]

    def test_both_active_require_both(self):
        ctx = self.make("ambas", capacity=8, max_time=5)
        assert self.merge(ctx) == [[2], [3]]
        ctx = self.make("ambas", capacity=8, max_time=100)
        assert self.merge(ctx) == [[2], [3]]  # the capacity still breaks
        ctx = self.make("ambas", capacity=100, max_time=100)
        assert self.merge(ctx) == [[2, 3]]

    def test_no_restriction_always_merges(self):
        ctx = self.make("nenhuma", capacity=1, max_time=1)
        assert self.merge(ctx) == [[2, 3]]

    def test_merged_route_leaves_with_its_time_measured(self):
        ctx = self.make("nenhuma")
        (route,) = _merge([Saving(2, 3, 10.0)], {2, 3}, ctx)
        assert route.time_minutes == _route_time(route.stops, ctx)


class TestLocalSearchUnderRestrictions:
    """No CW-3 operator returns a route over the time when its key is active."""

    def make_fixture(self):
        data = linear_data()
        return data, make_context(
            data,
            capacity=20,
            max_time=40,
            restrictions="tempo",
            stop_loads={2: 2, 3: 2, 4: 2, 5: 2},
        )

    def initial_routes(self, ctx):
        return [
            _update_cost(Route(stops=[2, 3], load=4), ctx),
            _update_cost(Route(stops=[4, 5], load=4), ctx),
        ]

    def test_shift_never_creates_a_route_over_the_time(self):
        _, ctx = self.make_fixture()
        routes = _shift_10(self.initial_routes(ctx), ctx)
        assert all(r.time_minutes <= ctx.max_time for r in routes)

    def test_swap_never_creates_a_route_over_the_time(self):
        _, ctx = self.make_fixture()
        routes = _swap_11(self.initial_routes(ctx), ctx)
        assert all(r.time_minutes <= ctx.max_time for r in routes)

    def test_shift_respects_the_capacity_when_active(self):
        data = linear_data()
        ctx = make_context(
            data,
            capacity=4,
            restrictions="capacidade",
            stop_loads={2: 2, 3: 2, 4: 2, 5: 2},
        )
        routes = _shift_10(self.initial_routes(ctx), ctx)
        assert all(r.load <= ctx.capacity for r in routes)


class TestFullAlgorithm:
    def test_deterministic_with_the_same_seed(self):
        data = linear_data({(2, 6): 3, (3, 6): 4, (4, 6): 3, (5, 6): 2})
        ctx = make_context(data, capacity=6, max_time=200)
        first, lam1 = clarke_wright_ovrp(
            ctx, iterations=5, post_improvement_iterations=2, seed=7, verbose=False
        )
        second, lam2 = clarke_wright_ovrp(
            ctx, iterations=5, post_improvement_iterations=2, seed=7, verbose=False
        )
        assert lam1 == lam2
        assert [r.stops for r in first] == [r.stops for r in second]

    @pytest.mark.parametrize(
        "restrictions,capacity,limit",
        [
            ("capacidade", 6, 5),
            ("tempo", 1000, 40),
            ("ambas", 6, 40),
            ("nenhuma", 1, 1),
        ],
    )
    def test_every_key_restriction_holds(self, restrictions, capacity, limit):
        data = linear_data({(2, 6): 3, (3, 6): 4, (4, 6): 3, (5, 6): 2})
        ctx = make_context(
            data, capacity=capacity, max_time=limit, restrictions=restrictions
        )
        routes, _ = clarke_wright_ovrp(
            ctx, iterations=20, post_improvement_iterations=5, seed=1, verbose=False
        )
        assert routes
        if ctx.restrictions.capacity:
            assert all(r.load <= capacity for r in routes)
        if ctx.restrictions.time:
            assert all(r.time_minutes <= limit for r in routes)

    def test_no_demand_builds_no_route(self):
        data = linear_data()
        ctx = make_context(data, capacity=6)
        assert clarke_wright_ovrp(ctx, verbose=False) == ([], 0.0)

    def test_savings_use_the_ovrp_formula(self):
        ctx = make_context(linear_data())
        savings = compute_savings_ovrp([2, 3], ctx, lam=0.5)
        # s(2,3) = c(depot,3) - 0.5 * c(2,3) = 2 - 0.5*1
        assert savings[0].value == pytest.approx(1.5)
        assert (savings[0].i, savings[0].j) == (2, 3)


class TestBuildContext:
    def test_no_limit_reports_infinity(self):
        ctx = build_context(linear_data(), DEPOT, capacity=10)
        assert ctx.max_time == float("inf")
        assert ctx.restrictions.key == "ambas"

    def test_capacity_comes_from_the_model_when_omitted(self):
        ctx = build_context(linear_data(), DEPOT, bus_model=bus_model(37))
        assert ctx.capacity == 37

    def test_key_as_string_is_accepted(self):
        ctx = build_context(linear_data(), DEPOT, restrictions="tempo")
        assert ctx.restrictions == Restrictions(time=True, capacity=False)

    def test_sense_is_recorded_in_the_context(self):
        data = linear_data({(2, 3): 4})
        ctx = build_context(data, DEPOT, capacity=10, sense="volta")
        assert ctx.sense == "volta"
        assert ctx.stop_loads == {2: 4, 3: 4}


class TestAttendanceEvaluation:
    """The simulation only measures: no decision may depend on it."""

    def test_full_pair_counts_and_fills_the_route(self):
        ctx = make_context(linear_data({(2, 4): 1}), capacity=10)
        route = Route(stops=[2, 3, 4], load=3)

        attendance = evaluate_attendance([route], ctx)

        assert (route.passengers, route.peak_load) == (1, 1)
        assert route.pairs == ((2, 4, 1),)
        assert attendance.served == 1
        assert attendance.total_demand == 1
        assert attendance.unserved == 0
        assert attendance.served_pct == pytest.approx(100.0)
        assert attendance.allocated == 3

    def test_origin_without_destination_on_the_route_does_not_count(self):
        ctx = make_context(linear_data({(2, 5): 1}))
        route = Route(stops=[2, 3, 4], load=1)

        evaluate_attendance([route], ctx)

        assert route.passengers == 0
        assert route.pairs == ()

    def test_destination_before_origin_does_not_count(self):
        ctx = make_context(linear_data({(4, 2): 1}))
        route = Route(stops=[2, 3, 4], load=1)

        evaluate_attendance([route], ctx)

        assert route.passengers == 0

    def test_the_depot_is_the_first_simulated_stop(self):
        ctx = make_context(linear_data({(1, 3): 1}))
        route = Route(stops=[3, 4], load=1)

        evaluate_attendance([route], ctx)

        assert route.passengers == 1

    def test_sequential_charging_does_not_count_the_pair_twice(self):
        ctx = make_context(linear_data({(2, 4): 1}))
        r1 = Route(stops=[2, 4], load=2)
        r2 = Route(stops=[2, 4], load=2)

        attendance = evaluate_attendance([r1, r2], ctx)

        assert (r1.passengers, r2.passengers) == (1, 0)
        assert attendance.served == 1

    def test_capacity_caps_the_boarding_and_leaves_demand_behind(self):
        ctx = make_context(linear_data({(2, 5): 3}), capacity=2)
        route = Route(stops=[2, 5], load=3)

        attendance = evaluate_attendance([route], ctx)

        assert route.passengers == 2
        assert route.peak_load == 2
        assert attendance.unserved == 1

    def test_peak_is_the_highest_simultaneous_occupancy(self):
        # 2->5 and 3->6 share the 3->5 leg: two passengers on board at once
        ctx = make_context(linear_data({(2, 5): 1, (3, 6): 1}), capacity=10)
        route = Route(stops=[2, 3, 5, 6], load=2)

        evaluate_attendance([route], ctx)

        assert route.passengers == 2
        assert route.peak_load == 2

    def test_empty_route_does_not_break(self):
        ctx = make_context(linear_data({(2, 4): 1}))
        route = Route(stops=[], load=0)

        attendance = evaluate_attendance([route], ctx)

        assert (route.passengers, route.peak_load, route.pairs) == (0, 0, ())
        assert attendance.served == 0

    def test_evaluation_does_not_change_the_decisions(self):
        ctx = make_context(linear_data({(2, 4): 1, (3, 5): 1}), capacity=10)
        routes, _ = clarke_wright_ovrp(
            ctx, iterations=5, post_improvement_iterations=2, seed=3, verbose=False
        )
        stops_before = [list(r.stops) for r in routes]
        loads_before = [r.load for r in routes]

        evaluate_attendance(routes, ctx)

        assert [list(r.stops) for r in routes] == stops_before
        assert [r.load for r in routes] == loads_before

    def test_no_demand_means_zero_percentages(self):
        attendance = Attendance(
            total_demand=0, allocated=0, served=0, unserved=0, peak_load=0
        )

        assert attendance.allocated_pct == 0.0
        assert attendance.served_pct == 0.0

    def test_unserved_pairs_keep_the_remaining_demand(self):
        ctx = make_context(linear_data({(2, 5): 3, (3, 5): 1}), capacity=10)
        route = Route(stops=[2, 3], load=4)

        attendance = evaluate_attendance([route], ctx)

        # the route never visits 5: nobody boards, and both pairs stay behind
        assert attendance.served == 0
        assert attendance.unserved_pairs == ((2, 5, 3), (3, 5, 1))


class TestFleetLimit:
    def test_no_cap_is_a_no_op(self):
        ctx = make_context(linear_data({(2, 4): 1}), capacity=10)
        routes = [Route(stops=[2, 4], load=1), Route(stops=[3, 5], load=1)]

        assert limit_fleet(routes, ctx) == routes

    def test_a_solution_that_already_fits_is_untouched(self):
        ctx = make_context(linear_data({(2, 4): 1}), capacity=10, max_routes=2)
        routes = [Route(stops=[2, 4], load=1), Route(stops=[3, 5], load=1)]

        assert limit_fleet(routes, ctx) == routes

    def test_drops_the_routes_that_serve_the_least(self):
        ctx = make_context(
            linear_data({(2, 5): 4, (3, 6): 1}), capacity=10, max_routes=1
        )
        full = Route(stops=[2, 5], load=4)
        spare = Route(stops=[3, 6], load=1)

        assert limit_fleet([spare, full], ctx) == [full]

    def test_solving_never_returns_more_routes_than_the_fleet(self, root):
        scenario = next(
            s for s in load_scenarios(root) if str(s["scenario_id"]) == "54"
        )
        buses = load_fleet(
            root / "fleet.csv", parse_fleet_ids(scenario["fleet_bus_ids"])
        )
        # Scenario 54 is the known case: pure CW-1 builds more routes than
        # buses (9 for 5); the cap cuts them before the evaluation.
        _data, routes, ctx, _attendance, _lam = solve_scenario(
            scenario,
            restrictions="tempo",
            lam=1.0,
            use_two_phase=False,
            use_post_improvement=False,
            seed=42,
        )

        assert ctx.max_routes == len(buses)
        assert len(routes) <= len(buses)

    def test_a_partially_served_pair_keeps_what_is_left(self):
        ctx = make_context(linear_data({(2, 5): 3}), capacity=2)
        route = Route(stops=[2, 5], load=3)

        attendance = evaluate_attendance([route], ctx)

        assert attendance.served_pairs == ((2, 5, 2),)
        assert attendance.unserved_pairs == ((2, 5, 1),)


class TestPlansAndSummary:
    """The conversion of the CW solution into the model `reporting` reads."""

    @staticmethod
    def make_bus(bus_id: int):
        return factories.make_bus(bus_id, capacity=24, fuel_capacity=150.0)

    def test_route_becomes_a_plan_with_the_depot_first(self):
        ctx = make_context(linear_data({(2, 4): 1}), capacity=10)
        route = Route(stops=[2, 4], load=2)
        attendance = evaluate_attendance([route], ctx)

        plans, summary = plans_and_summary([route], ctx, attendance, [self.make_bus(1)])

        assert len(plans) == 1
        assert plans[0].stops == (1, 2, 4)
        assert plans[0].origin == 1
        assert plans[0].destination == 4
        assert plans[0].served_passengers == 1
        assert plans[0].peak_load == 1
        assert plans[0].served_pairs == ((2, 4, 1),)
        assert summary.unserved_passengers == 0
        assert summary.unserved_pairs == ()

    def test_fleet_ids_follow_the_route_order(self):
        ctx = make_context(linear_data({(2, 4): 1, (3, 5): 1}), capacity=10)
        routes = [Route(stops=[2, 4], load=1), Route(stops=[3, 5], load=1)]
        attendance = evaluate_attendance(routes, ctx)

        plans, _ = plans_and_summary(
            routes, ctx, attendance, [self.make_bus(7), self.make_bus(9)]
        )

        assert [plan.bus_id for plan in plans] == [7, 9]

    def test_route_beyond_the_fleet_gets_a_sequential_id(self):
        ctx = make_context(linear_data({(2, 4): 1}), capacity=10)
        route = Route(stops=[2, 4], load=1)
        attendance = evaluate_attendance([route], ctx)

        plans, _ = plans_and_summary([route], ctx, attendance, [])

        assert [plan.bus_id for plan in plans] == [1]

    def test_summary_carries_the_demand_left_behind(self):
        ctx = make_context(linear_data({(2, 5): 3}), capacity=2)
        route = Route(stops=[2, 5], load=3)
        attendance = evaluate_attendance([route], ctx)

        _, summary = plans_and_summary([route], ctx, attendance, [self.make_bus(1)])

        assert summary.unserved_passengers == 1
        assert summary.unserved_pairs == ((2, 5, 1),)
