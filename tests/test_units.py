"""Unit tests for the heuristic building blocks."""

import numpy as np
import pytest

from algorithms.top_univasf import (
    DraftProposal,
    ExpansionProposal,
    WorkState,
)
from algorithms.top_univasf.conflict import conflict_groups
from algorithms.top_univasf.simulation import (
    board_greedily,
    segment_passengers,
    simulate_stops,
)
from entities.bus import Bus
from tests import factories
from tests.factories import make_data
from utils.fleet import load_fleet


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
        assert segment_passengers(stops, 5, remaining) == simulate_stops(
            data, stops, 5, remaining
        ).passengers

    def test_draft_fast_path_diverges_only_on_disjoint_repeats(self):
        """Documented divergence: `segment_passengers` skips the demand copy,
        so a pair reachable twice with disjoint leg ranges (1->2 at
        positions 0->1 and 2->3) boards once per occurrence instead of once
        in total. No draft shape can produce that, and the fast path is never
        called on expansion routes.
        """
        data = make_data(demand={(1, 2): 5}, time={(1, 2): 5})
        stops = (1, 2, 1, 2)
        assert segment_passengers(stops, 5, data.demand) == 10
        assert simulate_stops(data, stops, 5, data.demand).passengers == 5

    def test_shared_core_flag_is_the_only_difference(self):
        """Both entry points call board_greedily; only deduplicate_pairs differs."""
        data = make_data(demand={(1, 2): 5}, time={(1, 2): 5})
        stops = (1, 2, 1, 2)

        with_duplicates, _ = board_greedily(
            stops, 5, data.demand, [0] * (len(stops) - 1), deduplicate_pairs=False
        )
        without_duplicates, served = board_greedily(
            stops, 5, data.demand, [0] * (len(stops) - 1), deduplicate_pairs=True
        )
        assert with_duplicates == [(1, 2, 5), (1, 2, 5)]
        assert (without_duplicates, served) == ([(1, 2, 5)], 5)
        assert segment_passengers(stops, 5, data.demand) == 10
        assert simulate_stops(data, stops, 5, data.demand).passengers == 5


class TestProposals:
    def _bus(self, bus_id: int, capacity: int = 10) -> Bus:
        return factories.make_bus(bus_id, capacity=capacity)

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
        groups = conflict_groups([[("point", 1)], [("point", 2)]])
        assert sorted(sorted(group) for group in groups) == [[0], [1]]

    def test_shared_key_merges_transitively(self):
        groups = conflict_groups(
            [
                [("point", 1)],
                [("point", 1), ("point", 2)],
                [("point", 2)],
                [("point", 3)],
            ]
        )
        assert sorted(sorted(group) for group in groups) == [[0, 1, 2], [3]]

    def test_no_keys_means_no_group(self):
        assert conflict_groups([]) == []


class TestLoadFleet:
    ROWS = (
        "id,passenger_capacity,fuel_capacity,km_autonomy_per_liter\n"
        "1,24,148,4.11\n"
        "2,32,200,2.5\n"
    )

    @staticmethod
    def write(tmp_path) -> object:
        path = tmp_path / "fleet.csv"
        path.write_text(TestLoadFleet.ROWS, encoding="utf-8")
        return path

    def test_keeps_the_requested_order(self, tmp_path):
        buses = load_fleet(self.write(tmp_path), [2, 1])

        assert [bus.id for bus in buses] == [2, 1]

    def test_accepts_a_one_shot_iterator_of_ids(self, tmp_path):
        ids = (bus_id for bus_id in [2, 1])

        buses = load_fleet(self.write(tmp_path), ids)

        assert [bus.id for bus in buses] == [2, 1]

    def test_unknown_id_is_rejected(self, tmp_path):
        with pytest.raises(ValueError, match="unknown bus ids 9"):
            load_fleet(self.write(tmp_path), [1, 9])

    def test_unknown_id_from_an_iterator_is_rejected(self, tmp_path):
        ids = (bus_id for bus_id in [1, 9])

        with pytest.raises(ValueError, match="unknown bus ids 9"):
            load_fleet(self.write(tmp_path), ids)
