from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from application.orienteering.commit import commit_served_demand
from application.orienteering.heuristic import run_greedy_top
from application.orienteering.improve import improve_route_with_two_opt
from application.orienteering.judge import judge_competing_candidates
from application.orienteering.models import BusPlan, DemandState, FleetMove, FleetResult, FleetStep, RouteSimulation
from application.orienteering.planner import rank_candidates
from application.orienteering.prize import DENSITY, prize_for
from application.orienteering.ranking import move_sort_key
from application.orienteering.simulation import simulate_route
from domain.entities.bus import Bus
from domain.entities.graph import Graph


def _served_pairs_map(simulation: RouteSimulation) -> dict[tuple[str, str], int]:
    return {
        (origin, destination): quantity
        for origin, destination, quantity in simulation.served_pairs
    }


def _empty_route_simulation(route_stops: tuple[str, ...]) -> RouteSimulation:
    return RouteSimulation(
        stops=route_stops,
        edges=(),
        total_distance_km=0.0,
        travel_time_minutes=0,
        served_passengers=0,
        peak_load=0,
        route_valid=True,
    )


def evaluate_bus_plan(
    graph: Graph,
    demand_state: DemandState,
    bus: Bus,
    bus_index: int,
    origin_label: str,
    destination_label: str | None,
    time_limit_minutes: int,
    *,
    alpha: float = 1.0,
    score_metric: str = DENSITY,
    candidate_labels: Sequence[str] | None = None,
    max_iterations: int | None = None,
    diesel_price_per_liter: float = 0.0,
    driver_hourly_rate: float = 0.0,
) -> BusPlan:
    result = run_greedy_top(
        graph,
        demand_state,
        bus,
        origin_label,
        destination_label,
        time_limit_minutes,
        alpha=alpha,
        score_metric=score_metric,
        candidate_labels=candidate_labels,
        bus_index=bus_index,
        max_iterations=max_iterations,
    )
    if len(result.route_stops) < 2:
        return BusPlan(
            bus_index=bus_index,
            bus=bus,
            destination_label=None,
            route_stops=result.route_stops,
            prize=0.0,
            simulation=_empty_route_simulation(result.route_stops),
        )
    simulation = simulate_route(
        graph,
        demand_state,
        result.route_stops,
        diesel_price_per_liter=diesel_price_per_liter,
        driver_hourly_rate=driver_hourly_rate,
        km_autonomy_per_liter=bus.km_autonomy_per_liter,
    )
    prize = prize_for(simulation, score_metric, alpha)

    return BusPlan(
        bus_index=bus_index,
        bus=bus,
        destination_label=(
            destination_label if destination_label is not None else result.route_stops[-1]
        ),
        route_stops=result.route_stops,
        prize=prize,
        simulation=simulation,
    )


def evaluate_destination_options(
    graph: Graph,
    demand_state: DemandState,
    bus: Bus,
    bus_index: int,
    origin_label: str,
    destination_labels: Sequence[str],
    time_limit_minutes: int,
    *,
    alpha: float = 1.0,
    score_metric: str = DENSITY,
    candidate_labels: Sequence[str] | None = None,
    max_iterations: int | None = None,
    diesel_price_per_liter: float = 0.0,
    driver_hourly_rate: float = 0.0,
) -> tuple[BusPlan, ...]:
    return tuple(
        evaluate_bus_plan(
            graph,
            demand_state,
            bus,
            bus_index,
            origin_label,
            destination_label,
            time_limit_minutes,
            alpha=alpha,
            score_metric=score_metric,
            candidate_labels=candidate_labels,
            max_iterations=max_iterations,
            diesel_price_per_liter=diesel_price_per_liter,
            driver_hourly_rate=driver_hourly_rate,
        )
        for destination_label in destination_labels
    )


@dataclass
class _FleetBusState:
    bus_index: int
    bus: Bus
    route_stops: tuple[str, ...]
    destination_label: str | None = None


