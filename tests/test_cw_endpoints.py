"""Regression coverage for scenario origin and destination constraints."""

import numpy as np
import pytest

from algorithms import clarke_wright as cw
from algorithms.clarke_wright import scenario as scenario_module
from tests.factories import make_bus
from utils.instances import InstanceData
from utils.paths import path_distance, path_time_minutes
from utils.scenarios import load_scenarios, parse_node_labels


def line_data(demand=None, size=6):
    nodes = list(range(1, size + 1))
    distance = np.zeros((size + 1, size + 1), dtype=float)
    for a in nodes:
        for b in nodes:
            distance[a, b] = abs(a - b)
    quantities = np.zeros_like(distance, dtype=int)
    for (origin, destination), quantity in (demand or {}).items():
        quantities[origin, destination] = quantity
    return InstanceData(nodes, distance, distance.astype(int), quantities)


def synthetic_scenario(monkeypatch, data, origins="1;6", destinations="3;4", **values):
    monkeypatch.setattr(scenario_module, "load_instance_data", lambda *a, **k: data)
    monkeypatch.setattr(
        scenario_module, "_scenario_fleet",
        lambda *a, **k: [make_bus(1, capacity=1), make_bus(2, capacity=1)],
    )
    return {
        "instance_id": "synthetic", "period": "morning_1",
        "origin": origins, "destination_labels": destinations,
        "max_time_limit": 100, **values,
    }


def fast_solve(scenario, **kwargs):
    return cw.solve_scenario(
        scenario, lam=1.0, use_two_phase=False,
        use_post_improvement=False, **kwargs,
    )


def assert_plan_geometry(plans, data, origins, destinations, limit, capacity):
    assert plans, "The endpoint constraints must not be satisfied by dropping every route"
    for plan in plans:
        assert plan.origin in origins
        assert plan.destination in destinations
        assert plan.stops[0] == plan.origin
        assert plan.stops[-1] == plan.destination
        assert plan.travel_time_minutes == path_time_minutes(data.time, plan.stops)
        assert plan.travel_time_minutes <= limit
        assert plan.peak_load <= capacity


def test_scenario_uses_both_origins_and_both_destinations(monkeypatch):
    data = line_data({(2, 3): 1, (5, 6): 1})
    scenario = synthetic_scenario(monkeypatch, data, destinations="3;6")
    data, routes, ctx, attendance, _ = fast_solve(scenario)
    plans, _ = cw.plans_and_summary(routes, ctx, attendance)

    assert {p.origin for p in plans} == {1, 6}
    assert {p.destination for p in plans} == {3, 6}
    assert attendance.served == 2
    assert_plan_geometry(plans, data, {1, 6}, {3, 6}, 100, 1)


def test_scenario_prices_the_driver(monkeypatch):
    data = line_data({(2, 3): 1})
    scenario = synthetic_scenario(monkeypatch, data, driver_hourly_rate="45.0")
    _, routes, ctx, _, _ = fast_solve(scenario)

    assert ctx.bus_model.driver_hourly_rate == pytest.approx(45.0)
    assert routes
    for route in routes:
        fuel = route.distance_km * ctx.bus_model.cost_per_km
        driver = route.time_minutes / 60 * 45.0
        assert route.cost_brl == pytest.approx(fuel + driver)


def test_a_single_allowed_destination_is_really_visited(monkeypatch):
    data = line_data({(2, 6): 1})
    scenario = synthetic_scenario(monkeypatch, data, origins="1", destinations="6")
    data, routes, ctx, attendance, _ = fast_solve(scenario)
    plans, _ = cw.plans_and_summary(routes, ctx, attendance)

    assert attendance.served == 1
    assert plans[0].stops == (1, 2, 6)
    assert routes[0].distance_km == path_distance(data.distance, plans[0].stops)
    assert_plan_geometry(plans, data, {1}, {6}, 100, 1)


def test_terminal_leg_can_make_a_route_infeasible(monkeypatch):
    data = line_data({(2, 6): 1})
    scenario = synthetic_scenario(
        monkeypatch, data, origins="1", destinations="6", max_time_limit=3,
    )
    _, routes, _, attendance, _ = fast_solve(scenario)
    assert routes == []  # 1 -> 2 fits, but 1 -> 2 -> 6 takes five minutes
    assert attendance.served == 0
    assert attendance.unserved == 1


