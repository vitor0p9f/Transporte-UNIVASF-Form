"""
clarke_wright.py
----------------
Implementação do algoritmo Clarke-Wright para o problema
OVRP (Open Vehicle Routing Problem) do transporte universitário UNIVASF.

Os ônibus partem do depósito, percorrem as paradas e FICAM no campus
destino — não retornam ao depósito. Isso caracteriza o OVRP.

Baseado em:
  Pichpibul, T. & Kawtummachai, R. (2013). A Heuristic Approach Based
  on Clarke-Wright Algorithm for Open Vehicle Routing Problem.
  The Scientific World Journal, Article ID 874349.
  https://onlinelibrary.wiley.com/doi/10.1155/2013/874349

  Clarke, G. & Wright, J.W. (1964). Scheduling of vehicles from a
  central depot to a number of delivery points. Operations Research,
  12(4), 568–581.
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

A carga de cada parada é ESTÁTICA (embarques na ida, desembarques na
volta): ninguém libera assento no meio da rota. É a leitura do artigo e a
projeção que o CVRP clássico usa (uma demanda por nó) — por isso ela é
"demanda alocada", NÃO "passageiros transportados": nada garante que o
destino de quem embarca esteja na rota.

Para medir o atendimento real (só conta o par origem→destino que cabe na
rota, na ordem), o relatório roda a simulação de embarque/desembarque da
heurística TOP UNIVASF DEPOIS de montar a solução. O algoritmo continua
decidindo por distância + capacidade estática; a simulação é só avaliação
(`avaliar_atendimento`) e não realimenta nenhuma decisão.

Uso:
    python algorithms/clarke_wright.py --cenario 1
    python algorithms/clarke_wright.py --cenario 2 --restricao tempo --deposito 1
    python algorithms/clarke_wright.py --instancia p1_2_a --periodo morning_1 \\
        --deposito 1 --capacidade 32 --limite-tempo 90 --diesel 6.35
    python algorithms/clarke_wright.py --frota
"""

import argparse
import itertools
import json
import random
import sys
from dataclasses import dataclass, field, replace
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Imports must follow the sys.path setup above (same pattern as scripts/run_all.py).
from algorithms.top_univasf.model import BusPlan, FleetSummary
from algorithms.top_univasf.simulation import simulate_stops
from entities.bus import Bus
from utils.fleet import load_fleet, parse_fleet_ids
from utils.instances import InstanceData, load_instance_data
from utils.scenarios import load_scenarios, parse_node_labels

# ── Constantes ────────────────────────────────────────────────────────────────

LAMBDA_MIN       = 0.1    # range de λ conforme artigo (Tabela 1)
LAMBDA_MAX       = 2.0
LAMBDA_PASSO     = 0.1
ITER_TWO_PHASE   = 5000   # iterações da two-phase selection (artigo: 5000)
ITER_POSTIMPROVE = 500    # iterações sem melhora para parar post-improvement

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


# ── Estruturas de dados ───────────────────────────────────────────────────────

@dataclass(frozen=True)
class Restricoes:
    """Quais restrições de rota estão ativas nesta execução.

    Construa pela chave (`Restricoes.da_chave("tempo")`) para não errar a
    combinação; a CLI e `montar_contexto` só aceitam as chaves de `RESTRICOES`.
    """

    capacidade: bool = True
    tempo: bool = True

    @classmethod
    def da_chave(cls, chave: str) -> "Restricoes":
        try:
            ativa_capacidade, ativo_tempo = RESTRICOES[chave]
        except KeyError:
            validas = ", ".join(RESTRICOES)
            raise ValueError(
                f"restrição '{chave}' desconhecida (use: {validas})"
            ) from None
        return cls(capacidade=ativa_capacidade, tempo=ativo_tempo)

    @property
    def chave(self) -> str:
        """A chave ("capacidade"/"tempo"/"ambas"/"nenhuma") desta combinação."""
        for chave, (capacidade, tempo) in RESTRICOES.items():
            if (capacidade, tempo) == (self.capacidade, self.tempo):
                return chave
        return "custom"


@dataclass(frozen=True)
class ModeloOnibus:
    """Modelo de custo do veículo: litros por km e preço do litro.

    Substitui o antigo `utils.fleet.ModeloOnibus`; os dados vêm de uma linha
    do `fleet.csv` (capacidade e autonomia) e do cenário (preço do diesel).
    """

    nome: str
    capacidade: int
    consumo_km_l: float
    custo_litro: float
    capacidade_conforto: int | None = None

    @property
    def custo_por_km(self) -> float:
        return self.custo_litro / self.consumo_km_l

    def custo_rota(self, dist_km: float) -> float:
        return dist_km * self.custo_por_km


def modelo_de_bus(bus: Bus, custo_litro: float) -> ModeloOnibus:
    """Converte uma linha do `fleet.csv` no modelo de custo do algoritmo."""
    if bus.km_autonomy_per_liter <= 0:
        raise ValueError(f"bus {bus.id}: km_autonomy_per_liter deve ser > 0")
    return ModeloOnibus(
        nome=f"ônibus {bus.id}",
        capacidade=bus.passenger_capacity,
        consumo_km_l=bus.km_autonomy_per_liter,
        custo_litro=custo_litro,
    )


@dataclass(frozen=True)
class Contexto:
    """Tudo o que uma rota precisa para ser medida e validada.

    Carrega as duas matrizes (distância e tempo), o depósito, os limites e a
    chave de restrições. É ele que as funções internas recebem, em vez dos
    seis ou sete parâmetros soltos de antes.

    `carga_parada` é a projeção do CVRP (demanda por nó, o que as decisões
    usam); `demanda` é a matriz OD crua, lida só pela avaliação de
    atendimento por simulação.
    """

    distancia: np.ndarray
    tempo: np.ndarray
    deposito: int
    capacidade: int
    limite_tempo: float
    modelo: ModeloOnibus
    carga_parada: dict[int, int]
    demanda: np.ndarray
    restricoes: Restricoes = field(default_factory=Restricoes)
    sentido: str = "ida"

    def cabe(self, carga: int, minutos: float) -> bool:
        """Ponto único da chave: só valida a(s) restrição(ões) ativa(s)."""
        if self.restricoes.capacidade and carga > self.capacidade:
            return False
        return not self.restricoes.tempo or minutos <= self.limite_tempo


@dataclass
class Saving:
    """Par (i, j) com o valor de economia calculado."""
    i:     int
    j:     int
    valor: float

    def __lt__(self, other):
        return self.valor > other.valor  # ordenação decrescente


@dataclass
class Rota:
    """
    Rota aberta: depot → p1 → p2 → ... → pn  (sem retorno ao depósito).
    """
    paradas:    list[int] = field(default_factory=list)
    carga:      int       = 0       # demanda alocada (projeção do CVRP)
    dist_km:    float     = 0.0     # distância total da rota (km)
    tempo_min:  int       = 0       # tempo total da rota (min)
    custo_brl:  float     = 0.0     # custo de combustível (R$)
    pax:        int       = 0       # pax atendidos (simulação, pós-solução)
    pico:       int       = 0       # ocupação máxima simultânea (simulação)
    pares:      tuple     = ()      # (origem, destino, qtd) embarcados

    def primeira(self) -> int:
        return self.paradas[0]

    def ultima(self) -> int:
        return self.paradas[-1]

    def __repr__(self) -> str:
        return (
            f"Rota({len(self.paradas)} paradas | "
            f"{self.carga} aloc. | "
            f"{self.pax} pax | "
            f"{self.dist_km:.1f} km | "
            f"{self.tempo_min} min | "
            f"R${self.custo_brl:.2f})"
        )


# ── Medidas de rota (OVRP: sem retorno ao depósito) ──────────────────────────

