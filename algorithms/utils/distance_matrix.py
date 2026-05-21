"""
distance_matrix.py
------------------
Constrói a matriz de distâncias e tempos entre paradas a partir dos
arquivos JSON da branch python/VRP (stops/*.json).

Se os JSONs ainda não estiverem disponíveis localmente, usa distância
euclidiana como fallback (para testes).
"""

import json
import math
from pathlib import Path
from typing import Optional

# Caminho padrão dos JSONs de paradas (branch python/VRP)
STOPS_DIR = Path(__file__).parent.parent.parent / "stops"


def carregar_stops_json(stops_dir: Path = STOPS_DIR) -> dict:
    """
    Lê todos os arquivos stops/*.json e retorna um dicionário:
        stops[label] = { "edges": [...], "boardings": [...], "alightings": [...] }
    """
    stops = {}
    if not stops_dir.exists():
        print(f"[distance_matrix] Diretório de stops não encontrado: {stops_dir}")
        return stops

    for arquivo in stops_dir.glob("*.json"):
        with open(arquivo, "r", encoding="utf-8") as f:
            dados = json.load(f)
        label = dados.get("label", arquivo.stem)
        stops[label] = dados

    print(f"[distance_matrix] {len(stops)} stops carregados de '{stops_dir}'")
    return stops


def construir_matriz(stops: dict, metrica: str = "distance") -> tuple[list[str], dict]:
    """
    Constrói a matriz de distâncias (ou tempos) entre paradas.

    Args:
        stops:   saída de carregar_stops_json()
        metrica: "distance" (km) ou "estimated_travel_time" (min)

    Retorna:
        nos    : lista ordenada de nomes de paradas
        matriz : dict[origem][destino] = float
                 (float('inf') se não há aresta direta)
    """
    nos = list(stops.keys())
    matriz = {n: {m: float("inf") for m in nos} for n in nos}

    # Diagonal = 0
    for n in nos:
        matriz[n][n] = 0.0

    # Preenche com os dados das arestas
    for label, dados in stops.items():
        for edge in dados.get("edges", []):
            origem  = edge.get("origin", label)
            destino = edge.get("destination")
            valor   = edge.get(metrica, float("inf"))

            if destino in matriz:
                matriz[origem][destino] = valor
                # Grafo não-dirigido: simetria (se ainda não preenchido ou menor)
                if matriz[destino][origem] == float("inf"):
                    matriz[destino][origem] = valor

    return nos, matriz


def matriz_para_lista(nos: list[str], matriz: dict) -> list[list[float]]:
    """Converte a matriz dict para lista de listas (formato OR-Tools / numpy)."""
    return [[matriz[o][d] for d in nos] for o in nos]


def filtrar_paradas(nos: list[str], matriz: dict, paradas_ativas: set[str]) -> tuple[list[str], dict]:
    """
    Retorna apenas as paradas que aparecem nos dados de demanda,
    útil para reduzir o problema quando nem todas as paradas têm demanda.
    """
    nos_filtrados = [n for n in nos if n in paradas_ativas]
    matriz_filtrada = {
        o: {d: matriz[o][d] for d in nos_filtrados}
        for o in nos_filtrados
    }
    return nos_filtrados, matriz_filtrada


# ── Fallback: distância euclidiana com coordenadas aproximadas ──────────────
# Usado para testes quando os JSONs de stops ainda não estão disponíveis.

COORDS_FALLBACK = {
    # Coordenadas aproximadas (lat, lon) das principais paradas
    "UNIVASF Campus Juazeiro":           (-9.4167, -40.5011),
    "UNIVASF Campus Petrolina":          (-9.3925, -40.5072),
    "UNIVASF Campus Ciências Agrárias":  (-9.3300, -40.5600),
    "Terminal de Juazeiro":              (-9.4281, -40.5028),
    "GBarbosa Juazeiro":                 (-9.4200, -40.4980),
    "Feira da COHAB Massangano":         (-9.3750, -40.5300),
    "Supermercado Regente":              (-9.3890, -40.5010),
    "Sementeira":                        (-9.3960, -40.5400),
    "Petrape":                           (-9.3980, -40.5450),
}


def distancia_euclidiana_km(lat1, lon1, lat2, lon2) -> float:
    """Haversine simplificado para distâncias curtas."""
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def construir_matriz_fallback(paradas: list[str]) -> tuple[list[str], dict]:
    """
    Constrói matriz euclidiana como fallback para testes,
    usando as coordenadas aproximadas de COORDS_FALLBACK.
    """
    nos = [p for p in paradas if p in COORDS_FALLBACK]
    matriz = {n: {m: 0.0 for m in nos} for n in nos}

    for o in nos:
        for d in nos:
            if o != d:
                lat1, lon1 = COORDS_FALLBACK[o]
                lat2, lon2 = COORDS_FALLBACK[d]
                matriz[o][d] = round(distancia_euclidiana_km(lat1, lon1, lat2, lon2), 2)

    print(f"[distance_matrix] Fallback euclidiano: {len(nos)} paradas com coordenadas conhecidas")
    return nos, matriz
