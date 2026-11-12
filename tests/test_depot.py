"""Tests for the fixed-depot prefix used by the controlled comparison."""

import numpy as np

from algorithms.top_univasf import (
    CostModel,
    DraftProposal,
    InstanceData,
    run_fleet,
    with_depot,
)
from algorithms.top_univasf.draft import best_pair_for_bus
from entities.bus import Bus
from utils.fleet import homogenize_fleet


def make_data(demand: dict, time: dict, size: int = 4) -> InstanceData:
    """Tiny instance indexed by node id, built from ``{(a, b): quantity}``."""
    times = np.zeros((size + 1, size + 1), dtype=int)
    for (a, b), value in time.items():
        times[a, b] = value
    demands = np.zeros((size + 1, size + 1), dtype=int)
    for (a, b), value in demand.items():
        demands[a, b] = value
    return InstanceData(
        nodes=list(range(1, size + 1)),
        distance=np.zeros((size + 1, size + 1)),
        time=times,
        demand=demands,
    )


def make_bus(bus_id: int = 1, capacity: int = 10) -> Bus:
    return Bus(
        id=bus_id,
        passenger_capacity=capacity,
        fuel_capacity=100.0,
        km_autonomy_per_liter=4.0,
    )


def make_instance() -> InstanceData:
    """Demand 1->2, with a 10-minute deadhead from depot 3 to origin 1."""
    return make_data(demand={(1, 2): 4}, time={(3, 1): 10, (1, 2): 5})


def cost_model() -> CostModel:
    """Diesel at R$ 10/L and driver at R$ 60/h: one minute costs R$ 1."""
    return CostModel(diesel_price_per_liter=10.0, driver_hourly_rate=60.0)


class TestWithDepot:
    def test_prefixes_when_depot_is_not_first(self):
        assert with_depot((1, 2), 3) == (3, 1, 2)

    def test_keeps_route_when_depot_is_already_first(self):
        assert with_depot((3, 1, 2), 3) == (3, 1, 2)

    def test_no_depot_is_a_no_op(self):
        assert with_depot((1, 2), None) == (1, 2)

    def test_empty_route_stays_empty(self):
        assert with_depot((), 3) == ()


class TestDraftWithDepot:
    def test_deadhead_enters_time_and_score(self):
        data = make_instance()
        bus = make_bus()

        proposal = best_pair_for_bus(
            data,
            bus,
            data.demand,
            100,
            cost_model=cost_model(),
            destinations=(2,),
            draft_origins=(1,),
            depot=3,
        )

        assert proposal is not None
        assert proposal.stops == (1, 2)
        assert proposal.depot == 3
        assert proposal.served_passengers == 4
        assert proposal.travel_time_minutes == 15
        assert proposal.score == 4 / 15

    def test_without_depot_the_route_has_no_deadhead(self):
        data = make_instance()
        bus = make_bus()

        proposal = best_pair_for_bus(
            data,
            bus,
            data.demand,
            100,
            cost_model=cost_model(),
            destinations=(2,),
            draft_origins=(1,),
        )

        assert proposal is not None
        assert proposal.travel_time_minutes == 5
        assert proposal.score == 4 / 5

    def test_conflict_keys_keep_depot_pairs_but_not_the_depot_point(self):
        proposal = DraftProposal(
            bus=make_bus(),
            origin=1,
            destination=2,
            stops=(1, 2),
            served_passengers=4,
            travel_time_minutes=15,
            score=4 / 15,
            depot=3,
        )

        keys = proposal.conflict_keys()
        assert ("point", 3) not in keys
        assert ("point", 1) in keys
        assert ("point", 2) in keys
        assert ("od", 3, 1) in keys
        assert ("od", 3, 2) in keys
        assert ("od", 1, 2) in keys


class TestFleetWithDepot:
    def test_plan_starts_at_depot_and_counts_the_deadhead(self):
        data = make_instance()
        bus = make_bus()

        plans, _summary = run_fleet(
            data,
            [bus],
            100,
            cost_model=cost_model(),
            destinations=(2,),
            draft_origins=(1,),
            depot=3,
        )

        assert len(plans) == 1
        plan = plans[0]
        assert plan.stops == (3, 1, 2)
        assert plan.origin == 1
        assert plan.destination == 2
        assert plan.served_passengers == 4
        assert plan.travel_time_minutes == 15

    def test_without_depot_the_plan_keeps_the_pair_route(self):
        data = make_instance()
        bus = make_bus()

        plans, _summary = run_fleet(
            data,
            [bus],
            100,
            cost_model=cost_model(),
            destinations=(2,),
            draft_origins=(1,),
        )

        assert len(plans) == 1
        assert plans[0].stops == (1, 2)
        assert plans[0].travel_time_minutes == 5


class TestHomogenizeFleet:
    def test_keeps_ids_and_count_and_sets_every_capacity(self):
        buses = [
            Bus(1, 50, 100.0, 4.0),
            Bus(2, 32, 100.0, 4.0),
            Bus(3, 24, 100.0, 4.0),
        ]

        homogenized = homogenize_fleet(buses, 24)

        assert [bus.id for bus in homogenized] == [1, 2, 3]
        assert [bus.passenger_capacity for bus in homogenized] == [24, 24, 24]
        assert [bus.passenger_capacity for bus in buses] == [50, 32, 24]