def _dist_rota(paradas: list[int], ctx: Contexto) -> float:
    """
    Distância total da rota aberta: depot → p1 → p2 → ... → pn.
    Não inclui retorno ao depósito (OVRP).
    """
    if not paradas:
        return 0.0
    dist = float(ctx.distancia[ctx.deposito, paradas[0]])
    for a, b in itertools.pairwise(paradas):
        dist += float(ctx.distancia[a, b])
    return round(dist, 4)


def _tempo_rota(paradas: list[int], ctx: Contexto) -> int:
    """Tempo total da rota aberta, em minutos (matriz `time` do cenário)."""
    if not paradas:
        return 0
    total = int(ctx.tempo[ctx.deposito, paradas[0]])
    for a, b in itertools.pairwise(paradas):
        total += int(ctx.tempo[a, b])
    return total


def _atualizar_custo(rota: Rota, ctx: Contexto) -> Rota:
    """Recalcula dist_km, tempo_min e custo_brl da rota."""
    rota.dist_km   = _dist_rota(rota.paradas, ctx)
    rota.tempo_min = _tempo_rota(rota.paradas, ctx)
    rota.custo_brl = ctx.modelo.custo_rota(rota.dist_km)
    return rota


# ── Fórmula de savings OVRP (CW-1) ───────────────────────────────────────────

def calcular_savings_ovrp(
    paradas: list[int],
    ctx:     Contexto,
    lam:     float,
) -> list[Saving]:
    """
    Fórmula OVRP modificada (equação 5 do artigo):

        s(i,j) = c(depot, j) - λ · c(i, j)

    Diferença em relação ao CVRP: remove o termo c(i, depot)
    pois o veículo não retorna ao depósito após visitar i.

    Args:
        paradas : lista de paradas (sem o depósito)
        ctx     : matriz de distâncias + depósito
        lam     : parâmetro de forma λ ∈ [0.1, 2.0]
    """
    savings = []
    for idx_i in range(len(paradas)):
        for idx_j in range(idx_i + 1, len(paradas)):
            pi, pj = paradas[idx_i], paradas[idx_j]

            # Equação 5 do artigo (OVRP com λ)
            s = float(ctx.distancia[ctx.deposito, pj]) - lam * float(
                ctx.distancia[pi, pj]
            )
            savings.append(Saving(i=pi, j=pj, valor=round(s, 6)))

    savings.sort()  # decrescente via __lt__
    return savings


# ── Sentido da viagem e carga por parada ─────────────────────────────────────

def detectar_sentido(demanda: np.ndarray, deposito: int) -> str:
    """
    Detecta se a viagem é de "ida" ou de "volta" a partir de onde a demanda
    se concentra no depósito.

      - "volta"  : o depósito é o campus de onde as pessoas SAEM (embarcam ali).
                   A carga de cada parada é o nº de DESEMBARQUES (alighting),
                   pois é quanta gente desce naquele ponto.
      - "ida"    : o depósito é a origem e as pessoas embarcam nas paradas rumo
                   ao campus. A carga é o nº de EMBARQUES (boarding).
    """
    embarques   = int(demanda[deposito].sum())     # quem sai do depósito
    desembarques = int(demanda[:, deposito].sum())  # quem chega no depósito
    return "volta" if embarques > desembarques else "ida"


def construir_carga_parada(
    demanda: np.ndarray,
    deposito: int,
    sentido: str = "auto",
) -> tuple[dict[int, int], str]:
    """
    Calcula a carga (passageiros que o ônibus transporta) de cada parada,
    conforme o sentido da viagem. Retorna (carga_parada, sentido_usado).

    Na ida a carga vem dos embarques (linha da matriz); na volta, dos
    desembarques (coluna) — porque na volta quase todos embarcam no campus
    (depósito) e a demanda real de cada parada é quanta gente DESCE ali.
    """
    if sentido not in ("auto", "ida", "volta"):
        raise ValueError(f"sentido '{sentido}' desconhecido (use: auto, ida, volta)")
    if sentido == "auto":
        sentido = detectar_sentido(demanda, deposito)

    por_no = demanda.sum(axis=0) if sentido == "volta" else demanda.sum(axis=1)
    carga_parada = {
        no: int(por_no[no])
        for no in range(1, len(por_no))
        if no != deposito and por_no[no] > 0
    }
    return carga_parada, sentido


def montar_contexto(
    data:          InstanceData,
    deposito:      int,
    *,
    capacidade:    int | None = None,
    limite_tempo:  float | None = None,
    modelo:        ModeloOnibus | None = None,
    restricoes:    Restricoes | str = "ambas",
    sentido:       str = "auto",
) -> Contexto:
    """Resolve os limites, a chave de restrições e a carga por parada.

    `capacidade` e `limite_tempo` são independentes do modelo e do cenário:
    quando omitidos, vêm dele(s). Sem limite de tempo a restrição "tempo" não
    tem efeito; sem capacidade informada, vale a do modelo.
    """
    if isinstance(restricoes, str):
        restricoes = Restricoes.da_chave(restricoes)

    if modelo is None:
        capacidade_modelo = capacidade if capacidade is not None else 48
        modelo = ModeloOnibus(
            nome="genérico",
            capacidade=capacidade_modelo,
            consumo_km_l=CONSUMO_PADRAO,
            custo_litro=DIESEL_PADRAO,
        )
    if capacidade is None:
        capacidade = modelo.capacidade
    if limite_tempo is None:
        limite_tempo = INF

    carga_parada, sentido_usado = construir_carga_parada(
        data.demand, deposito, sentido
    )
    return Contexto(
        # float evita surpresa se a instância trouxer a distância como int
        distancia=data.distance.astype(float, copy=False),
        tempo=data.time,
        deposito=deposito,
        capacidade=capacidade,
        limite_tempo=limite_tempo,
        modelo=modelo,
        carga_parada=carga_parada,
        demanda=data.demand,
        restricoes=restricoes,
        sentido=sentido_usado,
    )


# ── Função objetivo: combustível + penalidade de superlotação ────────────────

def _excesso(carga: int, conforto: int) -> int:
    """Passageiros acima da capacidade de conforto (0 se dentro do conforto)."""
    return max(0, carga - conforto)


def _obj_rota(rota: Rota, peso_superlotacao: float, conforto: int) -> float:
    """
    Custo de uma rota para fins de otimização:
        custo_combustível + peso · (passageiros em desconforto)

    Com peso_superlotacao = 0 recai no custo puro (comportamento original).
    Com peso > 0 o algoritmo passa a EVITAR ônibus lotados além do conforto,
    redistribuindo passageiros mesmo que custe um pouco mais de combustível.
    """
    return rota.custo_brl + peso_superlotacao * _excesso(rota.carga, conforto)


def _obj_total(rotas: list[Rota], peso_superlotacao: float, conforto: int) -> float:
    return sum(_obj_rota(r, peso_superlotacao, conforto) for r in rotas)


# ── Construção OVRP (CW-2): rota aberta em dois sentidos ─────────────────────

def _melhor_direcao(paradas: list[int], ctx: Contexto) -> list[int]:
    """
    Procedimento CW-2 do artigo: testa as duas direções possíveis da rota
    aberta (forward e reverse) e retorna a de menor distância.

    Em OVRP:
      forward : depot → p1 → p2 → ... → pn   (distância D_f)
      reverse : depot → pn → p(n-1) → ... → p1 (distância D_r)

    Com a restrição de tempo ativa a direção não é indiferente (o primeiro
    trecho sai do depósito), então direções que já estouram o limite são
    descartadas antes de escolher a mais curta. Se nenhuma couber, devolve a
    mais curta e quem chamou rejeita a rota em `Contexto.cabe`.
    """
    direcoes = [list(paradas), list(reversed(paradas))]
    if ctx.restricoes.tempo:
        viaveis = [d for d in direcoes if _tempo_rota(d, ctx) <= ctx.limite_tempo]
        if viaveis:
            direcoes = viaveis
    return min(direcoes, key=lambda d: _dist_rota(d, ctx))