def test_origin_and_destination_may_be_the_same(monkeypatch):
    data = line_data({(2, 1): 1})
    scenario = synthetic_scenario(monkeypatch, data, origins="1", destinations="1")
    data, routes, ctx, attendance, _ = fast_solve(scenario)
    plans, _ = cw.plans_and_summary(routes, ctx, attendance)
    assert plans[0].stops == (1, 2, 1)
    assert attendance.served == 1
    assert_plan_geometry(plans, data, {1}, {1}, 100, 1)


def test_endpoint_list_order_does_not_choose_a_different_solution(monkeypatch):
    data = line_data({(2, 3): 1, (5, 4): 1})
    outcomes = []
    for origins, destinations in [("1;6", "3;4"), ("6;1", "4;3")]:
        scenario = synthetic_scenario(monkeypatch, data, origins, destinations)
        _, routes, ctx, attendance, _ = fast_solve(scenario)
        plans, _ = cw.plans_and_summary(routes, ctx, attendance)
        outcomes.append((sorted(p.stops for p in plans), attendance.served))
    assert outcomes[0] == outcomes[1]


def test_explicit_depot_overrides_the_origin_list(monkeypatch):
    data = line_data({(2, 3): 1, (5, 4): 1})
    scenario = synthetic_scenario(monkeypatch, data)
    _, routes, ctx, attendance, _ = fast_solve(scenario, depot=1)
    plans, _ = cw.plans_and_summary(routes, ctx, attendance)
    assert {p.origin for p in plans} == {1}
    assert {p.destination for p in plans} <= {3, 4}


def test_more_distant_origin_is_used_when_the_closest_is_too_slow(monkeypatch):
    data = line_data({(2, 4): 1})
    data.time[1, 2] = 90
    data.time[6, 2] = 2
    scenario = synthetic_scenario(
        monkeypatch, data, destinations="4", max_time_limit=10,
    )
    data, routes, ctx, attendance, _ = fast_solve(scenario)
    plans, _ = cw.plans_and_summary(routes, ctx, attendance)
    assert plans[0].origin == 6
    assert_plan_geometry(plans, data, {1, 6}, {4}, 10, 1)


def test_more_distant_destination_is_used_when_the_closest_is_too_slow(monkeypatch):
    data = line_data({(2, 6): 1})
    data.time[2, 3] = 90
    scenario = synthetic_scenario(
        monkeypatch, data, origins="1", destinations="3;6", max_time_limit=10,
    )
    data, routes, ctx, attendance, _ = fast_solve(scenario)
    plans, _ = cw.plans_and_summary(routes, ctx, attendance)
    assert plans[0].destination == 6
    assert attendance.served == 1
    assert_plan_geometry(plans, data, {1}, {3, 6}, 10, 1)


def test_an_endpoint_already_in_the_stop_order_is_not_duplicated():
    data = line_data({(2, 3): 1})
    ctx = cw.build_context(data, 2, origins=(2, 6), destinations=(3,))
    route = cw._update_cost(cw.Route(stops=[2, 3], load=1), ctx)
    attendance = cw.evaluate_attendance([route], ctx)
    plans, _ = cw.plans_and_summary([route], ctx, attendance)
    assert plans[0].stops == (2, 3)
    assert plans[0].travel_time_minutes == 1
    assert attendance.served == 1


@pytest.mark.parametrize("field", ["origins", "destinations"])
@pytest.mark.parametrize("labels", [(), (0,), (7,)])
def test_invalid_endpoint_labels_are_rejected(field, labels):
    with pytest.raises(ValueError, match=field):
        cw.build_context(line_data(), 1, **{field: labels})


