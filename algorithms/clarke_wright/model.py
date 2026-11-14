"""Data structures used by the Clarke-Wright OVRP heuristic."""

from dataclasses import dataclass, field

import numpy as np

from entities.bus import Bus

from .constants import RESTRICTIONS

#: Um par origem→destino atendido e sua quantidade.
Pair = tuple[int, int, int]
#: Lista imutável de pares atendidos.
Pairs = tuple[Pair, ...]


@dataclass(frozen=True)
class Restrictions:
    """Quais restrições de rota estão ativas nesta execução.

    Construa pela chave (`Restricoes.da_chave("tempo")`) para não errar a
    combinação; a CLI e `montar_contexto` só aceitam as chaves de `RESTRICOES`.
    """

    capacity: bool = True
    time: bool = True

    @classmethod
    def from_key(cls, key: str) -> "Restrictions":
        try:
            capacity_on, time_on = RESTRICTIONS[key]
        except KeyError:
            validas = ", ".join(RESTRICTIONS)
            raise ValueError(
                f"restrição '{key}' desconhecida (use: {validas})"
            ) from None
        return cls(capacity=capacity_on, time=time_on)

    @property
    def key(self) -> str:
        """A chave ("capacidade"/"tempo"/"ambas"/"nenhuma") desta combinação."""
        for key, (capacity, time) in RESTRICTIONS.items():
            if (capacity, time) == (self.capacity, self.time):
                return key
        return "custom"


@dataclass(frozen=True)
class BusModel:
    """Modelo de custo do veículo: litros por km e preço do litro.

    Substitui o antigo `utils.fleet.ModeloOnibus`; os dados vêm de uma linha
    do `fleet.csv` (capacidade e autonomia) e do cenário (preço do diesel).
    """

    name: str
    capacity: int
    km_per_liter: float
    diesel_price: float

    @property
    def cost_per_km(self) -> float:
        return self.diesel_price / self.km_per_liter

    def route_cost(self, distance_km: float) -> float:
        return distance_km * self.cost_per_km


def bus_model(bus: Bus, diesel_price: float) -> BusModel:
    """Converte uma linha do `fleet.csv` no modelo de custo do algoritmo."""
    if bus.km_autonomy_per_liter <= 0:
        raise ValueError(f"bus {bus.id}: km_autonomy_per_liter deve ser > 0")
    return BusModel(
        name=f"ônibus {bus.id}",
        capacity=bus.passenger_capacity,
        km_per_liter=bus.km_autonomy_per_liter,
        diesel_price=diesel_price,
    )


@dataclass(frozen=True)
class Context:
    """Tudo o que uma rota precisa para ser medida e validada.

    Carrega as duas matrizes (distância e tempo), o depósito, os limites e a
    chave de restrições. É ele que as funções internas recebem, em vez dos
    seis ou sete parâmetros soltos de antes.

    `carga_parada` é a projeção do CVRP (demanda por nó, o que as decisões
    usam); `demanda` é a matriz OD crua, lida só pela avaliação de
    atendimento por simulação.
    """

    distance: np.ndarray
    time: np.ndarray
    depot: int
    capacity: int
    max_time: float
    bus_model: BusModel
    stop_loads: dict[int, int]
    demanda: np.ndarray
    restrictions: Restrictions = field(default_factory=Restrictions)
    sense: str = "ida"
    #: Teto de veículos do cenário (None = sem limite). O CW não conhece a
    #: frota: ele abre uma rota por parada e funde enquanto as restrições
    #: deixam. Quando a solução passa do teto, as rotas excedentes não teriam
    #: ônibus para operar e são descartadas por `limitar_frota`.
    max_routes: int | None = None

    def fits(self, load: int, minutos: float) -> bool:
        """Ponto único da chave: só valida a(s) restrição(ões) ativa(s)."""
        if self.restrictions.capacity and load > self.capacity:
            return False
        return not self.restrictions.time or minutos <= self.max_time


@dataclass
class Saving:
    """Par (i, j) com o valor de economia calculado."""

    i: int
    j: int
    value: float

    def __lt__(self, other: "Saving") -> bool:
        return self.value > other.value  # ordenação decrescente


@dataclass
class Route:
    """Rota aberta: depot → p1 → p2 → ... → pn (sem retorno ao depósito)."""

    stops: list[int] = field(default_factory=list)
    load: int = 0  # demanda alocada (projeção do CVRP)
    distance_km: float = 0.0  # distância total da rota (km)
    time_minutes: int = 0  # tempo total da rota (min)
    cost_brl: float = 0.0  # custo de combustível (R$)
    passengers: int = 0  # pax atendidos (simulação, pós-solução)
    peak_load: int = 0  # ocupação máxima simultânea (simulação)
    pairs: Pairs = ()  # (origem, destino, qtd) embarcados

    def first(self) -> int:
        return self.stops[0]

    def last(self) -> int:
        return self.stops[-1]


@dataclass(frozen=True)
class Attendance:
    """Quanto da demanda as rotas realmente entregam.

    `alocada` é a projeção do CVRP (soma das demandas das paradas visitadas,
    o que o algoritmo otimiza); `atendida` é o que a simulação de
    embarque/desembarque confirma. Só a segunda é "passageiros
    transportados".
    """

    total_demand: int
    allocated: int
    served: int
    unserved: int
    peak_load: int
    served_pairs: Pairs = ()
    unserved_pairs: Pairs = ()

    @property
    def allocated_pct(self) -> float:
        return self.allocated / self.total_demand * 100 if self.total_demand else 0.0

    @property
    def served_pct(self) -> float:
        return self.served / self.total_demand * 100 if self.total_demand else 0.0