# ── Fusão de rotas ─────────────────────────────────────────────────────────────

def _fundir(
    savings:        list[Saving],
    paradas_ativas: set[int],
    ctx:            Contexto,
) -> list[Rota]:
    """
    Procedimento de fusão (route merging) do Clarke-Wright paralelo.

    Para cada saving s(i,j) em ordem decrescente:
      - Se i e j estão em rotas diferentes
      - Se a fusão não viola a(s) restrição(ões) ativa(s) (capacidade/tempo)
      - Se i é extremo (início ou fim) da sua rota
      - Se j é extremo da sua rota
      → funde as rotas

    Uma parada cuja demanda sozinha já estoura o limite continua virando rota
    própria (o algoritmo não descarta demanda); o relatório sinaliza o caso.
    """
    # Solução inicial: uma rota por parada
    rotas: dict[int, Rota] = {}
    extremo: dict[int, Rota] = {}   # extremo → rota que o contém

    for p in sorted(paradas_ativas):   # ordem fixa → resultado reprodutível
        r = Rota(paradas=[p], carga=ctx.carga_parada.get(p, 0))
        _atualizar_custo(r, ctx)
        rotas[id(r)] = r
        extremo[p] = r

    for s in savings:
        ri = extremo.get(s.i)
        rj = extremo.get(s.j)

        if ri is None or rj is None or ri is rj:
            continue

        carga = ri.carga + rj.carga
        if ctx.restricoes.capacidade and carga > ctx.capacidade:
            continue

        nova_ordem = None

        if ri.ultima() == s.i and rj.primeira() == s.j:
            nova_ordem = ri.paradas + rj.paradas
        elif rj.ultima() == s.j and ri.primeira() == s.i:
            nova_ordem = rj.paradas + ri.paradas
        elif ri.ultima() == s.i and rj.ultima() == s.j:
            nova_ordem = ri.paradas + list(reversed(rj.paradas))
        elif ri.primeira() == s.i and rj.primeira() == s.j:
            nova_ordem = list(reversed(ri.paradas)) + rj.paradas

        if nova_ordem is None:
            continue

        # Aplica CW-2: escolhe a melhor direção da rota aberta
        nova_ordem = _melhor_direcao(nova_ordem, ctx)
        if not ctx.cabe(carga, _tempo_rota(nova_ordem, ctx)):
            continue

        nova_rota = Rota(paradas=nova_ordem, carga=carga)
        _atualizar_custo(nova_rota, ctx)

        # Remove rotas antigas
        rotas.pop(id(ri), None)
        rotas.pop(id(rj), None)
        for p in ri.paradas + rj.paradas:
            extremo.pop(p, None)

        # Registra nova rota
        rotas[id(nova_rota)] = nova_rota
        extremo[nova_rota.primeira()] = nova_rota
        extremo[nova_rota.ultima()]   = nova_rota

    return list(rotas.values())


# ── Two-Phase Selection (CW-2 do artigo) ─────────────────────────────────────

def _roulette_wheel(savings: list[Saving], T: int) -> list[Saving]:
    """
    Seleção por roleta sobre os T melhores savings (seção 2.3 do artigo).

    Reconstrói a lista de savings embaralhando probabilisticamente
    os T melhores a cada iteração — explora ordens de fusão diferentes.

    Probabilidade (eq. do artigo): p_n = s_n / Σ s_i, favorecendo savings
    MAIORES. Como em OVRP s(i,j)=c(depot,j)-λ·c(i,j) pode ser negativo,
    deslocamos a janela pelo menor valor (em vez de usar abs(), que
    favoreceria erroneamente savings muito negativos).
    """
    if len(savings) <= 1:
        return list(savings)

    nova_lista = []
    restantes = list(savings)

    while restantes:
        t = min(T, len(restantes))
        candidatos = restantes[:t]

        menor = min(s.valor for s in candidatos)
        pesos = [s.valor - menor + 1e-9 for s in candidatos]
        soma  = sum(pesos)

        r = random.random() * soma
        acumulado = 0.0
        idx = t - 1
        for k, w in enumerate(pesos):
            acumulado += w
            if r <= acumulado:
                idx = k
                break

        nova_lista.append(restantes.pop(idx))

    return nova_lista


def two_phase_selection(
    savings:          list[Saving],
    paradas_ativas:   set[int],
    ctx:              Contexto,
    iteracoes:        int = ITER_TWO_PHASE,
    peso_superlotacao: float = 0.0,
    conforto:         int | None = None,
) -> list[Rota]:
    """
    Procedimento CW-2 do artigo: iterativamente reordena a lista de savings
    via roleta e verifica se a nova solução melhora a atual.
    """
    if conforto is None:
        conforto = ctx.modelo.capacidade_conforto or ctx.capacidade

    melhor_rotas = _fundir(savings, paradas_ativas, ctx)
    melhor_custo = _obj_total(melhor_rotas, peso_superlotacao, conforto)

    savings_atual = list(savings)

    for _ in range(iteracoes):
        # Tamanho do torneio T ∈ [3, 6] conforme o artigo (seção 2.3).
        T = random.randint(3, min(6, max(3, len(savings_atual))))
        nova_ordem = _roulette_wheel(savings_atual, T)
        novas_rotas = _fundir(nova_ordem, paradas_ativas, ctx)
        novo_custo = _obj_total(novas_rotas, peso_superlotacao, conforto)

        if novo_custo < melhor_custo:
            melhor_custo  = novo_custo
            melhor_rotas  = novas_rotas
            savings_atual = nova_ordem

    return melhor_rotas


# ── Post-improvement (CW-3 do artigo) ────────────────────────────────────────

def _custo_total(rotas: list[Rota]) -> float:
    return sum(r.custo_brl for r in rotas)


def _2opt_rota(rota: Rota, ctx: Contexto) -> Rota:
    """
    2-opt intra-rota: inverte segmentos internos e mantém o melhor.
    Aplica CW-2 (melhor direção) após cada melhoria.

    A carga não muda, mas o tempo pode: com a restrição ativa, candidato que
    estoura o limite é descartado (a distância cair não garante tempo menor).
    """
    paradas = list(rota.paradas)

    melhorou = True
    while melhorou:
        melhorou = False
        dist_atual = _dist_rota(paradas, ctx)
        for i in range(len(paradas) - 1):
            for j in range(i + 2, len(paradas)):
                nova = (
                    paradas[: i + 1]
                    + list(reversed(paradas[i + 1 : j + 1]))
                    + paradas[j + 1 :]
                )
                nova = _melhor_direcao(nova, ctx)
                if not ctx.cabe(rota.carga, _tempo_rota(nova, ctx)):
                    continue
                d_nova = _dist_rota(nova, ctx)
                if d_nova < dist_atual - 1e-6:
                    paradas = nova
                    dist_atual = d_nova
                    melhorou = True

    rota.paradas = paradas
    return _atualizar_custo(rota, ctx)