def test_scenario_without_destination_filter_keeps_an_open_end(monkeypatch):
    data = line_data({(2, 6): 1})
    scenario = synthetic_scenario(monkeypatch, data, origins="1", destinations="")
    _, routes, ctx, attendance, _ = fast_solve(scenario)
    plans, _ = cw.plans_and_summary(routes, ctx, attendance)

    # No terminal is forced beyond the stops: node 6 is a stop here because the
    # passenger gets off there, and the open route ends at its last stop.
    assert ctx.destinations is None
    assert plans[0].stops == (1, 2, 6)
    assert attendance.served == 1


def test_savings_include_the_terminal_leg():
    data = line_data()
    ctx = cw.build_context(data, 1, origins=(1,), destinations=(6,))
    saving, = cw.compute_savings_ovrp([2, 4], ctx, lam=1.0)
    # Each singleton drives five units; their merged route also drives five.
    # No driver is priced here, so the cost is the distance times R$/km.
    assert saving.value == pytest.approx((5 + 5 - 5) * ctx.bus_model.cost_per_km)


def test_printed_and_saved_routes_include_the_permitted_terminal(monkeypatch, tmp_path, capsys):
    import json

    from algorithms.clarke_wright import report as report_module

    data = line_data({(2, 6): 1})
    scenario = synthetic_scenario(monkeypatch, data, origins="1", destinations="6")
    _, routes, ctx, attendance, lam = fast_solve(scenario)
    cw.print_solution(routes, ctx, "endpoint regression", lam, attendance)
    assert "1 -> 2 -> 6" in capsys.readouterr().out

    (tmp_path / 'algorithms').mkdir()
    monkeypatch.setattr(report_module, "ROOT", tmp_path)
    cw.save_result(routes, ctx, "endpoint regression", lam, attendance)
    payload = json.loads(next((tmp_path / 'algorithms/output').glob('*.json')).read_text(encoding='utf-8'))
    route, = payload['rotas']
    assert route['percurso'] == [1, 2, 6]
    assert (route['origem'], route['destino']) == (1, 6)
    assert route['tempo_min'] == 5


def test_all_stored_scenarios_have_no_illegal_returned_endpoints(root):
    checked = 0
    for scenario in load_scenarios(root):
        data, routes, ctx, attendance, _ = fast_solve(scenario)
        plans, _ = cw.plans_and_summary(routes, ctx, attendance)
        origins = set(parse_node_labels(scenario['origin']))
        destinations = set(parse_node_labels(scenario['destination_labels']))
        for route, plan in zip(routes, plans):
            assert plan.origin in origins, scenario['scenario_id']
            assert plan.destination in destinations, scenario['scenario_id']
            assert plan.travel_time_minutes == path_time_minutes(data.time, plan.stops)
            assert plan.travel_time_minutes <= int(scenario['max_time_limit'])
            assert plan.peak_load <= ctx.capacity
            assert route.origin == plan.origin and route.destination == plan.destination
            assert route.distance_km == pytest.approx(path_distance(data.distance, plan.stops), abs=1e-4)
        assert len(plans) <= ctx.max_routes
        assert attendance.served + attendance.unserved == attendance.total_demand
        checked += len(plans)
    assert checked > 0


@pytest.mark.parametrize("scenario_id", ["16", "19", "32", "65", "69"])
@pytest.mark.parametrize("improve", [False, True], ids=["construction", "local-search"])
def test_real_report_scenarios_respect_endpoints_and_full_travel_time(root, scenario_id, improve):
    scenario = next(s for s in load_scenarios(root) if s["scenario_id"] == scenario_id)
    data, routes, ctx, attendance, _ = cw.solve_scenario(
        scenario, lam=1.0, use_two_phase=improve, iterations=3,
        use_post_improvement=improve, post_improvement_iterations=3,
    )
    plans, _ = cw.plans_and_summary(routes, ctx, attendance)
    assert_plan_geometry(
        plans, data, set(parse_node_labels(scenario['origin'])),
        set(parse_node_labels(scenario['destination_labels'])),
        int(scenario['max_time_limit']), ctx.capacity,
    )
    assert len(plans) <= ctx.max_routes
    assert attendance.served + attendance.unserved == attendance.total_demand
    for route, plan in zip(routes, plans):
        assert route.distance_km == pytest.approx(path_distance(data.distance, plan.stops), abs=1e-4)
