"""
rodar_todos.py
--------------
Roda o Clarke-Wright OVRP nos 6 turnos com os DADOS REAIS (viagens.csv) e a
matriz de distâncias da pasta stops/ (real, ou a sintética de
gerar_stops_sinteticos.py enquanto a real não chega).

O depósito de cada turno é escolhido automaticamente como a parada de maior
movimento (embarques + desembarques) — tipicamente o campus. O sentido
(ida/volta) é detectado sozinho.

Uso:
    python gerar_stops_sinteticos.py     # 1x, cria stops/ de teste
    python rodar_todos.py                # rápido (CW-1): todos os turnos
    python rodar_todos.py --completo     # CW-1+CW-2+CW-3 (lento: ~2 min/turno)
    python rodar_todos.py --pareto       # tabela custo × superlotação por turno
"""

import argparse

from clarke_wright import clarke_wright_ovrp, imprimir_solucao, analise_pareto
from utils.fleet import ONIBUS_GENERICO
from utils.loader import carregar_tudo
from utils.distance_matrix import (
    carregar_stops_json, construir_matriz, construir_matriz_fallback,
    filtrar_paradas,
)

TURNOS = ["manha_1", "manha_2", "tarde_1", "tarde_2", "noite_1", "noite_2"]


def escolher_deposito(demanda_turno: dict) -> str:
    """Parada de maior movimento (embarques + desembarques) = depósito/hub."""
    return max(demanda_turno.items(),
               key=lambda kv: kv[1]["boarding"] + kv[1]["alighting"])[0]


def main() -> None:
    ap = argparse.ArgumentParser(description="Roda CW-OVRP em todos os turnos (dados reais)")
    ap.add_argument("--completo", action="store_true",
                    help="Usa two-phase + post-improvement (mais preciso, mais lento)")
    ap.add_argument("--pareto", action="store_true",
                    help="Mostra a curva custo × superlotação por turno")
    ap.add_argument("--capacidade", type=int, default=48)
    ap.add_argument("--conforto", type=int, default=None)
    ap.add_argument("--peso-superlotacao", type=float, default=0.0)
    args = ap.parse_args()

    _, demand = carregar_tudo()

    stops = carregar_stops_json()
    if stops:
        nos_all, matriz_all = construir_matriz(stops)
    else:
        print("[aviso] pasta stops/ não encontrada — rode gerar_stops_sinteticos.py")
        nos_all, matriz_all = None, None

    for turno in TURNOS:
        dem = demand.get(turno)
        if not dem:
            continue
        deposito = escolher_deposito(dem)

        if nos_all:
            nos, matriz = filtrar_paradas(nos_all, matriz_all, set(dem) | {deposito})
        else:
            nos, matriz = construir_matriz_fallback(list(set(dem) | {deposito}))

        print(f"\n{'#' * 70}\n# TURNO: {turno}   |   depósito (hub): {deposito}\n{'#' * 70}")

        if args.pareto:
            analise_pareto(nos=nos, matriz=matriz, demanda=dem, deposito=deposito,
                           modelo=ONIBUS_GENERICO, verbose=True)
            continue

        rotas, lam = clarke_wright_ovrp(
            nos=nos, matriz=matriz, demanda=dem, deposito=deposito,
            capacidade=args.capacidade, modelo=ONIBUS_GENERICO,
            usar_two_phase=args.completo, usar_postimprove=args.completo,
            conforto=args.conforto, peso_superlotacao=args.peso_superlotacao,
            verbose=True,
        )
        imprimir_solucao(rotas, deposito, args.capacidade, ONIBUS_GENERICO,
                         turno, lam, conforto=args.conforto)


if __name__ == "__main__":
    main()
