"""
teste.py
--------
Testa o algoritmo Clarke-Wright OVRP com dados sintéticos,
sem precisar do CSV do Supabase.

Uso:
    python teste.py
    python teste.py --turno manha_1
    python teste.py --sem-postimprove    (mais rápido)
    python teste.py --lambda-val 1.2     (testa λ fixo)
"""

import argparse
from clarke_wright import clarke_wright_ovrp, imprimir_solucao, salvar_resultado
from utils.fleet import ONIBUS_GENERICO

# ── Paradas dos turnos (subconjunto real do database.sql) ─────────────────────
PARADAS_POR_TURNO = {
    "manha_1": [
        "UNIVASF Campus Juazeiro",
        "Terminal de Juazeiro",
        "GBarbosa Juazeiro",
        "UNIVASF Campus Petrolina",
        "Supermercado Regente",
        "Feira da COHAB Massangano",
        "Sementeira",
        "Petrape",
        "Plante Bem",
        "Residência Estudantil CCA",
        "UNIVASF Campus CCA",
        "Hospital Veterinário CCA",
    ],
    "tarde_1": [
        "UNIVASF Campus Juazeiro",
        "GBarbosa Juazeiro",
        "Terminal de Juazeiro",
        "UNIVASF Campus Petrolina",
        "Supermercado Regente",
        "Sementeira",
        "Petrape",
        "Feira da COHAB Massangano",
        "Plante Bem",
        "UNIVASF Campus CCA",
        "Hospital Veterinário CCA",
    ],
    "noite_1": [
        "UNIVASF Campus CCA",
        "Residência Estudantil CCA",
        "Feira da COHAB Massangano",
        "Petrape",
        "Sementeira",
        "UNIVASF Campus Petrolina",
        "Supermercado Regente",
        "GBarbosa Juazeiro",
        "Terminal de Juazeiro",
        "UNIVASF Campus Juazeiro",
    ],
}

