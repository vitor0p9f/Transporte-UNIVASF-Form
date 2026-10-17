"""UNIVASF TOP heuristic: greedy sequencial com trava no par OD.

Etapa 1 (draft do par): cada ônibus ainda sem par varre as seleções
possíveis (origem, destino) e, para cada par, busca no grafo de demanda
os pontos P com demanda vindo de `o` OU indo para `d`, avaliando o
trecho [o, P, d] (mais a opção direta [o, d]):
    servível = embarques do trecho com trava de capacidade
               (o→P desembarca, então embarca P→d, mais o o→d no caminho)
    score = servível / (tempo[o, P] + tempo[P, d])
Vale o P de maior score. O par NÃO precisa ter demanda direta `o→d`. O
maior score global trava a rota base [o, P, d] primeiro (o ônibus nasce
na origem do par — não há deslocamento vazio) e abate da demanda o que o
trecho embarcou. Os demais repetem sobre a demanda atualizada.

Etapa 2 (rodadas globais): a cada rodada, cada ônibus com par travado
(o, d) propõe um passo guiado pela demanda — ponto novo entra onde o par
manda: `A→B` põe `B` depois de `A` (se `A` é o destino final, cruzada
[..., d, B, d]); `B→Y` põe `B` antes de `Y` (início fixo); em conflito de
ponto ou par, sempre o maior score marginal committa e assume a demanda;
os demais replanejam na rodada seguinte, até estourar tempo/capacidade
ou zerar o score.

`destinations`/`draft_origins` (quando dados) filtram as seleções
possíveis de destino/origem do par.

Módulos:

    model       dados (planos, propostas, estado de trabalho)
    scoring     as três pontuações (par, marginal, plano final)
    simulation  embarque com trava de capacidade e nós candidatos
    draft       etapa 1: melhor par OD e sua rota base
    expansion   etapa 2: inserção de um ponto guiada pela demanda
    conflict    agrupamento das propostas que disputam ponto ou par
    fleet       a rodada: propostas, conflito, commit, planos finais
    solver      solve_scenario: carrega o cenário e chama a frota
"""

from algorithms.top_univasf.draft import best_pair_for_bus
from algorithms.top_univasf.expansion import best_demand_driven_insertion
from algorithms.top_univasf.fleet import collect_proposals, run_fleet
from algorithms.top_univasf.model import (
    BoardingOutcome,
    BusPlan,
    ConflictKey,
    DraftProposal,
    ExpansionProposal,
    FleetSummary,
    Proposal,
    ServedPair,
    StopSequence,
    WorkState,
    fleet_summary,
)
from algorithms.top_univasf.scoring import (
    marginal_pax_per_min,
    od_pair_score,
    pax_per_min,
)
from algorithms.top_univasf.simulation import (
    candidate_nodes,
    simulate_stops,
    stretch_passengers,
)
from algorithms.top_univasf.solver import solve_scenario
from utils.instances import InstanceData

__all__ = [
    "BoardingOutcome",
    "BusPlan",
    "ConflictKey",
    "DraftProposal",
    "ExpansionProposal",
    "FleetSummary",
    "InstanceData",
    "Proposal",
    "ServedPair",
    "StopSequence",
    "WorkState",
    "best_demand_driven_insertion",
    "best_pair_for_bus",
    "candidate_nodes",
    "collect_proposals",
    "fleet_summary",
    "marginal_pax_per_min",
    "od_pair_score",
    "pax_per_min",
    "run_fleet",
    "simulate_stops",
    "solve_scenario",
    "stretch_passengers",
]
