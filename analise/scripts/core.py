"""
core.py — Camada de avaliacao independente dos algoritmos do repositorio.

Carrega instancias de /stops, executa os tres bracos (CW-1, CW-1+CW-3 e
multi-objetivo) exatamente como plotar_rotas.py os invoca, e recomputa todos
os indicadores a partir apenas da sequencia de paradas e do conjunto de
viagens atribuidas — sem confiar em nenhum valor calculado pelo codigo
auditado.

Convencao do perfil de carga: em cada parada, primeiro DESEMBARCAM os
passageiros cujo destino e aquela parada, depois EMBARCAM os que a tem como
origem. Cada passageiro embarca no maximo uma vez (na primeira ocorrencia da
sua origem) e desembarca na primeira ocorrencia posterior do seu destino.
E essa regra que corrige o defeito D3 (reembarque duplicado).

Rode sempre com PYTHONHASHSEED=0 (ver defeito D4).
"""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

def _achar_repo() -> Path:
    """Localiza a raiz do repositorio auditado subindo a partir deste arquivo.

    Funciona nos dois layouts em que estes scripts vivem:
      <repo>/analise/scripts/core.py   -> o repo e um ancestral
      <qualquer>/artigo/scripts/core.py -> o repo e um irmao, em
                                           <qualquer>/Transporte-UNIVASF-Form
    """
    aqui = Path(__file__).resolve()
    for base in aqui.parents:
        for cand in (base, base / "Transporte-UNIVASF-Form"):
            if (cand / "stops").is_dir() and (cand / "algorithms").is_dir():
                return cand
    raise RuntimeError(
        "repositorio nao encontrado: esperava um diretorio contendo "
        "'stops/' e 'algorithms/' acima de " + str(aqui)
    )


REPO = _achar_repo()
ALGO = REPO / "algorithms"
STOPS = REPO / "stops"
SAIDA = Path(__file__).resolve().parent.parent / "dados"
sys.path.insert(0, str(ALGO))

from clarke_wright import clarke_wright_ovrp                        # noqa: E402
from clarke_wright_multi import clarke_wright_multi_ovrp            # noqa: E402
from utils.fleet import ONIBUS_GENERICO                             # noqa: E402
from utils.distance_matrix import construir_matriz, filtrar_paradas  # noqa: E402

TURNOS = ["manha_1", "manha_2", "tarde_1", "tarde_2", "noite_1", "noite_2"]
TURNO_IDX = {t: i for i, t in enumerate(TURNOS)}
ROTULO = {
    "manha_1": "Manhã 1", "manha_2": "Manhã 2", "tarde_1": "Tarde 1",
    "tarde_2": "Tarde 2", "noite_1": "Noite 1", "noite_2": "Noite 2",
}

# Depositos fixados em plotar_rotas.py (defeito D10)
DEPOT_IDS = {
    "manha_1": "9", "manha_2": "9", "tarde_1": "9",
    "tarde_2": "9", "noite_1": "37", "noite_2": "9",
}

CAPACIDADE = 48
CONFORTO = 36
MAX_TEMPO = 90.0
MODELO = ONIBUS_GENERICO

_STOPS_CACHE: dict | None = None
_MATRIZ_CACHE: tuple | None = None


# ---------------------------------------------------------------- carregamento

def carregar_stops() -> dict:
    global _STOPS_CACHE
    if _STOPS_CACHE is None:
        stops = {}
        for arq in sorted(STOPS.glob("*.json"), key=lambda p: int(p.stem)
                          if p.stem.isdigit() else 0):
            with open(arq, "r", encoding="utf-8") as f:
                dados = json.load(f)
            stops[str(dados.get("label", arq.stem))] = dados
        _STOPS_CACHE = stops
    return _STOPS_CACHE


def matrizes_globais():
    """Constroi as matrizes completas uma unica vez (custo alto, reuso barato)."""
    global _MATRIZ_CACHE
    if _MATRIZ_CACHE is None:
        stops = carregar_stops()
        nos, m_dist = construir_matriz(stops, metrica="distance")
        _, m_tempo = construir_matriz(stops, metrica="estimated_travel_time")
        _MATRIZ_CACHE = (nos, m_dist, m_tempo)
    return _MATRIZ_CACHE


def viagens_do_turno(turno: str) -> list[dict]:
    """Extrai as viagens (pares origem-destino) do vetor de demanda das arestas."""
    stops = carregar_stops()
    idx = TURNO_IDX[turno]
    viagens, tid = [], 1
    for stop_id in stops:
        for edge in stops[stop_id].get("edges", []):
            demanda = edge.get("demand", [])
            if len(demanda) > idx and int(demanda[idx]) > 0:
                dest = str(edge["destination"])
                for _ in range(int(demanda[idx])):
                    viagens.append({"id": tid, "embarque": stop_id,
                                    "desembarque": dest})
                    tid += 1
    return viagens


