"""Data structures used by the Clarke-Wright OVRP heuristic."""

from dataclasses import dataclass, field

import numpy as np

from entities.bus import Bus

from .constants import RESTRICOES

#: Um par origem→destino atendido e sua quantidade.
Pair = tuple[int, int, int]
#: Lista imutável de pares atendidos.
Pairs = tuple[Pair, ...]


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
    #: Teto de veículos do cenário (None = sem limite). O CW não conhece a
    #: frota: ele abre uma rota por parada e funde enquanto as restrições
    #: deixam. Quando a solução passa do teto, as rotas excedentes não teriam
    #: ônibus para operar e são descartadas por `limitar_frota`.
    max_rotas: int | None = None

    def cabe(self, carga: int, minutos: float) -> bool:
        """Ponto único da chave: só valida a(s) restrição(ões) ativa(s)."""
        if self.restricoes.capacidade and carga > self.capacidade:
            return False
        return not self.restricoes.tempo or minutos <= self.limite_tempo


@dataclass
class Saving:
    """Par (i, j) com o valor de economia calculado."""

    i: int
    j: int
    valor: float

    def __lt__(self, other: "Saving") -> bool:
        return self.valor > other.valor  # ordenação decrescente


@dataclass
class Rota:
    """Rota aberta: depot → p1 → p2 → ... → pn (sem retorno ao depósito)."""

    paradas: list[int] = field(default_factory=list)
    carga: int = 0  # demanda alocada (projeção do CVRP)
    dist_km: float = 0.0  # distância total da rota (km)
    tempo_min: int = 0  # tempo total da rota (min)
    custo_brl: float = 0.0  # custo de combustível (R$)
    pax: int = 0  # pax atendidos (simulação, pós-solução)
    pico: int = 0  # ocupação máxima simultânea (simulação)
    pares: Pairs = ()  # (origem, destino, qtd) embarcados

    def primeira(self) -> int:
        return self.paradas[0]

    def ultima(self) -> int:
        return self.paradas[-1]


@dataclass(frozen=True)
class Atendimento:
    """Quanto da demanda as rotas realmente entregam.

    `alocada` é a projeção do CVRP (soma das demandas das paradas visitadas,
    o que o algoritmo otimiza); `atendida` é o que a simulação de
    embarque/desembarque confirma. Só a segunda é "passageiros
    transportados".
    """

    demanda_total: int
    alocada: int
    atendida: int
    nao_atendida: int
    pico: int
    pares_atendidos: Pairs = ()
    pares_nao_atendidos: Pairs = ()

    @property
    def pct_alocada(self) -> float:
        return self.alocada / self.demanda_total * 100 if self.demanda_total else 0.0

    @property
    def pct_atendida(self) -> float:
        return self.atendida / self.demanda_total * 100 if self.demanda_total else 0.0