# ── Matriz de distâncias sintética (km) ───────────────────────────────────────
# Baseada em distâncias aproximadas reais entre os pontos.
# Substitui os stops/*.json enquanto a branch python/VRP não está disponível.
DISTANCIAS_KM = {
    "UNIVASF Campus Petrolina": {
        "UNIVASF Campus Juazeiro":      3.5,
        "Terminal de Juazeiro":         4.2,
        "GBarbosa Juazeiro":            3.8,
        "Supermercado Regente":         1.2,
        "Feira da COHAB Massangano":    8.5,
        "Sementeira":                   4.0,
        "Petrape":                      4.5,
        "Plante Bem":                   9.0,
        "Residência Estudantil CCA":   25.0,
        "UNIVASF Campus CCA":          26.0,
        "Hospital Veterinário CCA":    26.5,
    },
    "UNIVASF Campus Juazeiro": {
        "UNIVASF Campus Petrolina":     3.5,
        "Terminal de Juazeiro":         1.5,
        "GBarbosa Juazeiro":            1.2,
        "Supermercado Regente":         3.8,
        "Feira da COHAB Massangano":    9.5,
        "Sementeira":                   6.0,
        "Petrape":                      6.5,
        "Plante Bem":                  11.0,
        "Residência Estudantil CCA":   27.0,
        "UNIVASF Campus CCA":          28.0,
        "Hospital Veterinário CCA":    28.5,
    },
    "Terminal de Juazeiro": {
        "UNIVASF Campus Petrolina":     4.2,
        "UNIVASF Campus Juazeiro":      1.5,
        "GBarbosa Juazeiro":            0.8,
        "Supermercado Regente":         4.5,
        "Feira da COHAB Massangano":   10.0,
        "Sementeira":                   6.5,
        "Petrape":                      7.0,
        "Plante Bem":                  11.5,
        "Residência Estudantil CCA":   28.0,
        "UNIVASF Campus CCA":          29.0,
        "Hospital Veterinário CCA":    29.5,
    },
    "GBarbosa Juazeiro": {
        "UNIVASF Campus Petrolina":     3.8,
        "UNIVASF Campus Juazeiro":      1.2,
        "Terminal de Juazeiro":         0.8,
        "Supermercado Regente":         4.2,
        "Feira da COHAB Massangano":    9.8,
        "Sementeira":                   6.2,
        "Petrape":                      6.8,
        "Plante Bem":                  11.2,
        "Residência Estudantil CCA":   27.5,
        "UNIVASF Campus CCA":          28.5,
        "Hospital Veterinário CCA":    29.0,
    },
    "Supermercado Regente": {
        "UNIVASF Campus Petrolina":     1.2,
        "UNIVASF Campus Juazeiro":      3.8,
        "Terminal de Juazeiro":         4.5,
        "GBarbosa Juazeiro":            4.2,
        "Feira da COHAB Massangano":    7.5,
        "Sementeira":                   3.0,
        "Petrape":                      3.5,
        "Plante Bem":                   8.0,
        "Residência Estudantil CCA":   24.5,
        "UNIVASF Campus CCA":          25.5,
        "Hospital Veterinário CCA":    26.0,
    },
    "Feira da COHAB Massangano": {
        "UNIVASF Campus Petrolina":     8.5,
        "UNIVASF Campus Juazeiro":      9.5,
        "Terminal de Juazeiro":        10.0,
        "GBarbosa Juazeiro":            9.8,
        "Supermercado Regente":         7.5,
        "Sementeira":                   5.5,
        "Petrape":                      5.0,
        "Plante Bem":                   3.0,
        "Residência Estudantil CCA":   18.0,
        "UNIVASF Campus CCA":          19.0,
        "Hospital Veterinário CCA":    19.5,
    },
    "Sementeira": {
        "UNIVASF Campus Petrolina":     4.0,
        "UNIVASF Campus Juazeiro":      6.0,
        "Terminal de Juazeiro":         6.5,
        "GBarbosa Juazeiro":            6.2,
        "Supermercado Regente":         3.0,
        "Feira da COHAB Massangano":    5.5,
        "Petrape":                      0.8,
        "Plante Bem":                   5.2,
        "Residência Estudantil CCA":   22.0,
        "UNIVASF Campus CCA":          23.0,
        "Hospital Veterinário CCA":    23.5,
    },
    "Petrape": {
        "UNIVASF Campus Petrolina":     4.5,
        "UNIVASF Campus Juazeiro":      6.5,
        "Terminal de Juazeiro":         7.0,
        "GBarbosa Juazeiro":            6.8,
        "Supermercado Regente":         3.5,
        "Feira da COHAB Massangano":    5.0,
        "Sementeira":                   0.8,
        "Plante Bem":                   5.0,
        "Residência Estudantil CCA":   21.5,
        "UNIVASF Campus CCA":          22.5,
        "Hospital Veterinário CCA":    23.0,
    },
    "Plante Bem": {
        "UNIVASF Campus Petrolina":     9.0,
        "UNIVASF Campus Juazeiro":     11.0,
        "Terminal de Juazeiro":        11.5,
        "GBarbosa Juazeiro":           11.2,
        "Supermercado Regente":         8.0,
        "Feira da COHAB Massangano":    3.0,
        "Sementeira":                   5.2,
        "Petrape":                      5.0,
        "Residência Estudantil CCA":   16.0,
        "UNIVASF Campus CCA":          17.0,
        "Hospital Veterinário CCA":    17.5,
    },
    "Residência Estudantil CCA": {
        "UNIVASF Campus Petrolina":    25.0,
        "UNIVASF Campus Juazeiro":     27.0,
        "Terminal de Juazeiro":        28.0,
        "GBarbosa Juazeiro":           27.5,
        "Supermercado Regente":        24.5,
        "Feira da COHAB Massangano":   18.0,
        "Sementeira":                  22.0,
        "Petrape":                     21.5,
        "Plante Bem":                  16.0,
        "UNIVASF Campus CCA":           1.5,
        "Hospital Veterinário CCA":     2.0,
    },
    "UNIVASF Campus CCA": {
        "UNIVASF Campus Petrolina":    26.0,
        "UNIVASF Campus Juazeiro":     28.0,
        "Terminal de Juazeiro":        29.0,
        "GBarbosa Juazeiro":           28.5,
        "Supermercado Regente":        25.5,
        "Feira da COHAB Massangano":   19.0,
        "Sementeira":                  23.0,
        "Petrape":                     22.5,
        "Plante Bem":                  17.0,
        "Residência Estudantil CCA":    1.5,
        "Hospital Veterinário CCA":     0.8,
    },
    "Hospital Veterinário CCA": {
        "UNIVASF Campus Petrolina":    26.5,
        "UNIVASF Campus Juazeiro":     28.5,
        "Terminal de Juazeiro":        29.5,
        "GBarbosa Juazeiro":           29.0,
        "Supermercado Regente":        26.0,
        "Feira da COHAB Massangano":   19.5,
        "Sementeira":                  23.5,
        "Petrape":                     23.0,
        "Plante Bem":                  17.5,
        "Residência Estudantil CCA":    2.0,
        "UNIVASF Campus CCA":           0.8,
    },
}