def _shift_10(
    rotas:   list[Rota],
    ctx:     Contexto,
    peso_superlotacao: float = 0.0,
    conforto: int | None = None,
) -> list[Rota]:
    """
    Shift 1-0: move uma parada de uma rota para outra.
    Aceita se não violar a(s) restrição(ões) ativa(s) e se reduzir o objetivo
    (combustível + penalidade de superlotação). Atualiza a carga das rotas.
    """
    if conforto is None:
        conforto = ctx.modelo.capacidade_conforto or ctx.capacidade
    melhorou = True
    while melhorou:
        melhorou = False
        for a in range(len(rotas)):
            for pos_i in range(len(rotas[a].paradas)):
                parada = rotas[a].paradas[pos_i]
                delta  = ctx.carga_parada.get(parada, 0)

                for b in range(len(rotas)):
                    if a == b:
                        continue

                    carga_a = rotas[a].carga - delta
                    carga_b = rotas[b].carga + delta
                    if ctx.restricoes.capacidade and carga_b > ctx.capacidade:
                        continue

                    obj_antes = (_obj_rota(rotas[a], peso_superlotacao, conforto)
                                 + _obj_rota(rotas[b], peso_superlotacao, conforto))

                    # Testa inserção no início e fim da rota b
                    for pos_j in [0, len(rotas[b].paradas)]:
                        novas_a = list(rotas[a].paradas)
                        novas_a.pop(pos_i)
                        novas_b = list(rotas[b].paradas)
                        novas_b.insert(pos_j, parada)

                        if not novas_a:
                            continue  # não cria rota vazia

                        novas_a = _melhor_direcao(novas_a, ctx)
                        novas_b = _melhor_direcao(novas_b, ctx)
                        if not (ctx.cabe(carga_a, _tempo_rota(novas_a, ctx))
                                and ctx.cabe(carga_b, _tempo_rota(novas_b, ctx))):
                            continue

                        dist_a = _dist_rota(novas_a, ctx)
                        dist_b = _dist_rota(novas_b, ctx)
                        custo_a = ctx.modelo.custo_rota(dist_a)
                        custo_b = ctx.modelo.custo_rota(dist_b)
                        obj_depois = (custo_a + peso_superlotacao * _excesso(carga_a, conforto)
                                      + custo_b + peso_superlotacao * _excesso(carga_b, conforto))

                        if obj_depois < obj_antes - 1e-6:
                            rotas[a].paradas   = novas_a
                            rotas[a].dist_km   = dist_a
                            rotas[a].tempo_min = _tempo_rota(novas_a, ctx)
                            rotas[a].custo_brl = custo_a
                            rotas[a].carga     = carga_a

                            rotas[b].paradas   = novas_b
                            rotas[b].dist_km   = dist_b
                            rotas[b].tempo_min = _tempo_rota(novas_b, ctx)
                            rotas[b].custo_brl = custo_b
                            rotas[b].carga     = carga_b

                            melhorou = True
                            break
                    if melhorou:
                        break
                if melhorou:
                    break
            if melhorou:
                break

    return rotas


def _swap_11(
    rotas:   list[Rota],
    ctx:     Contexto,
    peso_superlotacao: float = 0.0,
    conforto: int | None = None,
) -> list[Rota]:
    """
    Swap 1-1: troca uma parada entre duas rotas.
    Aceita se não violar a(s) restrição(ões) ativa(s) e se reduzir o objetivo
    (combustível + penalidade de superlotação). Atualiza a carga das rotas.
    """
    if conforto is None:
        conforto = ctx.modelo.capacidade_conforto or ctx.capacidade
    melhorou = True
    while melhorou:
        melhorou = False
        for a in range(len(rotas)):
            for b in range(a + 1, len(rotas)):
                for pos_i in range(len(rotas[a].paradas)):
                    for pos_j in range(len(rotas[b].paradas)):
                        pi = rotas[a].paradas[pos_i]
                        pj = rotas[b].paradas[pos_j]
                        cp_i = ctx.carga_parada.get(pi, 0)
                        cp_j = ctx.carga_parada.get(pj, 0)

                        carga_a = rotas[a].carga - cp_i + cp_j
                        carga_b = rotas[b].carga - cp_j + cp_i
                        if ctx.restricoes.capacidade and (
                            carga_a > ctx.capacidade or carga_b > ctx.capacidade
                        ):
                            continue

                        obj_antes = (_obj_rota(rotas[a], peso_superlotacao, conforto)
                                     + _obj_rota(rotas[b], peso_superlotacao, conforto))

                        novas_a = list(rotas[a].paradas)
                        novas_b = list(rotas[b].paradas)
                        novas_a[pos_i] = pj
                        novas_b[pos_j] = pi

                        novas_a = _melhor_direcao(novas_a, ctx)
                        novas_b = _melhor_direcao(novas_b, ctx)
                        if not (ctx.cabe(carga_a, _tempo_rota(novas_a, ctx))
                                and ctx.cabe(carga_b, _tempo_rota(novas_b, ctx))):
                            continue

                        dist_a = _dist_rota(novas_a, ctx)
                        dist_b = _dist_rota(novas_b, ctx)
                        custo_a = ctx.modelo.custo_rota(dist_a)
                        custo_b = ctx.modelo.custo_rota(dist_b)
                        obj_depois = (custo_a + peso_superlotacao * _excesso(carga_a, conforto)
                                      + custo_b + peso_superlotacao * _excesso(carga_b, conforto))

                        if obj_depois < obj_antes - 1e-6:
                            rotas[a].paradas   = novas_a
                            rotas[a].dist_km   = dist_a
                            rotas[a].tempo_min = _tempo_rota(novas_a, ctx)
                            rotas[a].custo_brl = custo_a
                            rotas[a].carga     = carga_a

                            rotas[b].paradas   = novas_b
                            rotas[b].dist_km   = dist_b
                            rotas[b].tempo_min = _tempo_rota(novas_b, ctx)
                            rotas[b].custo_brl = custo_b
                            rotas[b].carga     = carga_b

                            melhorou = True
                            break
                    if melhorou:
                        break
                if melhorou:
                    break
            if melhorou:
                break

    return rotas


def post_improvement(
    rotas:      list[Rota],
    ctx:        Contexto,
    max_iter_sem_melhora: int = ITER_POSTIMPROVE,
    peso_superlotacao: float = 0.0,
    conforto:   int | None = None,
) -> list[Rota]:
    """
    Procedimento CW-3 do artigo: aplica operadores de busca local
    até não haver mais melhorias.

    Operadores (com igual probabilidade, conforme Tabela 1 do artigo):
      - 2-opt intra-rota
      - shift 1-0 inter-rotas
      - swap 1-1 inter-rotas

    Com peso_superlotacao > 0 os operadores inter-rotas também redistribuem
    passageiros para aliviar ônibus lotados além do conforto.
    """
    if conforto is None:
        conforto = ctx.modelo.capacidade_conforto or ctx.capacidade

    rotas = [_copiar_rota(r) for r in rotas]
    melhor_custo = _obj_total(rotas, peso_superlotacao, conforto)
    iter_sem_melhora = 0

    operadores = [
        lambda r: [_2opt_rota(x, ctx) for x in r],
        lambda r: _shift_10(r, ctx, peso_superlotacao, conforto),
        lambda r: _swap_11(r, ctx, peso_superlotacao, conforto),
    ]

    while iter_sem_melhora < max_iter_sem_melhora:
        op = random.choice(operadores)
        rotas_novas = op(rotas)
        novo_custo  = _obj_total(rotas_novas, peso_superlotacao, conforto)

        if novo_custo < melhor_custo - 1e-6:
            melhor_custo     = novo_custo
            rotas            = rotas_novas
            iter_sem_melhora = 0
        else:
            iter_sem_melhora += 1

    return rotas


def _copiar_rota(rota: Rota) -> Rota:
    """Cópia da rota: os operadores do CW-3 a mutam no lugar."""
    return Rota(
        paradas=list(rota.paradas),
        carga=rota.carga,
        dist_km=rota.dist_km,
        tempo_min=rota.tempo_min,
        custo_brl=rota.custo_brl,
    )


