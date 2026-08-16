"""
mapear_paradas.py — Reconstroi a correspondencia entre os rotulos numericos de
stops/ (branch feat/custom-implementation) e os nomes reais das paradas
(branch origin/python/VRP), que o repositorio nao versiona junto.

Estrategia em duas fases:
  1. casamento pelo par (boardings, alightings) — 12 numeros por parada;
  2. desempate pelo multiconjunto de distancias das arestas incidentes.

Saida: artigo/dados/mapa_paradas.json
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict

import core

BRANCH = "origin/python/VRP"


def stops_rotulados() -> dict:
    """Le os stops nomeados direto do git, sem alterar a arvore de trabalho."""
    listagem = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", BRANCH],
        cwd=core.REPO, capture_output=True, text=True, check=True,
    ).stdout.split("\n")
    arquivos = [a for a in listagem if a.startswith("stops/") and a.endswith(".json")]

    stops = {}
    for arq in arquivos:
        bruto = subprocess.run(
            ["git", "show", f"{BRANCH}:{arq}"],
            cwd=core.REPO, capture_output=True, check=True,
        ).stdout.decode("utf-8")
        dados = json.loads(bruto)
        stops[dados["label"]] = dados
    return stops


def assinatura_demanda(d: dict) -> tuple:
    return (tuple(d.get("boardings", [])), tuple(d.get("alightings", [])))


def assinatura_arestas(d: dict) -> tuple:
    return tuple(sorted(round(float(e.get("distance", 0)), 3)
                        for e in d.get("edges", [])))


def main() -> None:
    numericos = core.carregar_stops()
    nomeados = stops_rotulados()
    print(f"numericos={len(numericos)}  nomeados={len(nomeados)}")

    # fase 1: agrupa por assinatura de demanda
    por_dem_num = defaultdict(list)
    for k, v in numericos.items():
        por_dem_num[assinatura_demanda(v)].append(k)
    por_dem_nom = defaultdict(list)
    for k, v in nomeados.items():
        por_dem_nom[assinatura_demanda(v)].append(k)

    mapa: dict[str, str] = {}
    ambiguos: list[tuple] = []

    for assinatura, nums in por_dem_num.items():
        noms = por_dem_nom.get(assinatura, [])
        if len(nums) == 1 and len(noms) == 1:
            mapa[nums[0]] = noms[0]
        elif noms:
            ambiguos.append((assinatura, nums, noms))

    print(f"fase 1 (demanda): {len(mapa)} paradas identificadas")

    # fase 2: propagacao pela estrutura origem-destino.
    # Para cada parada ainda ambigua, compara o vetor de distancias ate as
    # paradas JA identificadas — uma assinatura geometrica que so a parada
    # correta reproduz.
    def dist_para(dados: dict, chave_destino) -> dict:
        return {chave_destino(e["destination"]): round(float(e.get("distance", 0)), 3)
                for e in dados.get("edges", [])}

    resolvidos = 1
    while resolvidos:
        resolvidos = 0
        ancoras_num = set(mapa)                     # numericos ja resolvidos
        for _, nums, noms in ambiguos:
            livres_num = [n for n in nums if n not in mapa]
            livres_nom = [n for n in noms if n not in set(mapa.values())]
            for num in livres_num:
                d_num = dist_para(numericos[num], lambda x: str(x))
                # traduz destinos numericos -> nomes, so onde ja se sabe
                alvo = {mapa[k]: v for k, v in d_num.items()
                        if k in ancoras_num}
                if len(alvo) < 3:
                    continue
                candidatos = []
                for nom in livres_nom:
                    d_nom = dist_para(nomeados[nom], lambda x: str(x))
                    if all(d_nom.get(k) == v for k, v in alvo.items()):
                        candidatos.append(nom)
                if len(candidatos) == 1:
                    mapa[num] = candidatos[0]
                    livres_nom.remove(candidatos[0])
                    ancoras_num.add(num)
                    resolvidos += 1
        if resolvidos:
            print(f"fase 2 (propagacao): +{resolvidos} paradas identificadas")
    print(f"TOTAL: {len(mapa)}/{len(numericos)} paradas identificadas")

    nao_id = sorted(set(numericos) - set(mapa), key=lambda x: int(x))
    if nao_id:
        print(f"nao identificadas: {', '.join(nao_id)}")

    core.SAIDA.mkdir(parents=True, exist_ok=True)
    destino = core.SAIDA / "mapa_paradas.json"
    with open(destino, "w", encoding="utf-8") as f:
        json.dump({k: mapa[k] for k in sorted(mapa, key=lambda x: int(x))},
                  f, ensure_ascii=False, indent=2)
    print(f"\ngravado em {destino}")

    # confere os depositos usados por plotar_rotas.py (defeito D10)
    print("\nDepositos fixados em DEPOT_IDS:")
    for turno, dep in core.DEPOT_IDS.items():
        print(f"  {turno:9s} -> parada {dep:>2s} = {mapa.get(dep, '??')}")

    # valida contra o relatorio original: parada 20 deve ser a GBarbosa
    if "20" in mapa:
        print(f"\nvalidacao: parada 20 = {mapa['20']}")
        print(f"           boardings = {numericos['20']['boardings']}")


if __name__ == "__main__":
    main()
