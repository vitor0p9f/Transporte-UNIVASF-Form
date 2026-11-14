"""Sentido da viagem, carga por parada e montagem do contexto."""

import numpy as np

from utils.instances import InstanceData

from .constants import CAPACIDADE_PADRAO, CONSUMO_PADRAO, DIESEL_PADRAO, INF
from .model import Contexto, ModeloOnibus, Restricoes


def detectar_sentido(demanda: np.ndarray, deposito: int) -> str:
    """Detecta se a viagem é de "ida" ou de "volta" a partir do depósito.

    - "volta": o depósito é o campus de onde as pessoas SAEM (embarcam ali).
      A carga de cada parada é o nº de DESEMBARQUES (alighting), pois é quanta
      gente desce naquele ponto.
    - "ida": o depósito é a origem e as pessoas embarcam nas paradas rumo ao
      campus. A carga é o nº de EMBARQUES (boarding).
    """
    embarques = int(demanda[deposito].sum())  # quem sai do depósito
    desembarques = int(demanda[:, deposito].sum())  # quem chega no depósito
    return "volta" if embarques > desembarques else "ida"


def construir_carga_parada(
    demanda: np.ndarray,
    deposito: int,
    sentido: str = "auto",
) -> tuple[dict[int, int], str]:
    """Calcula a carga (passageiros que o ônibus transporta) de cada parada.

    Na ida a carga vem dos embarques (linha da matriz); na volta, dos
    desembarques (coluna) — porque na volta quase todos embarcam no campus
    (depósito) e a demanda real de cada parada é quanta gente DESCE ali.
    Retorna `(carga_parada, sentido_usado)`.
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
    data: InstanceData,
    deposito: int,
    *,
    capacidade: int | None = None,
    limite_tempo: float | None = None,
    modelo: ModeloOnibus | None = None,
    restricoes: Restricoes | str = "ambas",
    sentido: str = "auto",
    max_rotas: int | None = None,
) -> Contexto:
    """Resolve os limites, a chave de restrições e a carga por parada.

    `capacidade` e `limite_tempo` são independentes do modelo e do cenário:
    quando omitidos, vêm dele(s). Sem limite de tempo a restrição "tempo" não
    tem efeito; sem capacidade informada, vale a do modelo. `max_rotas` é o
    teto de veículos do cenário (None = sem limite).
    """
    if isinstance(restricoes, str):
        restricoes = Restricoes.da_chave(restricoes)

    if modelo is None:
        capacidade_modelo = (
            capacidade if capacidade is not None else CAPACIDADE_PADRAO
        )
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
        max_rotas=max_rotas,
    )