# ── Algoritmo principal ───────────────────────────────────────────────────────

def clarke_wright_ovrp(
    ctx:              Contexto,
    lam:              float | None = None,
    usar_two_phase:   bool = True,
    usar_postimprove: bool = True,
    iteracoes:        int = ITER_TWO_PHASE,
    iter_postimprov:  int = ITER_POSTIMPROVE,
    seed:             int | None = 42,
    peso_superlotacao: float = 0.0,
    conforto:         int | None = None,
    verbose:          bool = True,
) -> tuple[list[Rota], float]:
    """
    Executa o Clarke-Wright OVRP completo (CW-1 + CW-2 + CW-3) sobre `ctx`.

    Se λ não for fornecido, testa todos os valores de 0.1 a 2.0
    (incremento 0.1) e usa o que gerar menor custo total — conforme
    procedimento CW-1 do artigo (Tabela 1).

    `seed` fixa o gerador aleatório (two-phase + post-improvement) para
    que a execução seja reprodutível — essencial para reportar resultados
    em um artigo. Passe seed=None para variar a cada execução.

    A(s) restrição(ões) de capacidade/tempo vêm da chave em `ctx.restricoes`;
    a de tempo só tem efeito se `ctx.limite_tempo` for finito.

    Retorna:
        (rotas, lambda_usado)
    """
    if seed is not None:
        random.seed(seed)

    if conforto is None:
        conforto = ctx.modelo.capacidade_conforto or ctx.capacidade

    paradas_ativas = set(ctx.carga_parada.keys())

    if not paradas_ativas:
        if verbose:
            print("[clarke_wright] Nenhuma parada com demanda neste período.")
        return [], 0.0

    if verbose:
        print(f"\n[CW-OVRP] {len(paradas_ativas)} paradas | sentido: {ctx.sentido} | "
              f"depósito: {ctx.deposito} | cap: {ctx.capacidade} | "
              f"limite: {_limite_texto(ctx.limite_tempo)} | "
              f"restrições: {ctx.restricoes.chave} | modelo: {ctx.modelo.nome}")

    # ── CW-1: testa múltiplos λ e guarda o melhor ────────────────────────────
    lambdas = [lam] if lam is not None else [
        round(LAMBDA_MIN + i * LAMBDA_PASSO, 1)
        for i in range(round((LAMBDA_MAX - LAMBDA_MIN) / LAMBDA_PASSO) + 1)
    ]

    melhor_rotas = None
    melhor_custo = INF
    melhor_lam   = lambdas[0]

    for l in lambdas:
        savings = calcular_savings_ovrp(sorted(paradas_ativas), ctx, l)

        if usar_two_phase:
            rotas_l = two_phase_selection(
                savings, paradas_ativas, ctx,
                iteracoes=iteracoes,
                peso_superlotacao=peso_superlotacao, conforto=conforto,
            )
        else:
            rotas_l = _fundir(savings, paradas_ativas, ctx)

        custo_l = _obj_total(rotas_l, peso_superlotacao, conforto)
        if verbose:
            maior_tempo = max((r.tempo_min for r in rotas_l), default=0)
            print(f"  lam={l:.1f} -> {len(rotas_l)} veiculos | "
                  f"R${custo_l:.2f} | {sum(r.dist_km for r in rotas_l):.1f} km | "
                  f"maior rota {maior_tempo} min")

        if custo_l < melhor_custo:
            melhor_custo = custo_l
            melhor_rotas = rotas_l
            melhor_lam   = l

    if verbose:
        print(f"\n  [OK] Melhor lam = {melhor_lam} | custo R${melhor_custo:.2f}")

    # ── CW-3: post-improvement sobre a melhor solução ───────────────────────
    if usar_postimprove and melhor_rotas:
        if verbose:
            print("  Aplicando post-improvement (2-opt / shift / swap)...")
        melhor_rotas = post_improvement(
            melhor_rotas, ctx,
            max_iter_sem_melhora=iter_postimprov,
            peso_superlotacao=peso_superlotacao, conforto=conforto,
        )
        custo_pos = _obj_total(melhor_rotas, peso_superlotacao, conforto)
        if verbose:
            reducao = round((melhor_custo - custo_pos) / melhor_custo * 100, 2)
            print(f"  [OK] Apos post-improvement: R${custo_pos:.2f} "
                  f"(-{reducao}%)")

    return melhor_rotas or [], melhor_lam


# ── Análise de Pareto: custo × superlotação ──────────────────────────────────

def analise_pareto(
    ctx:         Contexto,
    capacidades: list[int] | None = None,
    verbose:     bool = True,
) -> list[dict]:
    """
    Varre vários limites de lotação por ônibus (capacidade efetiva) e, para
    cada um, resolve o roteamento. Mostra o trade-off entre custo (combustível)
    e superlotação — é a curva de Pareto que responde "quanto custa cada nível
    de conforto".

    Reduzir a capacidade efetiva força o algoritmo a usar MAIS ônibus, aliviando
    a lotação. Cada linha da tabela é uma política possível para o gestor.

    A chave de restrições de `ctx` é mantida em todos os pontos da varredura.

    Retorna uma lista de dicts (uma por capacidade testada).
    """
    if capacidades is None:
        # do conforto (todos sentados) até a lotação máxima do veículo
        cmin = ctx.modelo.capacidade_conforto or ctx.modelo.capacidade
        cmax = ctx.modelo.capacidade
        capacidades = sorted(set(range(cmin, cmax + 1, 4)) | {cmin, cmax})

    linhas = []
    for cap in capacidades:
        ctx_cap = replace(ctx, capacidade=cap)
        # Varredura usa CW-1 (rápido): basta para comparar níveis de conforto.
        rotas, _ = clarke_wright_ovrp(
            ctx_cap, usar_two_phase=False, usar_postimprove=False, verbose=False,
        )
        if not rotas:
            continue
        maior     = max(r.carga for r in rotas)
        custo     = round(sum(r.custo_brl for r in rotas), 2)
        dist      = round(sum(r.dist_km for r in rotas), 1)
        tempo     = max(r.tempo_min for r in rotas)
        atend     = avaliar_atendimento(rotas, ctx_cap)
        linhas.append({
            "cap_efetiva":  cap,
            "veiculos":     len(rotas),
            "dist_km":      dist,
            "custo_brl":    custo,
            "maior_onibus": maior,
            "maior_tempo":  tempo,
            "ocup_maior_%": round(maior / ctx.modelo.capacidade * 100),
            "pax":          atend.atendida,
            "pax_%":        round(atend.pct_atendida),
        })

    if verbose:
        print(f"\n{'=' * 78}")
        print("ANÁLISE DE PARETO  —  custo (combustível) × superlotação")
        print(f"Depósito: {ctx.deposito} | modelo: {ctx.modelo.nome} | "
              f"máx: {ctx.modelo.capacidade} | conforto: {ctx.modelo.capacidade_conforto} | "
              f"restrições: {ctx.restricoes.chave}")
        print(f"{'=' * 78}")
        print(f"  {'cap/ônibus':>11} | {'ônibus':>6} | {'km':>7} | "
              f"{'R$ comb.':>9} | {'maior':>6} | {'tempo':>6} | {'pax':>5} | "
              f"{'% lot.':>6}")
        print(f"  {'-'*11} | {'-'*6} | {'-'*7} | {'-'*9} | {'-'*6} | "
              f"{'-'*6} | {'-'*5} | {'-'*6}")
        for L in linhas:
            print(f"  {L['cap_efetiva']:>11} | {L['veiculos']:>6} | "
                  f"{L['dist_km']:>7.1f} | {L['custo_brl']:>9.2f} | "
                  f"{L['maior_onibus']:>6} | {L['maior_tempo']:>6} | "
                  f"{L['pax']:>5} | {L['ocup_maior_%']:>5}%")
        print()

    return linhas


