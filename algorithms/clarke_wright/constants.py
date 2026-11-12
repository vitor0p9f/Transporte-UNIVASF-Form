"""Constants and defaults shared by the Clarke-Wright OVRP heuristic."""

LAMBDA_MIN = 0.1  # range de λ conforme artigo (Tabela 1)
LAMBDA_MAX = 2.0
LAMBDA_PASSO = 0.1
ITER_TWO_PHASE = 5000  # iterações da two-phase selection (artigo: 5000)
ITER_POSTIMPROVE = 500  # iterações sem melhora para parar post-improvement

#: Período de demanda usado quando nem a CLI nem o cenário dizem qual.
PERIODO_PADRAO = "morning_1"
#: Preço do litro usado quando o cenário não traz `diesel_price_per_liter`.
DIESEL_PADRAO = 6.00
#: Consumo usado no modelo genérico (km/L), quando não há frota no cenário.
CONSUMO_PADRAO = 3.00

INF = float("inf")

#: Chaves aceitas para escolher quais restrições de rota valem.
#: Cada valor é (checar capacidade, checar tempo).
RESTRICOES = {
    "capacidade": (True, False),
    "tempo": (False, True),
    "ambas": (True, True),
    "nenhuma": (False, False),
}