def _locked_destination_moves(
    graph: Graph,
    demand_state: DemandState,
    state: _FleetBusState,
    time_limit_minutes: int,
    *,
    alpha: float = 1.0,
    score_metric: str = DENSITY,
    candidate_labels: Sequence[str] | None = None,
    full_demand_state: DemandState | None = None,
) -> tuple[FleetMove, ...]:
    ranking = tuple(
        rank_candidates(
            graph,
            demand_state,
            state.bus,
            state.route_stops,
            time_limit_minutes,
            candidate_labels=candidate_labels,
            alpha=alpha,
            score_metric=score_metric,
            bus_index=state.bus_index,
            full_demand_state=full_demand_state,
        )
    )
    return tuple(
        FleetMove(
            bus_index=state.bus_index,
            destination_label=state.destination_label,
            route_stops=evaluation.route_stops,
            prize=evaluation.prize,
            simulation=evaluation.simulation,
            locks_destination=False,
        )
        for evaluation in ranking
        if evaluation.feasible
    )


def _destination_lock_moves(
    graph: Graph,
    demand_state: DemandState,
    state: _FleetBusState,
    origin_label: str,
    destination_labels: Sequence[str],
    time_limit_minutes: int,
    *,
    alpha: float = 1.0,
    score_metric: str = DENSITY,
    candidate_labels: Sequence[str] | None = None,
    diesel_price_per_liter: float = 0.0,
    driver_hourly_rate: float = 0.0,
) -> tuple[FleetMove, ...]:
    plans = evaluate_destination_options(
        graph,
        demand_state,
        state.bus,
        state.bus_index,
        origin_label,
        destination_labels,
        time_limit_minutes,
        alpha=alpha,
        score_metric=score_metric,
        candidate_labels=candidate_labels,
        diesel_price_per_liter=diesel_price_per_liter,
        driver_hourly_rate=driver_hourly_rate,
    )
    moves: list[FleetMove] = []
    for plan in plans:
        if not (
            plan.simulation.route_valid
            and plan.simulation.peak_load <= plan.bus.passenger_capacity
            and plan.simulation.served_passengers > 0
        ):
            continue
        moves.append(
            FleetMove(
                bus_index=state.bus_index,
                destination_label=plan.destination_label,
                route_stops=plan.route_stops,
                prize=plan.prize,
                simulation=plan.simulation,
                locks_destination=True,
            )
        )
    return tuple(moves)


def _full_route_moves(
    graph: Graph,
    demand_state: DemandState,
    state: _FleetBusState,
    origin_label: str,
    time_limit_minutes: int,
    *,
    alpha: float = 1.0,
    score_metric: str = DENSITY,
    candidate_labels: Sequence[str] | None = None,
    max_iterations: int | None = None,
    diesel_price_per_liter: float = 0.0,
    driver_hourly_rate: float = 0.0,
) -> tuple[FleetMove, ...]:
    plan = evaluate_bus_plan(
        graph,
        demand_state,
        state.bus,
        state.bus_index,
        origin_label,
        None,
        time_limit_minutes,
        alpha=alpha,
        score_metric=score_metric,
        candidate_labels=candidate_labels,
        max_iterations=max_iterations,
        diesel_price_per_liter=diesel_price_per_liter,
        driver_hourly_rate=driver_hourly_rate,
    )
    if (
        len(plan.route_stops) < 2
        or not plan.simulation.route_valid
        or plan.simulation.peak_load > plan.bus.passenger_capacity
        or plan.simulation.served_passengers <= 0
    ):
        return ()

    return (
        FleetMove(
            bus_index=state.bus_index,
            destination_label=plan.destination_label,
            route_stops=plan.route_stops,
            prize=plan.prize,
            simulation=plan.simulation,
            locks_destination=True,
        ),
    )


def _demand_state_from_pairs(
    served_pairs: dict[tuple[str, str], int],
) -> DemandState:
    boardings: dict[str, int] = {}
    alightings: dict[str, int] = {}
    for (origin, destination), quantity in served_pairs.items():
        boardings[origin] = boardings.get(origin, 0) + quantity
        alightings[destination] = alightings.get(destination, 0) + quantity
    return DemandState(
        boardings_by_label=boardings,
        alightings_by_label=alightings,
        edge_demand=dict(served_pairs),
    )


