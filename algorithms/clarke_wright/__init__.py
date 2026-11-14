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
    CONSUMO_PADRAO,
    DIESEL_PADRAO,
    INF,
    ITER_POSTIMPROVE,
    ITER_TWO_PHASE,
    LAMBDA_MAX,
    LAMBDA_MIN,
    LAMBDA_PASSO,
    PERIODO_PADRAO,
    RESTRICOES,
)
from .construction import (  # noqa: F401
    _fundir,
    _melhor_direcao,
    _roulette_wheel,
    two_phase_selection,
)
from .context import construir_carga_parada, detectar_sentido, montar_contexto
from .evaluation import (  # noqa: F401
    _instancia_do_contexto,
    _sequencia_simulada,
    avaliar_atendimento,
    limitar_frota,
)
from .improvement import (  # noqa: F401
    _2opt_rota,
    _copiar_rota,
    _shift_10,
    _swap_11,
    post_improvement,
)
from .metrics import (  # noqa: F401
    _atualizar_custo,
    _atualizar_rota,
    _dist_rota,
    _limite_texto,
    _tempo_rota,
    calcular_savings_ovrp,
)
from .model import (
    Atendimento,
    Contexto,
    ModeloOnibus,
    Pair,
    Pairs,
    Restricoes,
    Rota,
    Saving,
    modelo_de_bus,
)
from .report import (  # noqa: F401
    _pares_texto,
    _situacao,
    imprimir_frota,
    imprimir_solucao,
    salvar_resultado,
)
from .scenario import (  # noqa: F401
    ROOT,
    _buscar_cenario,
    _deposito_do_cenario,
    _frota_do_cenario,
    contexto_do_cenario,
    modelo_de_referencia,
    planos_e_resumo,
    resolver_cenario,
)
from .solver import clarke_wright_ovrp

__all__ = [
    "CONSUMO_PADRAO",
    "DIESEL_PADRAO",
    "INF",
    "ITER_POSTIMPROVE",
    "ITER_TWO_PHASE",
    "LAMBDA_MAX",
    "LAMBDA_MIN",
    "LAMBDA_PASSO",
    "PERIODO_PADRAO",
    "RESTRICOES",
    "ROOT",
    "Atendimento",
    "Contexto",
    "ModeloOnibus",
    "Pair",
    "Pairs",
    "Restricoes",
    "Rota",
    "Saving",
    "avaliar_atendimento",
    "calcular_savings_ovrp",
    "clarke_wright_ovrp",
    "construir_carga_parada",
    "contexto_do_cenario",
    "detectar_sentido",
    "imprimir_frota",
    "imprimir_solucao",
    "limitar_frota",
    "main",
    "modelo_de_bus",
    "modelo_de_referencia",
    "montar_contexto",
    "planos_e_resumo",
    "post_improvement",
    "resolver_cenario",
    "salvar_resultado",
    "two_phase_selection",
]
