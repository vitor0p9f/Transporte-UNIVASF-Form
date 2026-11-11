"""Pipeline entry point: load one scenario and solve its fleet."""

from pathlib import Path

from algorithms.top_univasf.cost import CostModel
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
    depot: int | None = None,
    objective: str = "time",
) -> tuple[InstanceData, list[BusPlan], FleetSummary]:
    """Full pipeline: load the instance and solve its fleet.

    The origins the draft may use come from the scenario's ``origin`` column
    (empty = free); the `origin` parameter overrides the scenario and forces a
    single allowed origin, for experiments. `depot` adds a fixed departure
    point to every route (the deadhead) without changing the allowed origins.

    `objective` selects the score: ``"time"`` (the original passengers per
    minute) or ``"cost"`` (passengers per real). Under the cost objective, the
    scenario's diesel price and driver hourly rate build the `CostModel` that
    every bus uses with its own km per liter.
    """
    if objective not in {"time", "cost"}:
        raise ValueError(
            f"unknown objective {objective!r}; expected 'time' or 'cost'"
        )
    data = load_instance_data(
        Path(root) / "instances" / scenario["instance_id"], period=scenario["period"]
    )
    draft_origins = parse_node_labels(scenario.get("origin"))
    if origin is not None:
        draft_origins = (origin,)
    cost_model = None
    if objective == "cost":
        cost_model = CostModel(
            diesel_price_per_liter=float(scenario["diesel_price_per_liter"]),
            driver_hourly_rate=float(scenario["driver_hourly_rate"]),
        )
    plans, summary = run_fleet(
        data,
        buses,
        int(scenario["max_time_limit"]),
        cost_model=cost_model,
        destinations=parse_node_labels(scenario.get("destination_labels")),
        draft_origins=draft_origins,
        depot=depot,
    )
    return data, plans, summary
