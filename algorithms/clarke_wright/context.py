"""Sentido da viagem, carga por parada e montagem do contexto."""

import numpy as np

from utils.instances import InstanceData

from .constants import DEFAULT_CAPACITY, DEFAULT_DIESEL_PRICE, DEFAULT_KM_PER_LITER, INF
from .model import BusModel, Context, Restrictions


def detect_sense(demanda: np.ndarray, depot: int) -> str:
    """Detecta se a viagem é de "ida" ou de "volta" a partir do depósito.

    - "volta": o depósito é o campus de onde as pessoas SAEM (embarcam ali).
      A carga de cada parada é o nº de DESEMBARQUES (alighting), pois é quanta
      gente desce naquele ponto.
    - "ida": o depósito é a origem e as pessoas embarcam nas paradas rumo ao
      campus. A carga é o nº de EMBARQUES (boarding).
    """
    boardings = int(demanda[depot].sum())  # quem sai do depósito
    alightings = int(demanda[:, depot].sum())  # quem chega no depósito
    return "volta" if boardings > alightings else "ida"


def build_stop_loads(
    demanda: np.ndarray,
    depot: int,
    sense: str = "auto",
) -> tuple[dict[int, int], str]:
    """Calcula a carga (passageiros que o ônibus transporta) de cada parada.

    Na ida a carga vem dos embarques (linha da matriz); na volta, dos
    desembarques (coluna) — porque na volta quase todos embarcam no campus
    (depósito) e a demanda real de cada parada é quanta gente DESCE ali.
    Retorna `(carga_parada, sentido_usado)`.
    """
    if sense not in ("auto", "ida", "volta"):
        raise ValueError(f"sentido '{sense}' desconhecido (use: auto, ida, volta)")
    if sense == "auto":
        sense = detect_sense(demanda, depot)

    per_node = demanda.sum(axis=0) if sense == "volta" else demanda.sum(axis=1)
    stop_loads = {
        no: int(per_node[no])
        for no in range(1, len(per_node))
        if no != depot and per_node[no] > 0
    }
    return stop_loads, sense


def build_context(
    data: InstanceData,
    depot: int,
    *,
    capacity: int | None = None,
    max_time: float | None = None,
    bus_model: BusModel | None = None,
    restrictions: Restrictions | str = "ambas",
    sense: str = "auto",
    max_routes: int | None = None,
) -> Context:
    """Resolve os limites, a chave de restrições e a carga por parada.

    `capacidade` e `limite_tempo` são independentes do modelo e do cenário:
    quando omitidos, vêm dele(s). Sem limite de tempo a restrição "tempo" não
    tem efeito; sem capacidade informada, vale a do modelo. `max_rotas` é o
    teto de veículos do cenário (None = sem limite).
    """
    if isinstance(restrictions, str):
        restrictions = Restrictions.from_key(restrictions)

    if bus_model is None:
        model_capacity = (
            capacity if capacity is not None else DEFAULT_CAPACITY
        )
        bus_model = BusModel(
            name="genérico",
            capacity=model_capacity,
            km_per_liter=DEFAULT_KM_PER_LITER,
            diesel_price=DEFAULT_DIESEL_PRICE,
        )
    if capacity is None:
        capacity = bus_model.capacity
    if max_time is None:
        max_time = INF

    stop_loads, used_sense = build_stop_loads(
        data.demand, depot, sense
    )
    return Context(
        # float evita surpresa se a instância trouxer a distância como int
        distance=data.distance.astype(float, copy=False),
        time=data.time,
        depot=depot,
        capacity=capacity,
        max_time=max_time,
        bus_model=bus_model,
        stop_loads=stop_loads,
        demanda=data.demand,
        restrictions=restrictions,
        sense=used_sense,
        max_routes=max_routes,
    )
