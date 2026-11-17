"""Helpers shared by the markdown report runners.

The report scripts differ in what they solve and how they lay the result out,
but they all select scenarios, time a run and build the cost the same way. The
scenario record, the metrics and the markdown formatting live in `reporting`;
this module keeps scenario selection and the solver invocation.
"""

import argparse
import sys
import time
from collections.abc import Callable
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import reporting
from algorithms.top_univasf import solve_scenario
from entities.bus import Bus
from utils.fleet import load_fleet, parse_fleet_ids
from utils.scenarios import (
    DEFAULT_REPORT_SCENARIOS,
    SCENARIO_FILES,
    load_scenarios,
    pick_scenarios,
)

#: What a runner passes to `run_scenario` to solve one scenario.
Solver = Callable[[dict, list[Bus], Path], tuple]


def select_scenarios(
    ids: tuple[str, ...] = DEFAULT_REPORT_SCENARIOS,
    root: str | Path = ROOT,
    *,
    files: tuple[str, ...] | None = None,
) -> list[dict]:
    """The requested scenarios, in the requested order.

    ``files`` lets the controlled runner select from its own scenario copy
    while keeping the same ordering and validation rules.
    """
    return pick_scenarios(load_scenarios(root, files=files or SCENARIO_FILES), ids)


def parse_scenario_ids(
    only: str | None,
    default: tuple[str, ...] = DEFAULT_REPORT_SCENARIOS,
) -> tuple[str, ...]:
    """Parse the ``--only`` comma-separated value, falling back to ``default``."""
    if not only:
        return default
    return tuple(item.strip() for item in only.split(",") if item.strip())


def add_only_argument(
    parser: argparse.ArgumentParser,
    default: tuple[str, ...] = DEFAULT_REPORT_SCENARIOS,
) -> None:
    """Add the common ``--only`` option to a report parser."""
    parser.add_argument(
        "--only",
        default=None,
        help=(
            "comma-separated scenario ids "
            f"(default: {','.join(default)})"
        ),
    )


def scenario_buses(
    scenario: dict,
    root: str | Path = ROOT,
    *,
    fleet: str = "fleet.csv",
) -> list[Bus]:
    """Load the buses named by a scenario from a fleet CSV."""
    return load_fleet(
        Path(root) / fleet,
        parse_fleet_ids(scenario["fleet_bus_ids"]),
    )


def run_scenario(
    scenario: dict,
    root: str | Path = ROOT,
    *,
    fleet: str = "fleet.csv",
    catch_errors: bool = False,
    solver: Solver = solve_scenario,
    buses: list[Bus] | None = None,
    heuristic: str = "",
) -> reporting.ScenarioRun:
    """Solve one scenario and record its time, plans and summary.

    `solver` is the pipeline to run (TOP by default; the controlled report
    passes both TOP and Clarke-Wright). `buses` lets a caller that already
    loaded the scenario fleet reuse it across heuristics. With ``catch_errors`` the
    failure is stored on the result so a batch report can keep going;
    otherwise the exception propagates.
    """
    root = Path(root)
    if buses is None:
        buses = scenario_buses(scenario, root, fleet=fleet)
    start = time.monotonic()
    try:
        data, plans, summary = solver(scenario, buses, root)
        error = ""
    except Exception as exc:
        if not catch_errors:
            raise
        data, plans, summary, error = None, [], None, f"{type(exc).__name__}: {exc}"
    return reporting.ScenarioRun(
        scenario=scenario,
        buses=buses,
        elapsed=time.monotonic() - start,
        data=data,
        plans=plans,
        summary=summary,
        error=error,
        heuristic=heuristic,
    )


def scenario_operational_cost(
    scenario: dict,
    data,
    plans,
    buses: list[Bus],
) -> reporting.OperationalCost:
    """Cost of a run, charging each route its own bus's fuel autonomy."""
    return reporting.operational_cost_per_bus(
        plans,
        data,
        buses,
        diesel_price=float(scenario["diesel_price_per_liter"]),
        driver_hourly_rate=float(scenario["driver_hourly_rate"]),
    )
