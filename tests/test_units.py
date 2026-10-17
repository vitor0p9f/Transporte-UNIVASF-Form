"""Unit tests for the heuristic building blocks."""

import numpy as np
import pytest

from algorithms.top_UNIVASF import (
    DraftProposal,
    ExpansionProposal,
    InstanceData,
    WorkState,
    _conflict_groups,
    _stretch_passengers,
    marginal_pax_per_min,
    od_pair_score,
    pax_per_min,
    simulate_stops,
)
from entities.bus import Bus


def make_data(demand: dict, time: dict | None = None, size: int = 4) -> InstanceData:
    """Tiny instance indexed by node id, built from ``{(a, b): quantity}``."""
    times = np.zeros((size + 1, size + 1), dtype=int)
    for (a, b), value in (time or {}).items():
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


class TestScoring:
    def test_pax_per_min_zero_inputs(self):
        assert pax_per_min(0, 10) == 0.0
        assert pax_per_min(10, 0) == 0.0
        assert pax_per_min(-1, 10) == 0.0

    def test_pax_per_min_ratio(self):
        assert pax_per_min(10, 2) == 5.0

    def test_od_pair_score(self):
        assert od_pair_score(0, 10) == 0.0
        assert od_pair_score(9, 3) == 3.0

    def test_marginal_pax_per_min(self):
        assert marginal_pax_per_min(0, 5) == 0.0
        assert marginal_pax_per_min(4, 2) == 2.0

    def test_marginal_score_is_infinite_without_extra_time(self):
        assert marginal_pax_per_min(3, 0) == float("inf")


class TestSimulateStops:
    def test_boarding_respects_capacity_per_leg(self):
        data = make_data(
            demand={(1, 2): 5, (1, 3): 5, (2, 3): 5},
            time={(1, 2): 10, (2, 3): 20},
        )
        outcome = simulate_stops(data, [1, 2, 3], 1, data.demand)
        # 1->3 finds the first leg full after 1->2 boarded, so it never boards.
        assert (outcome.passengers, outcome.travel_minutes, outcome.peak_load) == (2, 30, 1)
        assert outcome.pairs == ((1, 2, 1), (2, 3, 1))

    def test_passengers_alighting_free_seats(self):
        data = make_data(
            demand={(1, 2): 2, (2, 3): 2},
            time={(1, 2): 5, (2, 3): 5},
        )
        outcome = simulate_stops(data, [1, 2, 3], 2, data.demand)
        assert outcome.passengers == 4
        assert outcome.peak_load == 2
        assert outcome.pairs == ((1, 2, 2), (2, 3, 2))

    def test_claimed_demand_occupies_seats_without_being_recounted(self):
        data = make_data(
            demand={(1, 2): 1, (2, 3): 1},
            time={(1, 2): 5, (2, 3): 5},
        )
        outcome = simulate_stops(
            data, [1, 2, 3], 1, data.demand, claimed={(1, 2): 1}
        )
        assert outcome.passengers == 1
        assert outcome.peak_load == 1
        assert outcome.pairs == ((2, 3, 1),)

    def test_demand_matrix_is_never_mutated(self):
        data = make_data(demand={(1, 2): 3, (2, 1): 3}, time={(1, 2): 5})
        before = data.demand.copy()
        simulate_stops(data, [1, 2, 1], 2, data.demand)
        assert np.array_equal(data.demand, before)

    def test_repeated_stop_does_not_board_a_pair_twice(self):
        data = make_data(demand={(1, 3): 5}, time={(1, 3): 5, (3, 1): 5})
        outcome = simulate_stops(data, [1, 2, 1, 3], 5, data.demand)
        assert outcome.passengers == 5

    @pytest.mark.parametrize(
        "stops",
        [
            (1, 2),  # direct pair [o, d]
            (1, 3),  # direct pair, other destination
            (1, 2, 3),  # pair via one demand point [o, P, d]
            (1, 2, 1),  # o == d: the locked pair starts and ends at the same node
            (2, 1, 2),  # o == d, other node
        ],
    )
    def test_draft_fast_path_matches_simulation_on_draft_shapes(self, stops):
        """The draft evaluates only these shapes, where no OD pair can board
        twice, so the fast path and the full simulation must agree.
        """
        data = make_data(
            demand={(1, 2): 3, (1, 3): 4, (2, 3): 2, (2, 1): 1, (3, 2): 2},
            time={
                entry: 5
                for entry in [(1, 2), (1, 3), (2, 3), (2, 1), (3, 1), (3, 2)]
            },
        )
        remaining = data.demand.copy()
        assert _stretch_passengers(stops, 5, remaining) == simulate_stops(
            data, stops, 5, remaining
        ).passengers

    def test_draft_fast_path_diverges_only_on_disjoint_repeats(self):
        """Documented divergence: `_stretch_passengers` skips the local demand
        copy, so a pair reachable twice with disjoint leg ranges (1->2 at
        positions 0->1 and 2->3) boards once per occurrence instead of once
        in total. No draft shape can produce that, and the fast path is never
        called on expansion routes.
        """
        data = make_data(demand={(1, 2): 5}, time={(1, 2): 5})
        stops = (1, 2, 1, 2)
        assert _stretch_passengers(stops, 5, data.demand) == 10
        assert simulate_stops(data, stops, 5, data.demand).passengers == 5


