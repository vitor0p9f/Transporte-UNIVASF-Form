"""Unit tests for the scenario label parser."""

import pytest

from utils.scenarios import parse_node_labels


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("43;44;45", (43, 44, 45)),
        ("44", (44,)),
        (" 1 ; 2 ", (1, 2)),
        ("1;;2", (1, 2)),
        ("", None),
        (";", None),
        (None, None),
    ],
)
def test_parse_node_labels(value, expected):
    assert parse_node_labels(value) == expected
