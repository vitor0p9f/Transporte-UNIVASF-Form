"""Command-line entry point for the Clarke-Wright OVRP."""

import argparse

from .constants import (
    DIESEL_PADRAO,
    ITER_POSTIMPROVE,
    ITER_TWO_PHASE,
    PERIODO_PADRAO,
    RESTRICOES,
)
from .evaluation import avaliar_atendimento
from .report import imprimir_frota, imprimir_solucao, salvar_resultado
from .scenario import (
    _buscar_cenario,
    _frota_do_cenario,
    contexto_do_cenario,
)
from .solver import clarke_wright_ovrp


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clarke-Wright OVRP — Transporte UNIVASF"
    )
    parser.add_argument(
        "--cenario",
        default=None,
        help="scenario_id de scenarios.csv/scenarios_base.csv",
    )
    parser.add_argument(
        "--instancia",
        default=None,
        help="instance_id (ex: p1_2_a); padrão: a do cenário",
    )
    parser.add_argument(
        "--periodo",
        default=None,
        help=f"período de demanda (padrão: {PERIODO_PADRAO})",
    )
    parser.add_argument(
        "--deposito",
        type=int,
        default=None,
        help="nó de origem da frota (padrão: 1º origin do cenário)",
    )
    parser.add_argument(
        "--capacidade",
        type=int,
        default=None,
        help="capacidade efetiva por ônibus (padrão: a menor da frota)",
    )
    parser.add_argument(
        "--limite-tempo",
        type=int,
        default=None,
        help="tempo máximo da rota em minutos (padrão: do cenário)",
    )
    parser.add_argument(
        "--restricao",
        default="ambas",
        choices=list(RESTRICOES),
        help="quais restrições a rota precisa respeitar",
    )
    parser.add_argument(
        "--diesel",
        type=float,
        default=None,
        help=f"R$/litro (padrão: do cenário ou {DIESEL_PADRAO})",
    )
    parser.add_argument(
        "--lambda-val",
        type=float,
        default=None,
        help="valor fixo de λ (padrão: testa 0.1–2.0)",
    )
    parser.add_argument(
        "--sem-two-phase",
        action="store_true",
        help="desativa two-phase selection (CW-1 apenas)",
    )
    parser.add_argument(
        "--sem-postimprove",
        action="store_true",
        help="desativa post-improvement (CW-1+CW-2 apenas)",
    )
    parser.add_argument(
        "--iteracoes",
        type=int,
        default=ITER_TWO_PHASE,
        help=f"iterações da two-phase (padrão: {ITER_TWO_PHASE})",
    )
    parser.add_argument(
        "--iter-postimprov",
        type=int,
        default=ITER_POSTIMPROVE,
        help=f"iterações sem melhora do CW-3 (padrão: {ITER_POSTIMPROVE})",
    )
    parser.add_argument(
        "--sentido",
        default="auto",
        choices=["auto", "ida", "volta"],
        help="ida=carga por embarque; volta=carga por desembarque",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="semente do gerador aleatório (reprodutibilidade)",
    )
    parser.add_argument(
        "--salvar",
        action="store_true",
        help="salva resultado em algorithms/output/",
    )
    parser.add_argument(
        "--frota",
        action="store_true",
        help="exibe a frota do fleet.csv",
    )
    args = parser.parse_args()

    if args.frota:
        imprimir_frota()
        return

    cenario = _buscar_cenario(args.cenario) if args.cenario else None
    instancia = args.instancia or (cenario or {}).get("instance_id")
    if not instancia:
        parser.error("informe --cenario ou --instancia")

    periodo = args.periodo or (cenario or {}).get("period") or PERIODO_PADRAO
    buses = _frota_do_cenario(cenario)

    try:
        _, ctx = contexto_do_cenario(
            cenario,
            instancia=instancia,
            periodo=periodo,
            deposito=args.deposito,
            capacidade=args.capacidade,
            limite_tempo=args.limite_tempo,
            diesel=args.diesel,
            restricoes=args.restricao,
            sentido=args.sentido,
        )
    except ValueError as erro:
        parser.error(str(erro))

    rotulo = f"cenário {cenario['scenario_id']}" if cenario else instancia
    print(f"\nInstância: {instancia} | período: {periodo} | {rotulo}")
    if buses:
        print(
            f"Frota do cenário: {len(buses)} ônibus "
            f"[{', '.join(str(b.id) for b in buses)}]"
        )

    rotas, lam_usado = clarke_wright_ovrp(
        ctx,
        lam=args.lambda_val,
        usar_two_phase=not args.sem_two_phase,
        usar_postimprove=not args.sem_postimprove,
        iteracoes=args.iteracoes,
        iter_postimprov=args.iter_postimprov,
        seed=args.seed,
        verbose=True,
    )

    atend = avaliar_atendimento(rotas, ctx)
    imprimir_solucao(rotas, ctx, rotulo, lam_usado, atend=atend)

    if args.salvar:
        salvar_resultado(rotas, ctx, rotulo, lam_usado, atend=atend)
