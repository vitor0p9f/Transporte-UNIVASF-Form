"""Scenario/instance input and conversion to the report model."""

from pathlib import Path

from algorithms.top_univasf.model import BusPlan, FleetSummary
from entities.bus import Bus
from utils.fleet import load_fleet, parse_fleet_ids
from utils.instances import InstanceData, load_instance_data
from utils.scenarios import load_scenarios, parse_node_labels

from .constants import (
    DEFAULT_CAPACITY,
    DEFAULT_DIESEL_PRICE,
    DEFAULT_KM_PER_LITER,
    DEFAULT_PERIOD,
    ITER_POSTIMPROVE,
    ITER_TWO_PHASE,
)
from .context import build_context
from .evaluation import evaluate_attendance
from .metrics import _route_path
from .model import Attendance, BusModel, Context, Route, bus_model
from .solver import clarke_wright_ovrp

ROOT = Path(__file__).resolve().parents[2]


def _find_scenario(scenario_id: str) -> dict:
    for scenario in load_scenarios(ROOT):
        if str(scenario["scenario_id"]) == str(scenario_id):
            return scenario
    raise SystemExit(
        f"[erro] cenário '{scenario_id}' não encontrado em "
        "scenarios.csv / scenarios_base.csv"
    )


def _scenario_fleet(scenario: dict | None) -> list[Bus]:
    if not scenario or not scenario.get("fleet_bus_ids"):
        return []
    return load_fleet(
        ROOT / "fleet.csv", parse_fleet_ids(scenario["fleet_bus_ids"])
    )


def _scenario_depot(scenario: dict | None) -> int | None:
    """Legacy reference depot; scenario_context separately keeps all origins."""
    if not scenario:
        return None
    origins = parse_node_labels(scenario.get("origin"))
    return origins[0] if origins else None


def reference_model(
    scenario: dict | None, capacity: int, diesel: float
) -> BusModel:
    """Single cost model of the scenario, applied to BOTH heuristics.

    Picks the fleet bus with the effective capacity (the criterion CW always
    used); when no bus matches, the smallest one. Without a declared fleet it
    returns a generic model. The report's operating cost uses this same model
    for TOP and for CW, so the values are comparable.
    """
    buses = _scenario_fleet(scenario)
    if not buses:
        return BusModel(
            name="genérico",
            capacity=capacity,
            km_per_liter=DEFAULT_KM_PER_LITER,
            diesel_price=diesel,
        )
    reference = next(
        (b for b in buses if b.passenger_capacity == capacity),
        min(buses, key=lambda b: b.passenger_capacity),
    )
    return bus_model(reference, diesel)


def scenario_context(
    scenario: dict | None,
    *,
    instance: str | None = None,
    period: str | None = None,
    depot: int | None = None,
    capacity: int | None = None,
    max_time: float | None = None,
    diesel: float | None = None,
    restrictions: str = "ambas",
    sense: str = "auto",
    max_routes: int | None = None,
) -> tuple[InstanceData, Context]:
    """Turn a scenario (instance, permitted endpoints, fleet, limits) into a context.

    Every explicit parameter wins over what the scenario defines; it is the
    same path the CLI walks, so the report runners hand the heuristics exactly
    the same limits.

    `max_routes` is the vehicle cap; when omitted, it is the size of the
    scenario fleet (None only when no fleet is declared).

    Without an explicit depot, every node in ``origin`` can start a route.
    An explicit depot overrides only that list. ``destination_labels`` always
    constrains the terminal node when present.
    """
    scenario = scenario or {}
    instance = instance or scenario.get("instance_id")
    if not instance:
        raise ValueError("informe a instância (o cenário não define uma)")
    period = period or scenario.get("period") or DEFAULT_PERIOD
    data = load_instance_data(ROOT / "instances" / instance, period=period)

    origins = (depot,) if depot is not None else parse_node_labels(scenario.get("origin"))
    if depot is None:
        depot = _scenario_depot(scenario)
    if depot is None:
        raise ValueError("informe o depósito (o cenário não define uma origem)")

    buses = _scenario_fleet(scenario)
    if diesel is None:
        diesel = (
            float(scenario["diesel_price_per_liter"])
            if scenario.get("diesel_price_per_liter")
            else DEFAULT_DIESEL_PRICE
        )
    # Without a given capacity, the smallest bus of the fleet sets it: that way
    # every route CW builds fits any bus of the scenario.
    if capacity is None:
        capacity = (
            min(b.passenger_capacity for b in buses)
            if buses
            else DEFAULT_CAPACITY
        )
    bus_model = reference_model(scenario, capacity, diesel)

    if max_time is None and scenario.get("max_time_limit"):
        max_time = int(scenario["max_time_limit"])

    if max_routes is None:
        max_routes = len(buses) or None

    ctx = build_context(
        data,
        depot,
        capacity=capacity,
        max_time=max_time,
        bus_model=bus_model,
        restrictions=restrictions,
        sense=sense,
        max_routes=max_routes,
        origins=origins,
        destinations=parse_node_labels(scenario.get("destination_labels")),
    )
    return data, ctx