# ── Demanda sintética (simula respostas do formulário) ────────────────────────
# Valores aproximados para testar o algoritmo.
# Substitua com os dados reais do Supabase quando disponíveis.
DEMANDA_SINTETICA = {
    "manha_1": {
        "UNIVASF Campus Juazeiro":     {"boarding": 15, "alighting": 0,  "avg_load": 2.1},
        "Terminal de Juazeiro":        {"boarding": 8,  "alighting": 0,  "avg_load": 2.5},
        "GBarbosa Juazeiro":           {"boarding": 6,  "alighting": 0,  "avg_load": 2.3},
        "Supermercado Regente":        {"boarding": 10, "alighting": 0,  "avg_load": 2.8},
        "Feira da COHAB Massangano":   {"boarding": 12, "alighting": 0,  "avg_load": 3.2},
        "Sementeira":                  {"boarding": 9,  "alighting": 0,  "avg_load": 3.0},
        "Petrape":                     {"boarding": 7,  "alighting": 0,  "avg_load": 2.9},
        "Plante Bem":                  {"boarding": 5,  "alighting": 0,  "avg_load": 2.7},
        "Residência Estudantil CCA":   {"boarding": 4,  "alighting": 10, "avg_load": 3.5},
        "UNIVASF Campus CCA":          {"boarding": 0,  "alighting": 46, "avg_load": 4.0},
        "Hospital Veterinário CCA":    {"boarding": 0,  "alighting": 20, "avg_load": 3.8},
    },
    "tarde_1": {
        "UNIVASF Campus Juazeiro":     {"boarding": 20, "alighting": 0,  "avg_load": 2.5},
        "GBarbosa Juazeiro":           {"boarding": 5,  "alighting": 0,  "avg_load": 2.0},
        "Terminal de Juazeiro":        {"boarding": 10, "alighting": 0,  "avg_load": 2.8},
        "Supermercado Regente":        {"boarding": 8,  "alighting": 0,  "avg_load": 3.0},
        "Sementeira":                  {"boarding": 12, "alighting": 0,  "avg_load": 3.3},
        "Petrape":                     {"boarding": 6,  "alighting": 0,  "avg_load": 3.1},
        "Feira da COHAB Massangano":   {"boarding": 9,  "alighting": 0,  "avg_load": 2.9},
        "Plante Bem":                  {"boarding": 7,  "alighting": 0,  "avg_load": 2.6},
        "UNIVASF Campus CCA":          {"boarding": 0,  "alighting": 50, "avg_load": 4.2},
        "Hospital Veterinário CCA":    {"boarding": 0,  "alighting": 27, "avg_load": 3.9},
    },
    "noite_1": {
        "UNIVASF Campus CCA":          {"boarding": 25, "alighting": 0,  "avg_load": 4.5},
        "Residência Estudantil CCA":   {"boarding": 8,  "alighting": 0,  "avg_load": 4.0},
        "Feira da COHAB Massangano":   {"boarding": 3,  "alighting": 5,  "avg_load": 3.8},
        "Petrape":                     {"boarding": 0,  "alighting": 8,  "avg_load": 3.2},
        "Sementeira":                  {"boarding": 0,  "alighting": 6,  "avg_load": 3.0},
        "Supermercado Regente":        {"boarding": 0,  "alighting": 7,  "avg_load": 2.5},
        "GBarbosa Juazeiro":           {"boarding": 0,  "alighting": 8,  "avg_load": 2.2},
        "Terminal de Juazeiro":        {"boarding": 0,  "alighting": 5,  "avg_load": 1.8},
        "UNIVASF Campus Juazeiro":     {"boarding": 0,  "alighting": 7,  "avg_load": 1.5},
    },
}

