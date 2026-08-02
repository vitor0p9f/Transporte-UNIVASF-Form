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
    # Coordenadas aproximadas (lat, lon) — usadas apenas se stops/*.json
    # não estiverem disponíveis.  Nomes exatos conforme database.sql.
    "UNIVASF Campus Juazeiro":                      (-9.4167, -40.5011),
    "UNIVASF Campus Petrolina":                     (-9.3925, -40.5072),
    "UNIVASF Campus CCA":                           (-9.3300, -40.5600),
    "UNIVASF Campus CCA – Bloco Antigo":            (-9.3305, -40.5602),
    "UNIVASF Campus Ciências Agrárias – Bloco Antigo": (-9.3295, -40.5598),
    "Bloco de Salas de Aula CCA":                   (-9.3310, -40.5605),
    "Bloco Antigo CCA":                             (-9.3298, -40.5600),
    "Residência Estudantil CCA":                    (-9.3315, -40.5610),
    "Hospital Veterinário CCA":                     (-9.3320, -40.5615),
    "Hospital Veterinário":                         (-9.3318, -40.5612),
    "Terminal de Juazeiro – Camelódromo 2 de Julho": (-9.4281, -40.5028),
    "GBarbosa Juazeiro":                            (-9.4200, -40.4980),
    "GBarbosa Juazeiro – Av. Adolfo Viana":         (-9.4195, -40.4975),
    "GBarbosa Av. Monsenhor Ângelo Sampaio":        (-9.3850, -40.5150),
    "GBarbosa Petrolina":                           (-9.3870, -40.5140),
    "GBarbosa Petrolina – Av. Monsenhor Ângelo Sampaio": (-9.3855, -40.5145),
    "Supermercado Regente":                         (-9.3890, -40.5010),
    "Feira da COHAB Massangano":                    (-9.3750, -40.5300),
    "Sementeira":                                   (-9.3960, -40.5400),
    "Sementeira – Av. da Integração":               (-9.3958, -40.5402),
    "Av. da Integração – Sementeira":               (-9.3957, -40.5403),
    "Petrape":                                      (-9.3980, -40.5450),
    "Petrape – Av. da Integração":                  (-9.3978, -40.5452),
    "Av. da Integração – Petrape":                  (-9.3979, -40.5451),
    "Plante Bem":                                   (-9.3730, -40.5320),
    "Estação Velha Juazeiro":                       (-9.4240, -40.5020),
    "Estação Velha / Cooperativa Brasil":           (-9.4245, -40.5018),
    "Verdão Juazeiro":                              (-9.4180, -40.4960),
    "Abaré":                                        (-9.3848, -40.5267),
    "Academia I9":                                  (-9.3838, -40.5123),
    "Academia I9 – Av. 7 de Setembro":              (-9.3840, -40.5125),
    "Rodoviária de Petrolina":                      (-9.3910, -40.5090),
    "Parque Mundo da Lua":                          (-9.3975, -40.5420),
    "Igreja Filadélfia":                            (-9.3842, -40.5117),
    "Farmácia Popular":                             (-9.3835, -40.5130),
    "Ministério Público Federal":                   (-9.3830, -40.5135),
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