# ── Avaliação do atendimento (simulação TOP, fora das decisões) ──────────────

@dataclass(frozen=True)
class Atendimento:
    """Quanto da demanda as rotas realmente entregam.

    `alocada` é a projeção do CVRP (soma das demandas das paradas visitadas,
    o que o algoritmo otimiza); `atendida` é o que a simulação de
    embarque/desembarque confirma. Só a segunda é "passageiros
    transportados".
    """

    demanda_total:   int
    alocada:         int
    atendida:        int
    nao_atendida:    int
    pico:            int
    pares_atendidos:     tuple[tuple[int, int, int], ...] = ()
    pares_nao_atendidos: tuple[tuple[int, int, int], ...] = ()

    @property
    def pct_alocada(self) -> float:
        return self.alocada / self.demanda_total * 100 if self.demanda_total else 0.0

    @property
    def pct_atendida(self) -> float:
        return self.atendida / self.demanda_total * 100 if self.demanda_total else 0.0


def _instancia_do_contexto(ctx: Contexto) -> InstanceData:
    """`InstanceData` mínimo para a simulação (ela só lê tempo e demanda)."""
    return InstanceData(
        nodes=[], distance=ctx.distancia, time=ctx.tempo, demand=ctx.demanda
    )


def avaliar_atendimento(rotas: list[Rota], ctx: Contexto) -> Atendimento:
    """Mede o atendimento real de cada rota com a simulação do TOP UNIVASF.

    A rota do CW é aberta e começa no depósito, então a sequência simulada é
    `[depósito] + paradas` — o trecho que sai do depósito também ocupa
    assento. A demanda é cobrada em ordem: um par embarcado numa rota sai de
    `restante` e não é contado de novo na próxima.

    NÃO é critério de decisão: preenche `Rota.pax/pico/pares` depois que a
    solução está fechada.
    """
    restante = np.array(ctx.demanda, copy=True)
    instancia = _instancia_do_contexto(ctx)
    pares_totais: list[tuple[int, int, int]] = []

    for rota in rotas:
        sequencia = (ctx.deposito, *rota.paradas)
        resultado = simulate_stops(instancia, sequencia, ctx.capacidade, restante)
        rota.pax = resultado.passengers
        rota.pico = resultado.peak_load
        rota.pares = tuple(resultado.pairs)
        for origem, destino, quantidade in resultado.pairs:
            restante[origem, destino] -= quantidade
        pares_totais.extend(resultado.pairs)

    total = int(ctx.demanda.sum())
    atendida = sum(r.pax for r in rotas)
    nao_atendidos = tuple(sorted(
        (
            (origem, destino, int(quantidade))
            for (origem, destino), quantidade in np.ndenumerate(restante)
            if quantidade > 0
        ),
        key=lambda par: (-par[2], par[0], par[1]),
    ))
    return Atendimento(
        demanda_total=total,
        alocada=sum(r.carga for r in rotas),
        atendida=atendida,
        nao_atendida=total - atendida,
        pico=max((r.pico for r in rotas), default=0),
        pares_atendidos=tuple(pares_totais),
        pares_nao_atendidos=nao_atendidos,
    )


# ── Relatório ─────────────────────────────────────────────────────────────────

def _limite_texto(limite: float) -> str:
    return "sem limite" if limite == INF else f"{limite:g} min"


def _situacao(rota: Rota, ctx: Contexto, conforto: int) -> str:
    """Marcadores do relatório. Referem-se à CARGA ALOCADA (a do algoritmo)."""
    marcas = []
    if rota.carga > ctx.capacidade:
        marcas.append("[ALOCADA ACIMA DA CAP.]")
    elif rota.carga >= ctx.capacidade:
        marcas.append("[ALOCADA CHEIA]")
    elif rota.carga > conforto:
        marcas.append("[aloc. desconforto]")
    if rota.tempo_min > ctx.limite_tempo:
        marcas.append("[ACIMA DO TEMPO]")
    return " ".join(marcas)


def _pares_texto(pares: tuple, limite: int = 10) -> str:
    """Lista curta dos pares atendidos: "12->2=1, 22->2=1"."""
    itens = [f"{o}->{d}={q}" for o, d, q in pares[:limite]]
    if len(pares) > limite:
        itens.append(f"(+{len(pares) - limite})")
    return ", ".join(itens)


