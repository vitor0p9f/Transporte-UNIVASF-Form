"""Unit tests for the real-fleet TOP runner.

Covers the scenario selection, the per-bus cost and the row rendering; the
solver itself is already covered by the other suites.
"""

import numpy as np
import pytest

from algorithms.top_univasf import BusPlan, FleetSummary
from entities.bus import Bus
from reporting import OperationalCost
from scripts.run_top_real_fleet import (
    PLAN_HEADERS,
    ScenarioRun,
    operational_cost,
    plan_cells,
    run_scenario,
    select_scenarios,
)
from utils.instances import InstanceData


def make_bus(bus_id: int, capacity: int = 24, km_per_liter: float = 4.0) -> Bus:
    return Bus(bus_id, capacity, 100.0, km_per_liter)


def make_plan(
    bus_id: int, stops: tuple[int, ...], served: int = 4, minutes: int = 10
) -> BusPlan:
    return BusPlan(
        bus_id=bus_id,
        origin=stops[0],
        destination=stops[-1],
        stops=stops,
        served_passengers=served,
        travel_time_minutes=minutes,
        peak_load=3,
        score=0.2,
        served_pairs=((stops[0], stops[-1], served),),
    )


def make_data(distances: dict[tuple[int, int], float]) -> InstanceData:
    """Synthetic instance: only the distance matrix is read by the cost."""
    distance = np.zeros((4, 4))
    for (origin, destination), value in distances.items():
        distance[origin, destination] = value
    return InstanceData(
        nodes=[1, 2, 3],
        distance=distance,
        time=np.zeros((4, 4), dtype=int),
        demand=np.zeros((4, 4), dtype=int),
    )


def make_run(buses: list[Bus], plans: list[BusPlan], data: InstanceData) -> ScenarioRun:
    return ScenarioRun(
        scenario={
            "scenario_id": "1",
            "instance_id": "fixture",
            "period": "morning_1",
            "fleet_bus_ids": ";".join(str(bus.id) for bus in buses),
            "max_time_limit": "100",
            "diesel_price_per_liter": "6.0",
            "driver_hourly_rate": "30.0",
        },
        buses=buses,
        data=data,
        plans=plans,
        summary=FleetSummary(
            rounds=1, wins_per_bus=(), unserved_passengers=0, unserved_pairs=()
        ),
        elapsed=0.0,
    )


class TestSelectScenarios:
    def test_keeps_the_requested_order_and_finds_the_base_instance(self, root):
        scenarios = select_scenarios(("65", "19", "16"), root)

        assert [scenario["scenario_id"] for scenario in scenarios] == [
            "65",
            "19",
            "16",
        ]
        assert [scenario["instance_id"] for scenario in scenarios] == [
            "base",
            "p1_4_r",
            "p1_4_b",
        ]

    def test_unknown_id_is_rejected(self, root):
        with pytest.raises(ValueError, match="999"):
            select_scenarios(("16", "999"), root)


class TestOperationalCost:
    def test_fuel_uses_each_bus_own_autonomy(self):
        buses = [make_bus(1, km_per_liter=4.0), make_bus(2, km_per_liter=2.0)]
        plans = [make_plan(1, (1, 2), minutes=10), make_plan(2, (2, 3), minutes=30)]
        data = make_data({(1, 2): 8.0, (2, 3): 4.0})

        cost = operational_cost(make_run(buses, plans, data))

        # 8 km / 4 km/L + 4 km / 2 km/L = 2 + 2 L
        assert cost.liters == pytest.approx(4.0)
        assert cost.fuel == pytest.approx(24.0)
        assert cost.driver == pytest.approx(40 / 60 * 30)
        assert cost.total == pytest.approx(44.0)
        assert cost.per_passenger(8) == pytest.approx(5.5)

    def test_routes_that_serve_nobody_are_not_charged(self):
        buses = [make_bus(1)]
        plans = [make_plan(1, (1, 2), served=0)]
        data = make_data({(1, 2): 8.0})

        cost = operational_cost(make_run(buses, plans, data))

        assert cost == OperationalCost(
            distance_km=0.0,
            liters=0.0,
            fuel=0.0,
            driver=0.0,
            diesel_price=6.0,
            driver_hourly_rate=30.0,
        )


class TestPlanCells:
    def test_adds_capacity_and_autonomy_before_the_shared_cells(self):
        bus = make_bus(1, capacity=24, km_per_liter=4.61)
        plan = make_plan(1, (3, 7), served=4)

        cells = plan_cells(plan, bus, time_limit_minutes=50)

        assert len(cells) == len(PLAN_HEADERS)
        assert cells[0] == "1"
        assert cells[1] == "24"
        assert cells[2] == "4.61"
        assert cells[6] == "3/24"  # peak against this bus's capacity


class TestRunScenario:
    def test_uses_the_real_fleet_and_starts_at_the_pair_origin(self, root):
        scenario = select_scenarios(("65",), root)[0]

        run = run_scenario(scenario, root)

        capacities = {bus.id: bus.passenger_capacity for bus in run.buses}
        assert capacities[4] == 50  # scenario 65 includes the 50-seat bus
        assert capacities[1] == 24
        assert run.plans
        for plan in run.plans:
            assert plan.stops[0] == plan.origin  # no deadhead prefix
