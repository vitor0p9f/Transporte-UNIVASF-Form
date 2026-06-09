"""
gerar_stops_sinteticos.py
-------------------------
Gera uma pasta `stops/` SINTÉTICA (placeholder) para permitir testar o
pipeline completo com os dados reais do viagens.csv ENQUANTO a matriz de
distâncias verdadeira (branch python/VRP) não está disponível.

Para cada parada distinta do CSV é atribuída uma coordenada (lat, lon)
geograficamente plausível na região Petrolina–Juazeiro–CCA, com base em
palavras-chave do nome + jitter determinístico. As distâncias entre paradas
são calculadas por Haversine (linha reta) e escritas no MESMO formato dos
arquivos stops/*.json que a branch python/VRP produz:

    { "label": "<parada>",
      "edges": [ {"origin","destination","distance","estimated_travel_time"}, ... ] }

⚠  Dados FICTÍCIOS — substitua a pasta stops/ pela matriz real quando ela existir.

Uso:
    python gerar_stops_sinteticos.py
    python clarke_wright.py --turno manha_1 --deposito "Bloco de Salas de Aula CCA"
"""

import json
import math
import hashlib
from pathlib import Path

from utils.loader import carregar_tudo

# Raiz do projeto: .../Transporte-UNIVASF-Form/stops
STOPS_DIR = Path(__file__).parent.parent / "stops"

# Âncoras geográficas aproximadas (lat, lon) da região
ANCORAS = {
    "cca":       (-9.3300, -40.5600),  # Campus Ciências Agrárias (zona rural, ~25 km)
    "juazeiro":  (-9.4205, -40.4990),  # Juazeiro-BA (outro lado do rio)
    "petrolina": (-9.3925, -40.5072),  # Campus Petrolina / centro
    "periurb":   (-9.3700, -40.5350),  # cinturão peri-urbano (Sementeira/Petrape/Massangano)
}

VEL_MEDIA_KMH = 28.0   # para estimar tempo de viagem a partir da distância


def _regiao(nome: str) -> str:
    n = nome.lower()
    if any(k in n for k in ["cca", "ciências agrárias", "ciencias agrarias",
                            "veterinário", "veterinario", "bloco de salas",
                            "residência estudantil cca", "residencia estudantil cca"]):
        return "cca"
    if any(k in n for k in ["juazeiro", "monsenhor ângelo", "monsenhor angelo",
                            "terminal", "estação velha", "estacao velha", "verdão",
                            "verdao", "camelódromo", "camelodromo"]):
        return "juazeiro"
    if "petrolina" in n:
        return "petrolina"
    if any(k in n for k in ["sementeira", "petrape", "massangano", "plante bem",
                            "transnordestina", "br 428", "br 407", "banana"]):
        return "periurb"
    return "petrolina"  # urbano padrão


def _jitter(nome: str) -> tuple[float, float]:
    """Deslocamento determinístico (± ~2 km) a partir do hash do nome."""
    h = hashlib.md5(nome.encode("utf-8")).hexdigest()
    dx = (int(h[:8], 16) / 0xFFFFFFFF - 0.5) * 0.04   # ~±2.2 km
    dy = (int(h[8:16], 16) / 0xFFFFFFFF - 0.5) * 0.04
    return dx, dy


def coordenada(nome: str) -> tuple[float, float]:
    lat0, lon0 = ANCORAS[_regiao(nome)]
    dx, dy = _jitter(nome)
    return round(lat0 + dx, 5), round(lon0 + dy, 5)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    R = 6371.0
    lat1, lon1 = a
    lat2, lon2 = b
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    h = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlon / 2) ** 2)
    return R * 2 * math.asin(math.sqrt(h))


def main() -> None:
    _, demand = carregar_tudo()

    paradas = sorted({p for turno in demand.values() for p in turno.keys()})
    coords = {p: coordenada(p) for p in paradas}

    STOPS_DIR.mkdir(exist_ok=True)
    # limpa stops sintéticos antigos
    for antigo in STOPS_DIR.glob("*.json"):
        antigo.unlink()

    for i, p in enumerate(paradas):
        edges = []
        for q in paradas:
            if p == q:
                continue
            d = round(haversine_km(coords[p], coords[q]) * 1.30, 3)  # 1.30 = fator de rota (vias não são retas)
            edges.append({
                "origin": p,
                "destination": q,
                "distance": d,
                "estimated_travel_time": round(d / VEL_MEDIA_KMH * 60, 1),
            })
        arquivo = STOPS_DIR / f"stop_{i:03d}.json"
        with open(arquivo, "w", encoding="utf-8") as f:
            json.dump({"label": p, "lat": coords[p][0], "lon": coords[p][1],
                       "edges": edges, "_sintetico": True}, f,
                      ensure_ascii=False, indent=2)

    print(f"[gerar_stops] {len(paradas)} paradas escritas em: {STOPS_DIR}")
    print("[gerar_stops] ⚠  Distâncias FICTÍCIAS (Haversine × 1.30). "
          "Substitua pela matriz real da branch python/VRP.")


if __name__ == "__main__":
    main()