def imprimir_solucao(
    rotas:    list[Rota],
    ctx:      Contexto,
    rotulo:   str,
    lam:      float,
    conforto: int | None = None,
    atend:    Atendimento | None = None,
) -> None:
    if conforto is None:
        conforto = ctx.modelo.capacidade_conforto or ctx.capacidade
    if atend is None:
        atend = avaliar_atendimento(rotas, ctx)

    custo_total = _custo_total(rotas)
    dist_total  = sum(r.dist_km for r in rotas)
    alocada     = sum(r.carga for r in rotas)
    atendida    = sum(r.pax for r in rotas)
    ocup_aloc   = (alocada / (len(rotas) * ctx.capacidade) * 100) if rotas else 0.0
    ocup_real   = (atend.pico / ctx.capacidade * 100) if ctx.capacidade else 0.0
    custo_pax   = custo_total / atendida if atendida else 0.0
    n_cheias    = sum(1 for r in rotas if r.carga >= ctx.capacidade)
    desconforto = sum(_excesso(r.carga, conforto) for r in rotas)
    maior_tempo = max((r.tempo_min for r in rotas), default=0)
    fora_tempo  = sum(1 for r in rotas if r.tempo_min > ctx.limite_tempo)

    print(f"\n{'=' * 65}")
    print(f"SOLUCAO CLARKE-WRIGHT OVRP  |  {rotulo}  |  lam = {lam}")
    print(f"Depósito  : {ctx.deposito}")
    print(f"Modelo    : {ctx.modelo.nome} | R${ctx.modelo.custo_por_km:.4f}/km")
    print(f"Restrições: {ctx.restricoes.chave} "
          f"(capacidade={'sim' if ctx.restricoes.capacidade else 'não'}, "
          f"tempo={'sim' if ctx.restricoes.tempo else 'não'})")
    print(f"Capacidade: {ctx.capacidade} máx / {conforto} conforto")
    print(f"Tempo     : limite {_limite_texto(ctx.limite_tempo)} | "
          f"maior rota {maior_tempo} min")
    print(f"{'=' * 65}")
    print(f"  Veículos utilizados  : {len(rotas)}")
    print(f"  Demanda total        : {atend.demanda_total} pax")
    print(f"  Demanda alocada      : {alocada} "
          f"({atend.pct_alocada:.0f}%)  [projeção do CVRP]")
    print(f"  Passageiros atendidos: {atendida} "
          f"({atend.pct_atendida:.0f}%)  [simulação]")
    print(f"  Demanda não atendida : {atend.nao_atendida} pax")
    print(f"  Distância total      : {dist_total:.1f} km")
    print(f"  Custo total (comb.)  : R${custo_total:.2f}")
    print(f"  Custo médio/veículo  : R${custo_total / max(1, len(rotas)):.2f}")
    print(f"  Custo por pax atend. : R${custo_pax:.2f}")
    print(f"  Ocupação alocada     : {ocup_aloc:.0f}% da capacidade")
    print(f"  Ocupação real (pico) : {atend.pico}/{ctx.capacidade} ({ocup_real:.0f}%)")
    print(f"  Rotas com aloc. cheia: {n_cheias}/{len(rotas)} (carga alocada = capacidade)")
    print(f"  Alocados em desconforto: {desconforto} (acima de {conforto}/ônibus)")
    print(f"  Rotas acima do tempo : {fora_tempo}/{len(rotas)}")
    print()

    for i, rota in enumerate(sorted(rotas, key=lambda r: -r.carga), 1):
        pct    = round(rota.carga / ctx.capacidade * 100)
        cheio  = min(pct, 100)
        barra  = "#" * (cheio // 5) + "." * (20 - cheio // 5)
        status = _situacao(rota, ctx, conforto)

        print(f"  Ônibus {i:02d}  [{barra}] {pct:3d}%  "
              f"aloc {rota.carga:3d}/{ctx.capacidade} | "
              f"pax {rota.pax:3d} | pico {rota.pico:3d}  "
              f"{rota.tempo_min}/{_limite_texto(ctx.limite_tempo)}  "
              f"{rota.dist_km:.1f} km  R${rota.custo_brl:.2f}  {status}")

        rota_str = f"    {ctx.deposito} -> " + " -> ".join(
            str(p) for p in rota.paradas
        )
        if len(rota_str) > 130:
            rota_str = rota_str[:127] + "..."
        print(rota_str)
        if rota.pares:
            print(f"    atende: {_pares_texto(rota.pares)}")
        else:
            print("    atende: nenhum par origem->destino cabe na rota")
        print()


def salvar_resultado(
    rotas:  list[Rota],
    ctx:    Contexto,
    rotulo: str,
    lam:    float,
    atend:  Atendimento | None = None,
) -> None:
    if atend is None:
        atend = avaliar_atendimento(rotas, ctx)

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    resultado = {
        "algoritmo":     "Clarke-Wright OVRP (Pichpibul & Kawtummachai, 2013)",
        "rotulo":        rotulo,
        "deposito":      ctx.deposito,
        "sentido":       ctx.sentido,
        "lambda":        lam,
        "restricoes":    ctx.restricoes.chave,
        "capacidade":    ctx.capacidade,
        "limite_tempo":  None if ctx.limite_tempo == INF else ctx.limite_tempo,
        "modelo_onibus": {
            "nome":         ctx.modelo.nome,
            "capacidade":   ctx.modelo.capacidade,
            "consumo_km_l": ctx.modelo.consumo_km_l,
            "custo_litro":  ctx.modelo.custo_litro,
            "custo_por_km": ctx.modelo.custo_por_km,
        },
        "gerado_em":       datetime.now().isoformat(),
        "num_veiculos":    len(rotas),
        "dist_total_km":   round(sum(r.dist_km for r in rotas), 2),
        "custo_total_brl": round(sum(r.custo_brl for r in rotas), 2),
        # Projeção do CVRP (uma demanda por nó) × atendimento medido pela
        # simulação de embarque/desembarque. Os dois números são diferentes
        # por construção; ver o docstring do módulo.
        "demanda_total":        atend.demanda_total,
        "demanda_alocada":      atend.alocada,
        "demanda_alocada_pct":  round(atend.pct_alocada, 1),
        "pax_atendidos":        atend.atendida,
        "pax_atendidos_pct":    round(atend.pct_atendida, 1),
        "demanda_nao_atendida": atend.nao_atendida,
        "pico_max":             atend.pico,
        "pares_atendidos": [
            {"origem": o, "destino": d, "pax": q}
            for o, d, q in atend.pares_atendidos
        ],
        "rotas": [
            {
                "id":           i + 1,
                "paradas":      r.paradas,
                "carga":        r.carga,
                "pax_atendido": r.pax,
                "pico":         r.pico,
                "pares": [
                    {"origem": o, "destino": d, "pax": q} for o, d, q in r.pares
                ],
                "dist_km":   r.dist_km,
                "tempo_min": r.tempo_min,
                "custo_brl": r.custo_brl,
            }
            for i, r in enumerate(rotas)
        ],
    }

    nome_arquivo = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in rotulo.lower()
    )
    arquivo = output_dir / f"cw_ovrp_{nome_arquivo}.json"
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"[clarke_wright] Resultado salvo em: {arquivo}")


def imprimir_frota() -> None:
    """Lista o fleet.csv (o que o algoritmo usa como referência)."""
    buses = load_fleet(ROOT / "fleet.csv")
    print(f"\n{'=' * 46}")
    print("FROTA  (fleet.csv)")
    print(f"{'=' * 46}")
    print(f"  {'id':>3} | {'lugares':>7} | {'tanque (L)':>10} | {'km/L':>5}")
    print(f"  {'-'*3} | {'-'*7} | {'-'*10} | {'-'*5}")
    for bus in buses:
        print(f"  {bus.id:>3} | {bus.passenger_capacity:>7} | "
              f"{bus.fuel_capacity:>10g} | {bus.km_autonomy_per_liter:>5g}")
    print()


# ── Entrada: cenário/instância → Contexto ─────────────────────────────────────

def _buscar_cenario(scenario_id: str) -> dict:
    for scenario in load_scenarios(ROOT):
        if str(scenario["scenario_id"]) == str(scenario_id):
            return scenario
    raise SystemExit(
        f"[erro] cenário '{scenario_id}' não encontrado em "
        "scenarios.csv / scenarios_base.csv"
    )


def _frota_do_cenario(cenario: dict | None) -> list[Bus]:
    if not cenario or not cenario.get("fleet_bus_ids"):
        return []
    return load_fleet(ROOT / "fleet.csv", parse_fleet_ids(cenario["fleet_bus_ids"]))


def _deposito_do_cenario(cenario: dict | None) -> int | None:
    if not cenario:
        return None
    origens = parse_node_labels(cenario.get("origin"))
    return origens[0] if origens else None


def _modelo_do_cenario(
    cenario: dict | None, capacidade: int, diesel: float
) -> ModeloOnibus:
    """Modelo de custo: um ônibus da frota do cenário, ou um genérico."""
    buses = _frota_do_cenario(cenario)
    if not buses:
        return ModeloOnibus(
            nome="genérico",
            capacidade=capacidade,
            consumo_km_l=CONSUMO_PADRAO,
            custo_litro=diesel,
        )
    referencia = next(
        (b for b in buses if b.passenger_capacity == capacidade),
        min(buses, key=lambda b: b.passenger_capacity),
    )
    return modelo_de_bus(referencia, diesel)


def contexto_do_cenario(
    cenario: dict | None,
    *,
    instancia: str | None = None,
    periodo: str | None = None,
    deposito: int | None = None,
    capacidade: int | None = None,
    limite_tempo: float | None = None,
    diesel: float | None = None,
    restricoes: str = "ambas",
    sentido: str = "auto",
) -> tuple[InstanceData, Contexto]:
    """Resolve um cenário (instância, depósito, frota, limites) num contexto.

    Cada parâmetro explícito vence o que o cenário define; é o mesmo caminho
    que a CLI percorre, exposto para o `main.py` rodar as duas heurísticas
    com exatamente os mesmos limites.

    Devolve `(data, ctx)`.
    """
    cenario = cenario or {}
    instancia = instancia or cenario.get("instance_id")
    if not instancia:
        raise ValueError("informe a instância (o cenário não define uma)")
    periodo = periodo or cenario.get("period") or PERIODO_PADRAO
    data = load_instance_data(ROOT / "instances" / instancia, period=periodo)

    if deposito is None:
        deposito = _deposito_do_cenario(cenario)
    if deposito is None:
        raise ValueError("informe o depósito (o cenário não define uma origem)")

    buses = _frota_do_cenario(cenario)
    if diesel is None:
        diesel = (
            float(cenario["diesel_price_per_liter"])
            if cenario.get("diesel_price_per_liter")
            else DIESEL_PADRAO
        )
    # Sem capacidade informada, vale a do menor ônibus da frota: assim toda
    # rota que o CW monta cabe em qualquer ônibus do cenário.
    if capacidade is None:
        capacidade = (
            min(b.passenger_capacity for b in buses) if buses else 48
        )
    modelo = _modelo_do_cenario(cenario, capacidade, diesel)

    if limite_tempo is None and cenario.get("max_time_limit"):
        limite_tempo = int(cenario["max_time_limit"])

    ctx = montar_contexto(
        data, deposito,
        capacidade=capacidade, limite_tempo=limite_tempo, modelo=modelo,
        restricoes=restricoes, sentido=sentido,
    )
    return data, ctx


