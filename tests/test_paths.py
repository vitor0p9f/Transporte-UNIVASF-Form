"""Unit tests for the path measures shared by the heuristics."""

import numpy as np
import pytest

from utils.paths import path_distance, path_time_minutes


def make_matrices() -> tuple[np.ndarray, np.ndarray]:
    distance = np.zeros((4, 4))
    distance[1, 2] = 2.0
    distance[2, 1] = 1.0
    distance[2, 3] = 3.5
    time = np.zeros((4, 4), dtype=int)
    time[1, 2] = 7
    time[2, 1] = 3
    time[2, 3] = 11
    return distance, time


class TestPathDistance:
    def test_sums_every_leg(self):
        distance, _ = make_matrices()

        assert path_distance(distance, (1, 2, 3)) == pytest.approx(5.5)

    def test_counts_a_repeated_node_every_time_it_is_driven(self):
        distance, _ = make_matrices()

        assert path_distance(distance, (1, 2, 1, 2, 3)) == pytest.approx(8.5)

    def test_a_route_shorter_than_two_nodes_drives_nothing(self):
        distance, _ = make_matrices()

        assert path_distance(distance, ()) == 0.0
        assert path_distance(distance, (1,)) == 0.0

    def test_start_charges_the_leg_from_the_depot(self):
        distance, _ = make_matrices()

        assert path_distance(distance, (1, 2, 3), start=2) == pytest.approx(6.5)


class TestPathTimeMinutes:
    def test_sums_every_leg_in_minutes(self):
        _, time = make_matrices()

        assert path_time_minutes(time, (1, 2, 3)) == 18

    def test_returns_whole_minutes(self):
        _, time = make_matrices()
        time[1, 2] = 2.6

        assert path_time_minutes(time, (1, 2)) == 2

    def test_a_route_shorter_than_two_nodes_takes_no_time(self):
        _, time = make_matrices()

        assert path_time_minutes(time, ()) == 0
        assert path_time_minutes(time, (1,)) == 0

    def test_start_charges_the_leg_from_the_depot(self):
        _, time = make_matrices()

        assert path_time_minutes(time, (1, 2, 3), start=2) == 21