class Instancia:
    """Uma instancia de roteamento: grafo filtrado + conjunto de viagens."""

    def __init__(self, turno: str, viagens: list[dict], deposito: str | None = None):
        self.turno = turno
        self.viagens = viagens
        self.deposito = deposito or DEPOT_IDS[turno]
        nos, m_dist, m_tempo = matrizes_globais()
        ativas = ({t["embarque"] for t in viagens}
                  | {t["desembarque"] for t in viagens}
                  | {self.deposito})
        self.nos, self.dist = filtrar_paradas(nos, m_dist, ativas)
        _, self.tempo = filtrar_paradas(nos, m_tempo, ativas)

    @property
    def n(self) -> int:
        return len(self.viagens)


def instancia_observada(turno: str, deposito: str | None = None) -> Instancia:
    return Instancia(turno, viagens_do_turno(turno), deposito)


def reamostrar(base: Instancia, rng) -> Instancia:
    """Bootstrap por casos: sorteia n viagens com reposicao, com ids novos."""
    n = base.n
    idxs = rng.integers(0, n, size=n)
    viagens = []
    for novo_id, i in enumerate(idxs, 1):
        t = dict(base.viagens[int(i)])
        t["id"] = novo_id
        viagens.append(t)
    return Instancia(base.turno, viagens, base.deposito)


# ------------------------------------------------------------------- execucao

def _sequenciar_desembarques(paradas_embarque, viagens_atendidas, dist, deposito):
    """Anexa os desembarques ao final por vizinho mais proximo.

    Reproduz FIELMENTE converter_rota_classica_para_multi() de plotar_rotas.py,
    inclusive a iteracao sobre um `set` nao ordenado — que e a origem do defeito
    D4 no braco classico. Nao "conserte" isto: o objetivo e medir o codigo como
    publicado. A reprodutibilidade vem de fixar PYTHONHASHSEED=0.
    """
    seq = [deposito] + list(paradas_embarque)
    pendentes = set(t["desembarque"] for t in viagens_atendidas)
    curr = paradas_embarque[-1] if paradas_embarque else deposito
    while pendentes:
        melhor, menor = None, float("inf")
        for d in pendentes:
            dd = dist.get(curr, {}).get(d, float("inf"))
            if dd < menor:
                menor, melhor = dd, d
        if melhor is None:
            break
        seq.append(melhor)
        pendentes.remove(melhor)
        curr = melhor
    return seq


def rodar_classico(inst: Instancia, postimprove: bool = False) -> list[dict]:
    """Braco classico, replicando a montagem de demanda de plotar_rotas.py."""
    demanda = {}
    for t in inst.viagens:
        p = t["embarque"]
        if p != inst.deposito:      # <- defeito D1, preservado de proposito
            demanda.setdefault(p, {"boarding": 0, "alighting": 0})
            demanda[p]["boarding"] += 1

    if not demanda:
        return []

    rotas_raw, _ = clarke_wright_ovrp(
        nos=inst.nos, matriz=inst.dist, demanda=demanda,
        deposito=inst.deposito, capacidade=CAPACIDADE, modelo=MODELO,
        usar_two_phase=False, usar_postimprove=postimprove, verbose=False,
    )

    solucao = []
    for r in rotas_raw:
        if not r.paradas:
            continue
        conj = set(r.paradas)
        atendidas = [t for t in inst.viagens if t["embarque"] in conj]
        seq = _sequenciar_desembarques(r.paradas, atendidas, inst.dist,
                                       inst.deposito)
        solucao.append({"paradas": seq, "viagens": atendidas})
    return solucao


def rodar_multi(inst: Instancia) -> list[dict]:
    """Braco multi-objetivo, invocado como plotar_rotas.py o invoca."""
    rotas, _ = clarke_wright_multi_ovrp(
        nos=inst.nos, matriz_dist=inst.dist, matriz_tempo=inst.tempo,
        viagens=deepcopy(inst.viagens), deposito=inst.deposito,
        capacidade=CAPACIDADE, modelo=MODELO, conforto=CONFORTO,
        max_tempo=MAX_TEMPO, verbose=False,
    )
    # O modelo multi-objetivo calcula cargas_trecho durante a construcao,
    # consumindo cada viagem uma unica vez; plotar_rotas.py usa esse valor
    # diretamente. Logo o "pico reportado" deste braco e o proprio
    # carga_maxima, e nao a simulacao do defeito D3 (que so afete o classico).
    return [{"paradas": list(r.paradas), "viagens": list(r.viagens_atendidas),
             "pico_reportado": r.carga_maxima}
            for r in rotas]


