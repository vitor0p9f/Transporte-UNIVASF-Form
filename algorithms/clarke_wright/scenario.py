"""Entrada de cenário/instância e conversão para o modelo de resultados."""

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
from .evaluation import evaluate_attendance, limit_fleet
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
    if not scenario:
        return None
    origens = parse_node_labels(scenario.get("origin"))
    return origens[0] if origens else None


def reference_model(
    scenario: dict | None, capacity: int, diesel: float
) -> BusModel:
    """Modelo de custo único do cenário, aplicado às DUAS heurísticas.

    Escolhe o ônibus da frota com a capacidade efetiva (o critério que o CW
    sempre usou); sem correspondência, o menor da frota. Sem frota declarada,
    devolve um modelo genérico. O custo operacional dos relatórios usa este
    mesmo modelo para o TOP e para o CW, para que os valores sejam
    comparáveis.
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
    """Resolve um cenário (instância, depósito, frota, limites) num contexto.

    Cada parâmetro explícito vence o que o cenário define; é o mesmo caminho
    que a CLI percorre, exposto para o `main.py` rodar as duas heurísticas
    com exatamente os mesmos limites.

    `max_rotas` é o teto de veículos; omitido, vale o tamanho da frota do
    cenário (None só quando não há frota declarada).
    """
    scenario = scenario or {}
    instance = instance or scenario.get("instance_id")
    if not instance:
        raise ValueError("informe a instância (o cenário não define uma)")
    period = period or scenario.get("period") or DEFAULT_PERIOD
    data = load_instance_data(ROOT / "instances" / instance, period=period)

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
    # Sem capacidade informada, vale a do menor ônibus da frota: assim toda
    # rota que o CW monta cabe em qualquer ônibus do cenário.
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
    """Roda o CW num cenário e devolve a solução já avaliada.

    Devolve `(data, rotas, ctx, atendimento, lambda_usado)` — é o que o
    `main.py` consome para montar a linha do CW na tabela comparativa.
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
    routes = limit_fleet(routes, ctx)
    attendance = evaluate_attendance(routes, ctx)
    return data, routes, ctx, attendance, lambda_used


def plans_and_summary(
    routes: list[Route],
    ctx: Context,
    attendance: Attendance,
    buses: list[Bus] | None = None,
) -> tuple[list[BusPlan], FleetSummary]:
    """Converte a solução do CW no modelo de resultado que o `reporting` lê.

    O CW não tem par travado nem "rounds": a rota nasce no depósito, então
    `origin` é o depósito e `destination` é a última parada. Os ids dos ônibus
    vêm da frota do cenário em ordem; `resolver_cenario` já descarta as rotas
    que passariam do tamanho da frota, mas, numa chamada direta a
    `clarke_wright_ovrp` sem esse teto, os excedentes ainda recebem ids
    sequenciais depois do maior id.
    """
    ids = [bus.id for bus in (buses or [])]
    next_id = (max(ids) + 1) if ids else 1
    plans: list[BusPlan] = []

    for index, route in enumerate(routes):
        if index < len(ids):
            bus_id = ids[index]
        else:
            bus_id = next_id
            next_id += 1
        plans.append(
            BusPlan(
                bus_id=bus_id,
                origin=ctx.depot,
                destination=(
                    route.stops[-1] if route.stops else ctx.depot
                ),
                stops=(ctx.depot, *route.stops),
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
