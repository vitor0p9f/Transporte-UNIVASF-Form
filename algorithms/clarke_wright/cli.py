"""Command-line entry point for the Clarke-Wright OVRP."""

import argparse

from .constants import (
    DEFAULT_DIESEL_PRICE,
    DEFAULT_PERIOD,
    ITER_POSTIMPROVE,
    ITER_TWO_PHASE,
    RESTRICTIONS,
)
from .evaluation import evaluate_attendance
from .report import print_fleet, print_solution, save_result
from .scenario import (
    _find_scenario,
    _scenario_fleet,
    scenario_context,
)
from .solver import clarke_wright_ovrp


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clarke-Wright OVRP — Transporte UNIVASF"
    )
    parser.add_argument(
        "--cenario",
        dest="scenario",
        default=None,
        help="scenario_id de scenarios.csv/scenarios_base.csv",
    )
    parser.add_argument(
        "--instancia",
        dest="instance",
        default=None,
        help="instance_id (ex: p1_2_a); padrão: a do cenário",
    )
    parser.add_argument(
        "--periodo",
        dest="period",
        default=None,
        help=f"período de demanda (padrão: {DEFAULT_PERIOD})",
    )
    parser.add_argument(
        "--deposito",
        dest="depot",
        type=int,
        default=None,
        help="nó de origem da frota (padrão: 1º origin do cenário)",
    )
    parser.add_argument(
        "--capacidade",
        dest="capacity",
        type=int,
        default=None,
        help="capacidade efetiva por ônibus (padrão: a menor da frota)",
    )
    parser.add_argument(
        "--limite-tempo",
        dest="max_time",
        type=int,
        default=None,
        help="tempo máximo da rota em minutos (padrão: do cenário)",
    )
    parser.add_argument(
        "--restricao",
        dest="restriction",
        default="ambas",
        choices=list(RESTRICTIONS),
        help="quais restrições a rota precisa respeitar",
    )
    parser.add_argument(
        "--diesel",
        dest="diesel",
        type=float,
        default=None,
        help=f"R$/litro (padrão: do cenário ou {DEFAULT_DIESEL_PRICE})",
    )
    parser.add_argument(
        "--lambda-val",
        dest="lambda_val",
        type=float,
        default=None,
        help="valor fixo de λ (padrão: testa 0.1–2.0)",
    )
    parser.add_argument(
        "--sem-two-phase",
        dest="skip_two_phase",
        action="store_true",
        help="desativa two-phase selection (CW-1 apenas)",
    )
    parser.add_argument(
        "--sem-postimprove",
        dest="skip_post_improvement",
        action="store_true",
        help="desativa post-improvement (CW-1+CW-2 apenas)",
    )
    parser.add_argument(
        "--iteracoes",
        dest="iterations",
        type=int,
        default=ITER_TWO_PHASE,
        help=f"iterações da two-phase (padrão: {ITER_TWO_PHASE})",
    )
    parser.add_argument(
        "--iter-postimprov",
        dest="post_improvement_iterations",
        type=int,
        default=ITER_POSTIMPROVE,
        help=f"iterações sem melhora do CW-3 (padrão: {ITER_POSTIMPROVE})",
    )
    parser.add_argument(
        "--sentido",
        dest="sense",
        default="auto",
        choices=["auto", "ida", "volta"],
        help="ida=carga por embarque; volta=carga por desembarque",
    )
    parser.add_argument(
        "--seed",
        dest="seed",
        type=int,
        default=42,
        help="semente do gerador aleatório (reprodutibilidade)",
    )
    parser.add_argument(
        "--salvar",
        dest="save",
        action="store_true",
        help="salva resultado em algorithms/output/",
    )
    parser.add_argument(
        "--frota",
        dest="fleet",
        action="store_true",
        help="exibe a frota do fleet.csv",
    )
    args = parser.parse_args()

    if args.fleet:
        print_fleet()
        return

    scenario = _find_scenario(args.scenario) if args.scenario else None
    instance = args.instance or (scenario or {}).get("instance_id")
    if not instance:
        parser.error("informe --cenario ou --instancia")

    period = args.period or (scenario or {}).get("period") or DEFAULT_PERIOD
    buses = _scenario_fleet(scenario)

    try:
        _, ctx = scenario_context(
            scenario,
            instance=instance,
            period=period,
            depot=args.depot,
            capacity=args.capacity,
            max_time=args.max_time,
            diesel=args.diesel,
            restrictions=args.restriction,
            sense=args.sense,
        )
    except ValueError as error:
        parser.error(str(error))

    label = f"cenário {scenario['scenario_id']}" if scenario else instance
    print(f"\nInstância: {instance} | período: {period} | {label}")
    if buses:
        print(
            f"Frota do cenário: {len(buses)} ônibus "
            f"[{', '.join(str(b.id) for b in buses)}]"
        )

    routes, lambda_used = clarke_wright_ovrp(
        ctx,
        lam=args.lambda_val,
        use_two_phase=not args.skip_two_phase,
        use_post_improvement=not args.skip_post_improvement,
        iterations=args.iterations,
        post_improvement_iterations=args.post_improvement_iterations,
        seed=args.seed,
        verbose=True,
    )

    attendance = evaluate_attendance(routes, ctx)
    print_solution(routes, ctx, label, lambda_used, attendance=attendance)

    if args.save:
        save_result(routes, ctx, label, lambda_used, attendance=attendance)
