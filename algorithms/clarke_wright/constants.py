"""Constants and defaults shared by the Clarke-Wright OVRP heuristic."""

#: Lambda range from the paper (Table 1).
LAMBDA_MIN = 0.1
LAMBDA_MAX = 2.0
#: Lambda step of the sweep.
LAMBDA_PASSO = 0.1
#: Two-phase selection iterations (paper: 5000).
ITER_TWO_PHASE = 5000
#: Iterations without improvement before post-improvement stops.
ITER_POSTIMPROVE = 500

#: Demand period used when neither the CLI nor the scenario names one.
DEFAULT_PERIOD = "morning_1"
#: Price per litre used when the scenario has no `diesel_price_per_liter`.
DEFAULT_DIESEL_PRICE = 6.00
#: Consumption of the generic model (km/L) when the scenario has no fleet.
DEFAULT_KM_PER_LITER = 3.00

#: Capacity assumed when neither the scenario nor the caller gives one.
DEFAULT_CAPACITY = 48

INF = float("inf")

#: Keys accepted for choosing which route constraints apply.
#: Each value is (check capacity, check time). The keys stay in pt-BR because
#: they are user-facing (CLI choices and report text).
RESTRICTIONS = {
    "capacidade": (True, False),
    "tempo": (False, True),
    "ambas": (True, True),
    "nenhuma": (False, False),
}
