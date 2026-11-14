"""Constants and defaults shared by the Clarke-Wright OVRP heuristic."""

LAMBDA_MIN = 0.1  # range de λ conforme artigo (Tabela 1)
LAMBDA_MAX = 2.0
LAMBDA_PASSO = 0.1
ITER_TWO_PHASE = 5000  # iterações da two-phase selection (artigo: 5000)
ITER_POSTIMPROVE = 500  # iterações sem melhora para parar post-improvement

#: Período de demanda usado quando nem a CLI nem o cenário dizem qual.
DEFAULT_PERIOD = "morning_1"
#: Preço do litro usado quando o cenário não traz `diesel_price_per_liter`.
DEFAULT_DIESEL_PRICE = 6.00
#: Consumo usado no modelo genérico (km/L), quando não há frota no cenário.
DEFAULT_KM_PER_LITER = 3.00

#: Capacidade assumida quando nem o cenário nem o chamador informam uma.
DEFAULT_CAPACITY = 48

INF = float("inf")

#: Chaves aceitas para escolher quais restrições de rota valem.
#: Cada valor é (checar capacidade, checar tempo).
RESTRICTIONS = {
    "capacidade": (True, False),
    "tempo": (False, True),
    "ambas": (True, True),
    "nenhuma": (False, False),
}