DEPOSITO_POR_TURNO = {
    "manha_1": "UNIVASF Campus Petrolina",
    "tarde_1": "UNIVASF Campus Petrolina",
    "noite_1": "UNIVASF Campus CCA",
}


def montar_nos_e_matriz(turno: str) -> tuple[list[str], dict]:
    """Monta lista de nós e matriz para o turno escolhido."""
    paradas = PARADAS_POR_TURNO.get(turno, [])
    deposito = DEPOSITO_POR_TURNO.get(turno, "UNIVASF Campus Petrolina")

    nos = list({deposito} | set(paradas))

    # Garante simetria na matriz
    matriz: dict[str, dict[str, float]] = {n: {} for n in nos}
    for origem, destinos in DISTANCIAS_KM.items():
        if origem not in matriz:
            continue
        for destino, dist in destinos.items():
            if destino in matriz:
                matriz[origem][destino] = dist
                if origem not in matriz[destino]:
                    matriz[destino][origem] = dist  # simetria

    return nos, matriz


def main():
    parser = argparse.ArgumentParser(description="Teste Clarke-Wright OVRP — dados sintéticos")
    parser.add_argument("--turno",          default="manha_1",
                        choices=list(PARADAS_POR_TURNO.keys()),
                        help="Turno a testar")
    parser.add_argument("--capacidade",     type=int,   default=48)
    parser.add_argument("--lambda-val",     type=float, default=None,
                        help="λ fixo (padrão: busca automática 0.1–2.0)")
    parser.add_argument("--sem-two-phase",  action="store_true",
                        help="Executa só CW-1 (mais rápido)")
    parser.add_argument("--sem-postimprove",action="store_true",
                        help="Pula post-improvement (mais rápido)")
    parser.add_argument("--salvar",         action="store_true",
                        help="Salva resultado em output/")
    parser.add_argument("--todos",          action="store_true",
                        help="Testa todos os turnos disponíveis")
    args = parser.parse_args()

    turnos = list(PARADAS_POR_TURNO.keys()) if args.todos else [args.turno]

    for turno in turnos:
        deposito = DEPOSITO_POR_TURNO[turno]
        nos, matriz = montar_nos_e_matriz(turno)
        demanda = DEMANDA_SINTETICA[turno]

        rotas, lam_usado = clarke_wright_ovrp(
            nos              = nos,
            matriz           = matriz,
            demanda          = demanda,
            deposito         = deposito,
            capacidade       = args.capacidade,
            modelo           = ONIBUS_GENERICO,
            lam              = args.lambda_val,
            usar_two_phase   = not args.sem_two_phase,
            usar_postimprove = not args.sem_postimprove,
            verbose          = True,
        )

        imprimir_solucao(
            rotas      = rotas,
            deposito   = deposito,
            capacidade = args.capacidade,
            modelo     = ONIBUS_GENERICO,
            turno      = turno,
            lam        = lam_usado,
        )

        if args.salvar:
            salvar_resultado(rotas, turno, deposito, ONIBUS_GENERICO, lam_usado)


if __name__ == "__main__":
    main()