BRACOS = {
    "cw1": lambda inst: rodar_classico(inst, postimprove=False),
    "cw13": lambda inst: rodar_classico(inst, postimprove=True),
    "multi": rodar_multi,
}
NOME_BRACO = {
    "cw1": "Clássico (CW-1)",
    "cw13": "Clássico + CW-3",
    "multi": "Multi-objetivo",
}


# ------------------------------------------------- recomputacao independente

def perfil_carga(paradas: list[str], viagens: list[dict]) -> dict:
    """Reconstroi o perfil de carga garantindo embarque unico por passageiro."""
    pendentes: dict[str, list[dict]] = {}
    for t in viagens:
        pendentes.setdefault(t["embarque"], []).append(t)

    a_bordo: list[dict] = []
    servidas = 0
    cargas: list[int] = []

    for node in paradas:
        descem = [t for t in a_bordo if t["desembarque"] == node]
        for t in descem:
            a_bordo.remove(t)
            servidas += 1
        if node in pendentes:
            a_bordo.extend(pendentes.pop(node))
        cargas.append(len(a_bordo))

    return {
        "cargas": cargas,
        "pico": max(cargas) if cargas else 0,
        "servidas": servidas,
        "nao_embarcaram": sum(len(v) for v in pendentes.values()),
        "nao_desembarcaram": len(a_bordo),
        "paradas_repetidas": len(paradas) - len(set(paradas)),
    }


def perfil_carga_repositorio(paradas: list[str], viagens: list[dict]) -> int:
    """Reproduz o pico COM o defeito D3 (reembarque a cada visita da parada).

    Replica converter_rota_classica_para_multi(): a cada parada visitada, o
    embarque e recalculado filtrando a lista COMPLETA de viagens atendidas, de
    modo que uma parada repetida embarca os mesmos passageiros outra vez.
    A ordem tambem e a do repositorio: embarque antes do desembarque.
    Aplica-se apenas ao braco classico.
    """
    a_bordo: list[dict] = []
    pico = 0
    for node in paradas:
        a_bordo.extend([t for t in viagens if t["embarque"] == node])
        for t in [t for t in a_bordo if t["desembarque"] == node]:
            a_bordo.remove(t)
        pico = max(pico, len(a_bordo))
    return pico


def metricas_rota(rota: dict, inst: Instancia) -> dict:
    paradas, viagens = rota["paradas"], rota["viagens"]
    perfil = perfil_carga(paradas, viagens)
    dist = tempo = 0.0
    for a, b in zip(paradas, paradas[1:]):
        d = inst.dist.get(a, {}).get(b, 0.0)
        t = inst.tempo.get(a, {}).get(b, 0.0)
        dist += 0.0 if d == float("inf") else d
        tempo += 0.0 if t == float("inf") else t
    reportado = rota.get("pico_reportado")
    if reportado is None:                       # braco classico: sofre D3
        reportado = perfil_carga_repositorio(paradas, viagens)
    return {
        **perfil,
        "pico_repositorio": reportado,
        "dist_km": round(dist, 4),
        "tempo_min": round(tempo, 2),
        "custo_brl": MODELO.custo_rota(dist),
    }


def avaliar(solucao: list[dict], inst: Instancia) -> dict:
    """Indicadores agregados de uma solucao, todos recomputados."""
    rotas = [metricas_rota(r, inst) for r in solucao]
    servidas = sum(r["servidas"] for r in rotas)
    custo = round(sum(r["custo_brl"] for r in rotas), 2)
    total = inst.n
    return {
        "veiculos": len(rotas),
        "dist_km": round(sum(r["dist_km"] for r in rotas), 2),
        "tempo_min": round(sum(r["tempo_min"] for r in rotas), 2),
        "custo_brl": custo,
        "servidas": servidas,
        "demanda_total": total,
        "cobertura": 100.0 * servidas / total if total else 0.0,
        "custo_por_pass": custo / servidas if servidas else float("nan"),
        "pico": max((r["pico"] for r in rotas), default=0),
        "pico_repositorio": max((r["pico_repositorio"] for r in rotas), default=0),
        "superlotados": sum(1 for r in rotas if r["pico"] > CAPACIDADE),
        "desconforto": sum(max(0, r["pico"] - CONFORTO) for r in rotas),
        "acima_tempo": sum(1 for r in rotas if r["tempo_min"] > MAX_TEMPO),
        "paradas_repetidas": sum(r["paradas_repetidas"] for r in rotas),
    }
