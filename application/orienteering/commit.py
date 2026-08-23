from __future__ import annotations

from collections.abc import Mapping

from application.orienteering.models import DemandState
from application.orienteering.state import apply_demand_commit, prune_empty_demand


def commit_served_demand(
    demand_state: DemandState,
    served_pairs: Mapping[tuple[str, str], int],
) -> DemandState:
    return apply_demand_commit(demand_state, served_pairs)


def prune_satisfied_nodes(demand_state: DemandState) -> DemandState:
    return prune_empty_demand(demand_state)
