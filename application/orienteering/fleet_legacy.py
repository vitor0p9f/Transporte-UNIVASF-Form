from __future__ import annotations

"""Versão sequencial balanceada da frota (legado).

Substituída por `run_parallel_fleet_top` (application.orienteering.fleet).
Mantida apenas para comparação/referência; o CLI não a utiliza.
"""

from collections.abc import Sequence
from random import Random

from application.orienteering.commit import commit_served_demand
from application.orienteering.fleet import _served_pairs_map, evaluate_destination_options
from application.orienteering.improve import improve_route_with_two_opt
from application.orienteering.models import BusPlan, DemandState, FleetResult, FleetStep, RouteSimulation
from application.orienteering.prize import DENSITY, prize_for
from application.orienteering.simulation import simulate_route
from domain.entities.bus import Bus
from domain.entities.graph import Graph


def select_balanced_bus_plan(
    plans: Sequence[BusPlan],
    destination_usage: dict[str, int],
    rng: Random,
) -> BusPlan | None:
    feasible = [
        plan for plan in plans
        if plan.simulation.route_valid
        and plan.simulation.peak_load <= plan.bus.passenger_capacity
    ]
    if not feasible:
        return None

    min_usage = min(destination_usage.get(plan.destination_label, 0) for plan in feasible)
    pool = [plan for plan in feasible if destination_usage.get(plan.destination_label, 0) == min_usage]

    best_prize = max(plan.prize for plan in pool)
    best_pool = [plan for plan in pool if plan.prize == best_prize]
    if len(best_pool) == 1:
        return best_pool[0]

    ordered = sorted(best_pool, key=lambda plan: (plan.destination_label, plan.bus_index))
    return rng.choice(ordered)


def run_balanced_fleet_top(
    graph: Graph,
    demand_state: DemandState,
    buses: Sequence[Bus],
    origin_label: str,
    destination_labels: Sequence[str],
    time_limit_minutes: int,
    *,
    alpha: float = 1.0,
    score_metric: str = DENSITY,
    seed: int = 0,
    candidate_labels: Sequence[str] | None = None,
    max_iterations: int | None = None,
    use_two_opt: bool = True,
    diesel_price_per_liter: float = 0.0,
    driver_hourly_rate: float = 0.0,
) -> FleetResult:
    rng = Random(seed)
    current_state = demand_state
    destination_usage = {label: 0 for label in destination_labels}
    chosen_plans: list[BusPlan] = []
    steps: list[FleetStep] = []
    final_simulation: RouteSimulation | None = None

    for bus_index, bus in enumerate(buses):
        options = evaluate_destination_options(
            graph,
            current_state,
            bus,
            bus_index,
            origin_label,
            destination_labels,
            time_limit_minutes,
            alpha=alpha,
            score_metric=score_metric,
            candidate_labels=candidate_labels,
            max_iterations=max_iterations,
            diesel_price_per_liter=diesel_price_per_liter,
            driver_hourly_rate=driver_hourly_rate,
        )

        chosen = select_balanced_bus_plan(options, destination_usage, rng)
        if chosen is None:
            continue

        if use_two_opt:
            optimized_route = improve_route_with_two_opt(
                graph,
                current_state,
                chosen.route_stops,
                chosen.bus,
                time_limit_minutes,
            )
            optimized_simulation = simulate_route(
                graph,
                current_state,
                optimized_route,
                diesel_price_per_liter=diesel_price_per_liter,
                driver_hourly_rate=driver_hourly_rate,
                km_autonomy_per_liter=chosen.bus.km_autonomy_per_liter,
            )
            chosen = BusPlan(
                bus_index=chosen.bus_index,
                bus=chosen.bus,
                destination_label=chosen.destination_label,
                route_stops=optimized_route,
                prize=prize_for(optimized_simulation, score_metric, alpha),
                simulation=optimized_simulation,
            )

        if not _served_pairs_map(chosen.simulation):
            continue

        chosen_plans.append(chosen)
        steps.append(
            FleetStep(
                iteration=len(steps) + 1,
                bus_index=bus_index,
                route_stops_before=(origin_label, chosen.destination_label),
                route_stops_after=chosen.route_stops,
                options=options,
                chosen=chosen,
            )
        )
        current_state = commit_served_demand(current_state, _served_pairs_map(chosen.simulation))
        destination_usage[chosen.destination_label] = destination_usage.get(chosen.destination_label, 0) + 1
        final_simulation = chosen.simulation

    return FleetResult(
        plans=tuple(chosen_plans),
        demand_state=current_state,
        steps=tuple(steps),
        simulation=final_simulation,
    )