class TestProposals:
    def _bus(self, bus_id: int, capacity: int = 10) -> Bus:
        return Bus(
            id=bus_id,
            passenger_capacity=capacity,
            fuel_capacity=100.0,
            km_autonomy_per_liter=4.0,
        )

    def _draft(self, stops=(1, 2, 3), score=2.0, served=4, travel=10, bus_id=5):
        return DraftProposal(
            bus=self._bus(bus_id),
            origin=stops[0],
            destination=stops[-1],
            stops=stops,
            served_passengers=served,
            travel_time_minutes=travel,
            score=score,
        )

    def test_draft_conflict_keys_are_points_and_sub_pairs(self):
        keys = self._draft().conflict_keys()
        assert ("point", 1) in keys
        assert ("od", 1, 2) in keys
        assert ("od", 1, 3) in keys
        assert ("od", 2, 3) in keys
        assert len(keys) == 3 + 3

    def test_draft_tie_break_prefers_score_then_passengers_then_time_then_id(self):
        better_score = self._draft(score=3.0)
        more_passengers = self._draft(served=9)
        less_time = self._draft(travel=1)
        lower_id = self._draft(bus_id=1)
        reference = self._draft()
        assert better_score.tie_break_key() > reference.tie_break_key()
        assert more_passengers.tie_break_key() > reference.tie_break_key()
        assert less_time.tie_break_key() > reference.tie_break_key()
        assert lower_id.tie_break_key() > reference.tie_break_key()

    def test_expansion_conflict_keys_are_inserted_points_and_claimed_pairs(self):
        state = WorkState(
            bus=self._bus(1), origin=8, destination=8, stops=[8, 6, 8]
        )
        proposal = ExpansionProposal(
            state=state,
            stops=(8, 6, 2, 8),
            claim=((6, 8, 2),),
            new_points=(2,),
            travel_time_minutes=20,
            peak_load=3,
            score=1.5,
        )
        assert proposal.conflict_keys() == [("point", 2), ("od", 6, 8)]

    def test_expansion_tie_break_sums_the_claim(self):
        state = WorkState(
            bus=self._bus(1), origin=8, destination=8, stops=[8, 6, 8]
        )
        small = ExpansionProposal(
            state=state, stops=(8, 6, 2, 8), claim=((6, 8, 1),), new_points=(2,),
            travel_time_minutes=20, peak_load=3, score=1.5,
        )
        big = ExpansionProposal(
            state=state, stops=(8, 6, 3, 8), claim=((6, 8, 4),), new_points=(3,),
            travel_time_minutes=20, peak_load=3, score=1.5,
        )
        assert big.tie_break_key() > small.tie_break_key()


class TestConflictGroups:
    def test_disjoint_keys_stay_separate(self):
        groups = _conflict_groups([[("point", 1)], [("point", 2)]])
        assert sorted(sorted(group) for group in groups) == [[0], [1]]

    def test_shared_key_merges_transitively(self):
        groups = _conflict_groups(
            [
                [("point", 1)],
                [("point", 1), ("point", 2)],
                [("point", 2)],
                [("point", 3)],
            ]
        )
        assert sorted(sorted(group) for group in groups) == [[0, 1, 2], [3]]

    def test_no_keys_means_no_group(self):
        assert _conflict_groups([]) == []