def solve_scenario(
    scenario: dict,
    *,
    instance: str | None = None,
    period: str | None = None,
    depot: int | None = None,
    capacity: int | None = None,
    max_time: float | None = None,
    diesel: float | None = None,
    restrictions: str = "ambas",
    sense: str = "auto",
    max_routes: int | None = None,
    lam: float | None = None,
    use_two_phase: bool = True,
    use_post_improvement: bool = True,
    iterations: int = ITER_TWO_PHASE,
    post_improvement_iterations: int = ITER_POSTIMPROVE,
    seed: int = 42,
    verbose: bool = False,
) -> tuple[InstanceData, list[Route], Context, Attendance, float]:
    """Run CW on a scenario and return the solution already evaluated.

    Returns `(data, routes, ctx, attendance, lambda_used)` -- what `main.py`
    consumes to build the CW row of the comparison table.
    """
    data, ctx = scenario_context(
        scenario,
        instance=instance,
        period=period,
        depot=depot,
        capacity=capacity,
        max_time=max_time,
        diesel=diesel,
        restrictions=restrictions,
        sense=sense,
        max_routes=max_routes,
    )
    routes, lambda_used = clarke_wright_ovrp(
        ctx,
        lam=lam,
        use_two_phase=use_two_phase,
        use_post_improvement=use_post_improvement,
        iterations=iterations,
        post_improvement_iterations=post_improvement_iterations,
        seed=seed,
        verbose=verbose,
    )
    # The solver already cut the routes by the fleet and ran the local search
    # on them; here they are only measured.
    attendance = evaluate_attendance(routes, ctx)
    return data, routes, ctx, attendance, lambda_used


def plans_and_summary(
    routes: list[Route],
    ctx: Context,
    attendance: Attendance,
    buses: list[Bus] | None = None,
) -> tuple[list[BusPlan], FleetSummary]:
    """Convert the CW solution into the report model `reporting` reads.

    CW has no "rounds". Each plan uses the complete path, including its
    selected origin and permitted destination. The bus ids come
    from the scenario fleet, in order; `solve_scenario` already drops the
    routes beyond the fleet size, but on a direct call to
    `clarke_wright_ovrp` without that cap the extras still get sequential ids
    after the highest one.
    """
    ids = [bus.id for bus in (buses or [])]
    next_id = (max(ids) + 1) if ids else 1
    plans: list[BusPlan] = []

    for index, route in enumerate(routes):
        path = _route_path(route.stops, ctx, route.origin, route.destination)
        if index < len(ids):
            bus_id = ids[index]
        else:
            bus_id = next_id
            next_id += 1
        plans.append(
            BusPlan(
                bus_id=bus_id,
                origin=path[0],
                destination=path[-1],
                stops=path,
                served_passengers=route.passengers,
                travel_time_minutes=route.time_minutes,
                peak_load=route.peak_load,
                score=(
                    route.passengers / route.time_minutes if route.time_minutes else 0.0
                ),
                served_pairs=tuple(route.pairs),
            )
        )

    summary = FleetSummary(
        rounds=0,
        wins_per_bus=(),
        unserved_passengers=attendance.unserved,
        unserved_pairs=attendance.unserved_pairs,
    )
    return plans, summary
