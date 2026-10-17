"""Pipeline entry point: load one scenario and solve its fleet."""

from pathlib import Path

from algorithms.top_univasf.fleet import run_fleet
from algorithms.top_univasf.model import BusPlan, FleetSummary
from entities.bus import Bus
from utils.instances import InstanceData, load_instance_data
from utils.scenarios import parse_node_labels


def solve_scenario(
    scenario: dict,
    buses: list[Bus],
    root: str | Path,
    *,
    origin: int | None = None,
) -> tuple[InstanceData, list[BusPlan], FleetSummary]:
    """Full pipeline: load the instance and solve its fleet.

    The origins the draft may use come from the scenario's ``origin`` column
    (empty = free); the `origin` parameter overrides the scenario and forces a
    single allowed origin, for experiments.
    """
    data = load_instance_data(
        Path(root) / "instances" / scenario["instance_id"], period=scenario["period"]
    )
    draft_origins = parse_node_labels(scenario.get("origin"))
    if origin is not None:
        draft_origins = (origin,)
    plans, summary = run_fleet(
        data,
        buses,
        int(scenario["max_time_limit"]),
        destinations=parse_node_labels(scenario.get("destination_labels")),
        draft_origins=draft_origins,
    )
    return data, plans, summary
