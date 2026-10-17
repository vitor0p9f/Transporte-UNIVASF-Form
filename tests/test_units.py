"""Unit tests for the heuristic building blocks."""

import numpy as np
import pytest

from algorithms.top_UNIVASF import (
    InstanceData,
    _conflict_groups,
    _stretch_passengers,
    marginal_pax_per_min,
    od_pair_score,
    pax_per_min,
    simulate_stops,
)


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
        served, travel, peak, pairs = simulate_stops(data, [1, 2, 3], 1, data.demand)
        # 1->3 finds the first leg full after 1->2 boarded, so it never boards.
        assert (served, travel, peak) == (2, 30, 1)
        assert pairs == [(1, 2, 1), (2, 3, 1)]

    def test_passengers_alighting_free_seats(self):
        data = make_data(
            demand={(1, 2): 2, (2, 3): 2},
            time={(1, 2): 5, (2, 3): 5},
        )
        served, _, peak, pairs = simulate_stops(data, [1, 2, 3], 2, data.demand)
        assert served == 4
        assert peak == 2
        assert pairs == [(1, 2, 2), (2, 3, 2)]

    def test_background_occupies_seats_without_being_recounted(self):
        data = make_data(
            demand={(1, 2): 1, (2, 3): 1},
            time={(1, 2): 5, (2, 3): 5},
        )
        served, _, peak, pairs = simulate_stops(
            data, [1, 2, 3], 1, data.demand, background={(1, 2): 1}
        )
        assert served == 1
        assert peak == 1
        assert pairs == [(2, 3, 1)]

    def test_demand_matrix_is_never_mutated(self):
        data = make_data(demand={(1, 2): 3, (2, 1): 3}, time={(1, 2): 5})
        before = data.demand.copy()
        simulate_stops(data, [1, 2, 1], 2, data.demand)
        assert np.array_equal(data.demand, before)

    def test_repeated_stop_does_not_board_a_pair_twice(self):
        data = make_data(demand={(1, 3): 5}, time={(1, 3): 5, (3, 1): 5})
        served, _, _, _ = simulate_stops(data, [1, 2, 1, 3], 5, data.demand)
        assert served == 5

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
        )[0]

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
        assert simulate_stops(data, stops, 5, data.demand)[0] == 5


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
