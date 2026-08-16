"""
numeros.py — Imprime todos os numeros citados no texto do artigo, na ordem em
que aparecem, para conferencia e transcricao sem erro.

Uso: PYTHONHASHSEED=0 python numeros.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

import core

SEP = "=" * 74


def secao(titulo: str):
    print(f"\n{SEP}\n{titulo}\n{SEP}")


def main() -> None:
    df = pd.read_csv(core.SAIDA / "replicas.csv")
    obs = df[df.replica == 0]

    # ---------------------------------------------------------- instancias
    secao("TABELA 1 — instancias por turno")
    mapa = json.loads((core.SAIDA / "mapa_paradas.json").read_text(encoding="utf-8"))
    total_viagens = total_dep = 0
    for t in core.TURNOS:
        v = core.viagens_do_turno(t)
        dep = core.DEPOT_IDS[t]
        paradas = ({x["embarque"] for x in v} | {x["desembarque"] for x in v}) - {dep}
        n_dep = sum(1 for x in v if x["embarque"] == dep)
        total_viagens += len(v)
        total_dep += n_dep
        print(f"  {core.ROTULO[t]:8s} viagens={len(v):4d} paradas={len(paradas):3d} "
              f"dep={dep:>2s} ({mapa.get(dep, '??')[:44]}) emb_dep={n_dep:3d}")
    print(f"  TOTAL viagens={total_viagens}  embarques no deposito={total_dep} "
          f"({100 * total_dep / total_viagens:.1f}%)")

    # ------------------------------------------------------------ grafo
    secao("GRAFO")
    stops = core.carregar_stops()
    arestas = {(s, str(e["destination"])): float(e.get("distance", 0))
               for s in stops for e in stops[s].get("edges", [])}
    reciprocos = assimetricos = 0
    for (a, b), d in arestas.items():
        if a < b and (b, a) in arestas:
            reciprocos += 1
            if abs(arestas[(b, a)] - d) > 1e-9:
                assimetricos += 1
    print(f"  paradas={len(stops)}  arestas dirigidas={len(arestas)}")
    print(f"  pares reciprocos={reciprocos}  com distancia diferente="
          f"{assimetricos} ({100 * assimetricos / reciprocos:.1f}%)")
    print(f"  mapa de paradas reconstruido: {len(mapa)}/{len(stops)}")

    # ---------------------------------------------- reproducao manha_1
    secao("REPRODUCAO DO EXPERIMENTO ORIGINAL (Manha 1, PYTHONHASHSEED=0)")
    for br in ["cw1", "multi"]:
        r = obs[(obs.turno == "manha_1") & (obs.braco == br)].iloc[0]
        print(f"  {core.NOME_BRACO[br]:18s} veic={r.veiculos} dist={r.dist_km:.1f} km "
              f"tempo={r.tempo_min:.0f} min custo=R${r.custo_brl:.2f} "
              f"pico_reportado={r.pico_repositorio:.0f} pico_real={r.pico:.0f} "
              f"rotas>90min={r.acima_tempo}")

    # ----------------------------------------------------- D1 / D5 / cobertura
    secao("COBERTURA POR TURNO (instancia observada)")
    print(f"  {'turno':9s} {'total':>6s} {'cw1':>16s} {'cw13':>16s} {'multi':>16s}")
    for t in core.TURNOS:
        linha = f"  {core.ROTULO[t]:9s}"
        tot = obs[(obs.turno == t) & (obs.braco == "cw1")].demanda_total.iloc[0]
        linha += f" {tot:6.0f}"
        for br in ["cw1", "cw13", "multi"]:
            r = obs[(obs.turno == t) & (obs.braco == br)].iloc[0]
            linha += f" {r.servidas:5.0f} ({r.cobertura:5.1f}%)"
        print(linha)
    print("\n  perdas do multi ALEM das do classico (defeito D5):")
    for t in core.TURNOS:
        c = obs[(obs.turno == t) & (obs.braco == "cw1")].servidas.iloc[0]
        m = obs[(obs.turno == t) & (obs.braco == "multi")].servidas.iloc[0]
        if c != m:
            print(f"    {core.ROTULO[t]:9s} {c - m:.0f} viagens")

    # ------------------------------------------------------------- D3 pico
    secao("D3 — PICO REPORTADO vs RECOMPUTADO (instancia observada)")
    for br in ["cw1", "multi"]:
        print(f"  {core.NOME_BRACO[br]}:")
        for t in core.TURNOS:
            r = obs[(obs.turno == t) & (obs.braco == br)].iloc[0]
            marca = "  <-- excede capacidade" if r.pico > core.CAPACIDADE else ""
            print(f"    {core.ROTULO[t]:9s} reportado={r.pico_repositorio:3.0f} "
                  f"real={r.pico:3.0f} delta={r.pico_repositorio - r.pico:+3.0f} "
                  f"paradas_repetidas={r.paradas_repetidas:2.0f}{marca}")

    # --------------------------------------------------------- Noite 1 custo
    secao("NOITE 1 — custo enganoso (D5)")
    for br in ["cw1", "multi"]:
        r = obs[(obs.turno == "noite_1") & (obs.braco == br)].iloc[0]
        print(f"  {core.NOME_BRACO[br]:18s} custo=R${r.custo_brl:.2f} "
              f"servidas={r.servidas:.0f} custo/pass=R${r.custo_por_pass:.2f} "
              f"rotas>90min={r.acima_tempo}")

    # ----------------------------------------------------- estatistica pareada
    secao("TABELA 3 — comparacao pareada (2.400 instancias)")
    res = pd.read_csv(core.SAIDA / "estatistica_cw1_vs_multi.csv")
    for _, r in res.iterrows():
        nulo = "  [IC CONTEM ZERO]" if r.ic_lo <= 0 <= r.ic_hi else ""
        print(f"  {r.desfecho:16s} {r.media_a:9.3f} -> {r.media_b:9.3f} "
              f"{r.var_pct:+7.1f}% [{r.ic_lo:+6.1f};{r.ic_hi:+6.1f}] "
              f"r={r.r:+.2f} p={r.p_holm:.2e}{nulo}")

    n_sup_cw1 = int((df[df.braco == "cw1"].superlotados > 0).sum())
    n_sup_multi = int((df[df.braco == "multi"].superlotados > 0).sum())
    print(f"\n  instancias com veiculo superlotado: cw1={n_sup_cw1}/2400  "
          f"multi={n_sup_multi}/2400")

    # ------------------------------------------------------------ CW-3
    secao("BRACO CW-1+CW-3 vs CW-1 (efeito do pos-processamento)")
    a = df[df.braco == "cw1"].sort_values(["turno", "replica"]).reset_index(drop=True)
    b = df[df.braco == "cw13"].sort_values(["turno", "replica"]).reset_index(drop=True)
    d = 100 * (b.custo_brl - a.custo_brl) / a.custo_brl
    print(f"  custo: variacao mediana={np.median(d):+.2f}%  media={d.mean():+.2f}%")
    print(f"  cobertura identica em {100 * (a.cobertura == b.cobertura).mean():.1f}% das instancias")
    print(f"  pico identico em {100 * (a.pico == b.pico).mean():.1f}% das instancias")

    # ------------------------------------------------------------ D4 hash
    caminho_hash = core.SAIDA / "sens_hash.csv"
    if caminho_hash.exists():
        secao("D4 — dispersao entre 40 sementes de hash")
        h = pd.read_csv(caminho_hash)
        for (t, br), g in h.groupby(["turno", "braco"]):
            n_sol = g[["veiculos", "dist_km", "custo_brl"]].drop_duplicates().shape[0]
            lo, hi = g.custo_brl.min(), g.custo_brl.max()
            disp = 100 * (hi - lo) / lo if lo else 0
            if n_sol > 1:
                print(f"  {core.ROTULO[t]:9s} {br:6s} solucoes={n_sol:2d} "
                      f"custo {lo:.2f}-{hi:.2f} dispersao={disp:.1f}% "
                      f"frota={g.veiculos.min()}-{g.veiculos.max()}")
        deterministicos = [f"{core.ROTULO[t]}/{br}"
                           for (t, br), g in h.groupby(["turno", "braco"])
                           if g[["veiculos", "dist_km", "custo_brl"]]
                           .drop_duplicates().shape[0] == 1]
        print(f"  deterministicos ({len(deterministicos)}/12): "
              f"{', '.join(deterministicos)}")

    # ------------------------------------------------------------ D9 lambda
    caminho_lam = core.SAIDA / "sens_lambda.csv"
    if caminho_lam.exists():
        secao("D9 — varredura de lambda (20 valores)")
        lam = pd.read_csv(caminho_lam)
        for t, g in lam.groupby("turno"):
            n_sol = g[["veiculos", "dist_km", "custo_brl"]].drop_duplicates().shape[0]
            print(f"  {core.ROTULO[t]:9s} solucoes distintas={n_sol:2d} "
                  f"cobertura {g.cobertura.min():.1f}%-{g.cobertura.max():.1f}%")

    # ---------------------------------------------------------- D10 deposito
    caminho_dep = core.SAIDA / "sens_deposito.csv"
    if caminho_dep.exists():
        secao("TABELA 4 — cobertura media por criterio de deposito")
        dep = pd.read_csv(caminho_dep)
        piv = dep.pivot_table(index="criterio", columns="braco",
                              values="cobertura", aggfunc="mean")
        print(piv.round(1).to_string())
        print("\n  Manha 1 e Noite 1, por criterio (cw1):")
        for t in ["manha_1", "noite_1"]:
            for _, r in dep[(dep.turno == t) & (dep.braco == "cw1")].iterrows():
                print(f"    {core.ROTULO[t]:9s} {r.criterio[:38]:40s} "
                      f"parada={str(r.deposito):>3s} "
                      f"cobertura={r.cobertura:5.1f}%")


if __name__ == "__main__":
    main()
