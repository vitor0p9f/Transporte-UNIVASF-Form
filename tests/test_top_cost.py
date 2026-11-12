"""Unit tests for TOP's cost objective.

The score is passengers per real (R$): each bus pays the fuel for its own km
per liter plus the driver for the route minutes. These tests pin the cost
arithmetic, the draft and expansion scores and the final plan consistency.
"""

import numpy as np
import pytest

from algorithms.top_univasf import (
    CostModel,
    WorkState,
    best_demand_driven_insertion,
    best_pair_for_bus,
    route_distance_km,
    run_fleet,
    solve_scenario,
)
from entities.bus import Bus
from utils.fleet import load_fleet, parse_fleet_ids
from utils.instances import InstanceData
from utils.scenarios import load_scenarios


def make_bus(bus_id: int, capacity: int = 10, km_per_liter: float = 4.0) -> Bus:
    return Bus(bus_id, capacity, 100.0, km_per_liter)


def make_data(
    demand: dict[tuple[int, int], int] | None = None,
    time: dict[tuple[int, int], int] | None = None,
    distance: dict[tuple[int, int], float] | None = None,
    size: int = 3,
) -> InstanceData:
    """Tiny instance indexed by node id, built from {(a, b): value}."""
    demands = np.zeros((size + 1, size + 1), dtype=int)
    for (origin, destination), quantity in (demand or {}).items():
        demands[origin, destination] = quantity
    times = np.zeros((size + 1, size + 1), dtype=int)
    for (origin, destination), minutes in (time or {}).items():
        times[origin, destination] = minutes
    distances = np.zeros((size + 1, size + 1))
    for (origin, destination), km in (distance or {}).items():
        distances[origin, destination] = km
    return InstanceData(
        nodes=list(range(1, size + 1)),
        distance=distances,
        time=times,
        demand=demands,
    )


def cost_model() -> CostModel:
    """Diesel at R$ 10/L and driver at R$ 60/h: one minute costs R$ 1."""
    return CostModel(diesel_price_per_liter=10.0, driver_hourly_rate=60.0)


def make_instance() -> InstanceData:
    """Demand 1->2 = 4: 10 minutes and 8 km."""
    return make_data(
        demand={(1, 2): 4},
        time={(1, 2): 10},
        distance={(1, 2): 8.0},
    )


class TestCostModel:
    def test_fuel_plus_driver(self):
        cost = cost_model().route_cost(8.0, 10, km_per_liter=4.0)

        assert cost == pytest.approx(8 / 4 * 10 + 10 / 60 * 60)

    def test_rejects_non_positive_autonomy(self):
        with pytest.raises(ValueError, match="km_per_liter"):
            cost_model().route_cost(8.0, 10, km_per_liter=0)

    def test_route_distance_counts_repeated_nodes(self):
        distance = np.zeros((4, 4))
        distance[1, 2] = 2.0
        distance[2, 1] = 3.0
        distance[1, 3] = 4.0

        assert route_distance_km(distance, (1, 2, 1, 3)) == pytest.approx(9.0)
        assert route_distance_km(distance, (1,)) == 0.0


class TestDraftScore:
    def test_cheaper_bus_gets_a_higher_pax_per_real(self):
        data = make_instance()
        remaining = data.demand

        cheap = best_pair_for_bus(
            data,
            make_bus(1, km_per_liter=4.0),
            remaining,
            100,
            cost_model=cost_model(),
            destinations=(2,),
            draft_origins=(1,),
        )
        thirsty = best_pair_for_bus(
            data,
            make_bus(2, km_per_liter=2.0),
            remaining,
            100,
            cost_model=cost_model(),
            destinations=(2,),
            draft_origins=(1,),
        )

        assert cheap is not None and thirsty is not None
        assert cheap.cost == pytest.approx(30.0)
        assert thirsty.cost == pytest.approx(50.0)
        assert cheap.score == pytest.approx(4 / 30)
        assert thirsty.score == pytest.approx(4 / 50)
        assert cheap.score > thirsty.score

    def test_bigger_bus_wins_when_its_seats_board_more(self):
        data = make_data(
            demand={(1, 2): 20},
            time={(1, 2): 10},
            distance={(1, 2): 8.0},
        )

        small = best_pair_for_bus(
            data,
            make_bus(1, capacity=5, km_per_liter=4.0),
            data.demand,
            100,
            cost_model=cost_model(),
            destinations=(2,),
            draft_origins=(1,),
        )
        big = best_pair_for_bus(
            data,
            make_bus(2, capacity=20, km_per_liter=2.0),
            data.demand,
            100,
            cost_model=cost_model(),
            destinations=(2,),
            draft_origins=(1,),
        )

        assert small is not None and big is not None
        assert small.served_passengers == 5
        assert big.served_passengers == 20
        assert big.score > small.score


class TestExpansionScore:
    def test_marginal_pax_per_extra_real(self):
        data = make_data(
            demand={(3, 2): 5},
            time={(1, 2): 10, (1, 3): 10, (3, 2): 10},
            distance={(1, 2): 8.0, (1, 3): 10.0, (3, 2): 8.0},
        )
        bus = make_bus(1, capacity=10, km_per_liter=4.0)
        state = WorkState(
            bus=bus,
            origin=1,
            destination=2,
            stops=[1, 2],
            claimed={(1, 2): 4},
            travel_time_minutes=10,
            cost=30.0,
        )

        proposal = best_demand_driven_insertion(
            data, state, data.demand, 100, cost_model=cost_model()
        )

        assert proposal is not None
        assert proposal.stops == (1, 3, 2)
        # Trial: 18 km and 20 min -> R$ 65; marginal R$ 35 for 5 passengers.
        assert proposal.cost == pytest.approx(65.0)
        assert proposal.score == pytest.approx(5 / 35)


class TestFinalPlan:
    def test_plan_cost_and_score_are_consistent(self):
        data = make_instance()
        buses = [make_bus(1)]

        plans, _summary = run_fleet(
            data,
            buses,
            100,
            cost_model=cost_model(),
            destinations=(2,),
            draft_origins=(1,),
        )

        assert len(plans) == 1
        plan = plans[0]
        assert plan.cost == pytest.approx(30.0)
        assert plan.score == pytest.approx(plan.served_passengers / plan.cost)


class TestSolver:
    def test_solver_fills_cost_and_pax_per_real(self, root):
        scenario = next(
            s for s in load_scenarios(root) if str(s["scenario_id"]) == "65"
        )
        buses = load_fleet(
            root / "fleet.csv", parse_fleet_ids(scenario["fleet_bus_ids"])
        )

        _data, plans, _summary = solve_scenario(scenario, buses, root)

        assert plans
        assert all(plan.cost > 0.0 for plan in plans)
        assert all(
            plan.score == pytest.approx(plan.served_passengers / plan.cost)
            for plan in plans
        )