def run_parallel_fleet_top(
    graph: Graph,
    demand_state: DemandState,
    buses: Sequence[Bus],
    origin_label: str,
    destination_labels: Sequence[str],
    time_limit_minutes: int,
    *,
    alpha: float = 1.0,
    score_metric: str = DENSITY,
    candidate_labels: Sequence[str] | None = None,
    use_two_opt: bool = True,
    diesel_price_per_liter: float = 0.0,
    driver_hourly_rate: float = 0.0,
) -> FleetResult:
    current_state = demand_state
    states = [
        _FleetBusState(bus_index=bus_index, bus=bus, route_stops=(origin_label,))
        for bus_index, bus in enumerate(buses)
    ]
    served_per_bus: list[dict[tuple[str, str], int]] = [{} for _ in buses]
    steps: list[FleetStep] = []
    iteration = 0

    while True:
        iteration += 1
        round_options: list[FleetMove] = []

        for state in states:
            if state.destination_label is None:
                if destination_labels:
                    moves = _destination_lock_moves(
                        graph,
                        current_state,
                        state,
                        origin_label,
                        destination_labels,
                        time_limit_minutes,
                        alpha=alpha,
                        score_metric=score_metric,
                        candidate_labels=candidate_labels,
                        diesel_price_per_liter=diesel_price_per_liter,
                        driver_hourly_rate=driver_hourly_rate,
                    )
                else:
                    moves = _full_route_moves(
                        graph,
                        current_state,
                        state,
                        origin_label,
                        time_limit_minutes,
                        alpha=alpha,
                        score_metric=score_metric,
                        candidate_labels=candidate_labels,
                        diesel_price_per_liter=diesel_price_per_liter,
                        driver_hourly_rate=driver_hourly_rate,
                    )
            else:
                moves = _locked_destination_moves(
                    graph,
                    current_state,
                    state,
                    time_limit_minutes,
                    alpha=alpha,
                    score_metric=score_metric,
                    candidate_labels=candidate_labels,
                    full_demand_state=demand_state,
                )

            if moves:
                round_options.append(max(moves, key=move_sort_key))

        if not round_options:
            break

        chosen = max(round_options, key=move_sort_key)
        chosen_state = states[chosen.bus_index]

        steps.append(
            FleetStep(
                iteration=iteration,
                bus_index=chosen.bus_index,
                route_stops_before=chosen_state.route_stops,
                route_stops_after=chosen.route_stops,
                options=tuple(round_options),
                chosen=chosen,
            )
        )
        chosen_state.route_stops = chosen.route_stops
        if chosen.locks_destination:
            assert chosen.destination_label is not None
            chosen_state.destination_label = chosen.destination_label

        commit_route = chosen.route_stops
        commit_simulation = chosen.simulation
        if chosen.locks_destination and use_two_opt:
            commit_route = improve_route_with_two_opt(
                graph,
                current_state,
                chosen.route_stops,
                chosen_state.bus,
                time_limit_minutes,
            )
            commit_simulation = simulate_route(graph, current_state, commit_route)
            chosen_state.route_stops = commit_route

        served = _served_pairs_map(commit_simulation)
        for (origin, destination), quantity in served.items():
            served_per_bus[chosen.bus_index][(origin, destination)] = (
                served_per_bus[chosen.bus_index].get((origin, destination), 0) + quantity
            )
        current_state = commit_served_demand(current_state, served)

        if not current_state.edge_demand:
            break

    plans: list[BusPlan] = []
    for state in states:
        if state.destination_label is None or not served_per_bus[state.bus_index]:
            continue
        simulation = simulate_route(
            graph,
            _demand_state_from_pairs(served_per_bus[state.bus_index]),
            state.route_stops,
            diesel_price_per_liter=diesel_price_per_liter,
            driver_hourly_rate=driver_hourly_rate,
            km_autonomy_per_liter=state.bus.km_autonomy_per_liter,
        )
        plans.append(
            BusPlan(
                bus_index=state.bus_index,
                bus=state.bus,
                destination_label=state.destination_label,
                route_stops=state.route_stops,
                prize=prize_for(simulation, score_metric, alpha),
                simulation=simulation,
            )
        )

    return FleetResult(
        plans=tuple(plans),
        demand_state=current_state,
        steps=tuple(steps),
        simulation=plans[-1].simulation if plans else None,
    )