def resolver_cenario(
    cenario: dict,
    *,
    instancia: str | None = None,
    periodo: str | None = None,
    deposito: int | None = None,
    capacidade: int | None = None,
    limite_tempo: float | None = None,
    diesel: float | None = None,
    restricoes: str = "ambas",
    sentido: str = "auto",
    lam: float | None = None,
    usar_two_phase: bool = True,
    usar_postimprove: bool = True,
    iteracoes: int = ITER_TWO_PHASE,
    iter_postimprov: int = ITER_POSTIMPROVE,
    seed: int = 42,
    conforto: int | None = None,
    peso_superlotacao: float = 0.0,
    verbose: bool = False,
) -> tuple[InstanceData, list[Rota], Contexto, Atendimento, float]:
    """Roda o CW num cenário e devolve a solução já avaliada.

    Devolve `(data, rotas, ctx, atendimento, lambda_usado)` — é o que o
    `main.py` consome para montar a linha do CW na tabela comparativa.
    """
    data, ctx = contexto_do_cenario(
        cenario,
        instancia=instancia, periodo=periodo, deposito=deposito,
        capacidade=capacidade, limite_tempo=limite_tempo, diesel=diesel,
        restricoes=restricoes, sentido=sentido,
    )
    rotas, lam_usado = clarke_wright_ovrp(
        ctx,
        lam=lam,
        usar_two_phase=usar_two_phase,
        usar_postimprove=usar_postimprove,
        iteracoes=iteracoes,
        iter_postimprov=iter_postimprov,
        seed=seed,
        conforto=conforto,
        peso_superlotacao=peso_superlotacao,
        verbose=verbose,
    )
    atend = avaliar_atendimento(rotas, ctx)
    return data, rotas, ctx, atend, lam_usado


def planos_e_resumo(
    rotas:    list[Rota],
    ctx:      Contexto,
    atend:    Atendimento,
    buses:    list[Bus] | None = None,
) -> tuple[list[BusPlan], FleetSummary]:
    """Converte a solução do CW no modelo de resultado que o `reporting` lê.

    O CW não tem par travado nem "rounds": a rota nasce no depósito, então
    `origin` é o depósito e `destination` é a última parada. Os ids dos ônibus
    vêm da frota do cenário em ordem; se o CW precisar de mais veículos que a
    frota, os excedentes recebem ids sequenciais depois do maior id.
    """
    ids = [bus.id for bus in (buses or [])]
    proximo = (max(ids) + 1) if ids else 1
    planos: list[BusPlan] = []

    for indice, rota in enumerate(rotas):
        if indice < len(ids):
            bus_id = ids[indice]
        else:
            bus_id = proximo
            proximo += 1
        planos.append(BusPlan(
            bus_id=bus_id,
            origin=ctx.deposito,
            destination=rota.paradas[-1] if rota.paradas else ctx.deposito,
            stops=(ctx.deposito, *rota.paradas),
            served_passengers=rota.pax,
            travel_time_minutes=rota.tempo_min,
            peak_load=rota.pico,
            score=rota.pax / rota.tempo_min if rota.tempo_min else 0.0,
            served_pairs=tuple(rota.pares),
        ))

    resumo = FleetSummary(
        rounds=0,
        wins_per_bus=(),
        unserved_passengers=atend.nao_atendida,
        unserved_pairs=atend.pares_nao_atendidos,
    )
    return planos, resumo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clarke-Wright OVRP — Transporte UNIVASF"
    )
    parser.add_argument("--cenario", default=None,
                        help="scenario_id de scenarios.csv/scenarios_base.csv")
    parser.add_argument("--instancia", default=None,
                        help="instance_id (ex: p1_2_a); padrão: a do cenário")
    parser.add_argument("--periodo", default=None,
                        help=f"período de demanda (padrão: {PERIODO_PADRAO})")
    parser.add_argument("--deposito", type=int, default=None,
                        help="nó de origem da frota (padrão: 1º origin do cenário)")
    parser.add_argument("--capacidade", type=int, default=None,
                        help="capacidade efetiva por ônibus (padrão: a menor da frota)")
    parser.add_argument("--limite-tempo", type=int, default=None,
                        help="tempo máximo da rota em minutos (padrão: do cenário)")
    parser.add_argument("--restricao", default="ambas", choices=list(RESTRICOES),
                        help="quais restrições a rota precisa respeitar")
    parser.add_argument("--diesel", type=float, default=None,
                        help=f"R$/litro (padrão: do cenário ou {DIESEL_PADRAO})")
    parser.add_argument("--lambda-val", type=float, default=None,
                        help="valor fixo de λ (padrão: testa 0.1–2.0)")
    parser.add_argument("--sem-two-phase",  action="store_true",
                        help="desativa two-phase selection (CW-1 apenas)")
    parser.add_argument("--sem-postimprove", action="store_true",
                        help="desativa post-improvement (CW-1+CW-2 apenas)")
    parser.add_argument("--iteracoes", type=int, default=ITER_TWO_PHASE,
                        help=f"iterações da two-phase (padrão: {ITER_TWO_PHASE})")
    parser.add_argument("--iter-postimprov", type=int, default=ITER_POSTIMPROVE,
                        help=f"iterações sem melhora do CW-3 (padrão: {ITER_POSTIMPROVE})")
    parser.add_argument("--sentido", default="auto",
                        choices=["auto", "ida", "volta"],
                        help="ida=carga por embarque; volta=carga por desembarque")
    parser.add_argument("--conforto", type=int, default=None,
                        help="lotação confortável por ônibus (padrão: do modelo)")
    parser.add_argument("--peso-superlotacao", type=float, default=0.0,
                        help="penalidade R$ por passageiro acima do conforto (0 = custo puro)")
    parser.add_argument("--seed", type=int, default=42,
                        help="semente do gerador aleatório (reprodutibilidade)")
    parser.add_argument("--pareto", action="store_true",
                        help="varre capacidades e mostra o trade-off custo × superlotação")
    parser.add_argument("--salvar", action="store_true",
                        help="salva resultado em algorithms/output/")
    parser.add_argument("--frota", action="store_true",
                        help="exibe a frota do fleet.csv")
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
        print(f"Frota do cenário: {len(buses)} ônibus "
              f"[{', '.join(str(b.id) for b in buses)}]")

    if args.pareto:
        analise_pareto(ctx)
        return

    rotas, lam_usado = clarke_wright_ovrp(
        ctx,
        lam=args.lambda_val,
        usar_two_phase=not args.sem_two_phase,
        usar_postimprove=not args.sem_postimprove,
        iteracoes=args.iteracoes,
        iter_postimprov=args.iter_postimprov,
        seed=args.seed,
        conforto=args.conforto,
        peso_superlotacao=args.peso_superlotacao,
        verbose=True,
    )

    atend = avaliar_atendimento(rotas, ctx)
    imprimir_solucao(
        rotas, ctx, rotulo, lam_usado, conforto=args.conforto, atend=atend
    )

    if args.salvar:
        salvar_resultado(rotas, ctx, rotulo, lam_usado, atend=atend)


if __name__ == "__main__":
    main()
