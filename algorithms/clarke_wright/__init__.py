"""Clarke-Wright OVRP para o transporte universitário UNIVASF.

Os ônibus partem do depósito, percorrem as paradas e FICAM no campus destino —
não retornam ao depósito. Isso caracteriza o OVRP.

Baseado em:
  Pichpibul, T. & Kawtummachai, R. (2013). A Heuristic Approach Based on
  Clarke-Wright Algorithm for Open Vehicle Routing Problem. The Scientific
  World Journal, Article ID 874349.
  https://onlinelibrary.wiley.com/doi/10.1155/2013/874349

  Clarke, G. & Wright, J.W. (1964). Scheduling of vehicles from a central
  depot to a number of delivery points. Operations Research, 12(4), 568–581.
  https://www.jstor.org/stable/167703

Procedimentos implementados (cf. artigo):
  CW-1 : Fórmula OVRP modificada com parâmetro λ
  CW-2 : Construção de rota aberta (sem retorno ao depósito)
  CW-3 : Post-improvement (2-opt, shift 1-0, swap 1-1)

Restrições de rota — a chave `restricoes` decide qual (ou quais) vale:

  "capacidade" : a carga da rota não passa da capacidade do ônibus
  "tempo"      : o tempo da rota não passa do limite do cenário
  "ambas"      : as duas ao mesmo tempo (padrão)
  "nenhuma"    : nenhuma; só a função objetivo decide

A carga de cada parada é ESTÁTICA (embarques na ida, desembarques na volta):
ninguém libera assento no meio da rota. É a leitura do artigo e a projeção que
o CVRP clássico usa (uma demanda por nó) — por isso ela é "demanda alocada",
NÃO "passageiros transportados": nada garante que o destino de quem embarca
esteja na rota.

Para medir o atendimento real (só conta o par origem→destino que cabe na rota,
na ordem), o relatório roda a simulação de embarque/desembarque da heurística
TOP UNIVASF DEPOIS de montar a solução. O algoritmo continua decidindo por
distância + capacidade estática; a simulação é só avaliação
(`avaliar_atendimento`) e não realimenta nenhuma decisão.

Módulos:

    constants    limites, defaults e chaves de restrição
    model        estruturas (contexto, rota, saving, atendimento)
    context      sentido da viagem, carga por parada e montagem do contexto
    metrics      distância, tempo e savings (CW-1)
    objective    combustível + penalidade de superlotação
    construction fusão de rotas e two-phase selection (CW-2)
    improvement  2-opt, shift e swap (CW-3)
    solver       clarke_wright_ovrp e análise de Pareto
    evaluation   simulação de atendimento e corte pela frota
    scenario     leitura do cenário e conversão para o modelo de resultados
    report       impressão, JSON e listagem da frota
    cli          linha de comando

Uso:
    python -m algorithms.clarke_wright --cenario 1
    python -m algorithms.clarke_wright --cenario 2 --restricao tempo --deposito 1
    python -m algorithms.clarke_wright --instancia p1_2_a --periodo morning_1 \
        --deposito 1 --capacidade 32 --limite-tempo 90 --diesel 6.35
    python -m algorithms.clarke_wright --frota
"""

from .cli import main
from .constants import (
    DEFAULT_DIESEL_PRICE,
    DEFAULT_KM_PER_LITER,
    DEFAULT_PERIOD,
    INF,
    ITER_POSTIMPROVE,
    ITER_TWO_PHASE,
    LAMBDA_MAX,
    LAMBDA_MIN,
    LAMBDA_PASSO,
    RESTRICTIONS,
)
from .construction import (  # noqa: F401
    _best_direction,
    _merge,
    _roulette_wheel,
    two_phase_selection,
)
from .context import build_context, build_stop_loads, detect_sense
from .evaluation import (  # noqa: F401
    _instance_from_context,
    _simulated_sequence,
    evaluate_attendance,
    limit_fleet,
)
from .improvement import (  # noqa: F401
    _copy_route,
    _shift_10,
    _swap_11,
    _two_opt_route,
    post_improvement,
)
from .metrics import (  # noqa: F401
    _route_distance,
    _route_time,
    _time_limit_text,
    _update_cost,
    _update_route,
    compute_savings_ovrp,
)
from .model import (
    Attendance,
    BusModel,
    Context,
    Pair,
    Pairs,
    Restrictions,
    Route,
    Saving,
    bus_model,
)
from .report import (  # noqa: F401
    _pairs_text,
    _status,
    print_fleet,
    print_solution,
    save_result,
)
from .scenario import (  # noqa: F401
    ROOT,
    _find_scenario,
    _scenario_depot,
    _scenario_fleet,
    plans_and_summary,
    reference_model,
    scenario_context,
    solve_scenario,
)
from .solver import clarke_wright_ovrp

__all__ = [
    "DEFAULT_CAPACITY",
    "DEFAULT_DIESEL_PRICE",
    "DEFAULT_KM_PER_LITER",
    "DEFAULT_PERIOD",
    "INF",
    "ITER_POSTIMPROVE",
    "ITER_TWO_PHASE",
    "LAMBDA_MAX",
    "LAMBDA_MIN",
    "LAMBDA_PASSO",
    "RESTRICTIONS",
    "ROOT",
    "Attendance",
    "BusModel",
    "Context",
    "Pair",
    "Pairs",
    "Restrictions",
    "Route",
    "Saving",
    "build_context",
    "build_stop_loads",
    "bus_model",
    "clarke_wright_ovrp",
    "compute_savings_ovrp",
    "detect_sense",
    "evaluate_attendance",
    "limit_fleet",
    "main",
    "plans_and_summary",
    "post_improvement",
    "print_fleet",
    "print_solution",
    "reference_model",
    "save_result",
    "scenario_context",
    "solve_scenario",
    "two_phase_selection",
]
