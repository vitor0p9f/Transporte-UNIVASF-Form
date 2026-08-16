"""
sensibilidade.py — Tres analises de sensibilidade sobre a instancia observada.

  1. hash   : reproduz o defeito D4 rodando o mesmo codigo, sobre a mesma
              entrada, em 40 processos que diferem apenas em PYTHONHASHSEED.
  2. lambda : varredura de lambda no modelo multi-objetivo (defeito D9).
  3. deposito: cobertura media por criterio de escolha do deposito (D10).

Uso:
    python sensibilidade.py hash [--sementes 40]
    PYTHONHASHSEED=0 python sensibilidade.py lambda
    PYTHONHASHSEED=0 python sensibilidade.py deposito

Saidas em artigo/dados/: sens_hash.csv, sens_lambda.csv, sens_deposito.csv
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys

import pandas as pd

import core

CAMPUS_PETROLINA = "45"   # UNIVASF / PETROLINA
CAMPUS_JUAZEIRO = "44"    # UNIVASF / JUAZEIRO


# ------------------------------------------------------------------ 1. hash

def _worker_hash() -> None:
    """Executado no subprocesso: resolve todos os turnos e imprime JSON."""
    saida = {}
    for turno in core.TURNOS:
        inst = core.instancia_observada(turno)
        linha = {}
        for braco in ("cw1", "multi"):
            m = core.avaliar(core.BRACOS[braco](inst), inst)
            linha[braco] = {k: m[k] for k in
                            ("veiculos", "dist_km", "custo_brl", "cobertura",
                             "pico", "acima_tempo")}
        saida[turno] = linha
    print("@@JSON@@" + json.dumps(saida))


def analise_hash(n_sementes: int) -> None:
    registros = []
    for semente in range(1, n_sementes + 1):
        env = dict(os.environ, PYTHONHASHSEED=str(semente))
        proc = subprocess.run(
            [sys.executable, __file__, "_worker_hash"],
            env=env, capture_output=True, text=True, cwd=os.path.dirname(__file__),
        )
        marca = proc.stdout.find("@@JSON@@")
        if marca < 0:
            print(f"[erro] semente {semente}:\n{proc.stderr[-500:]}")
            continue
        dados = json.loads(proc.stdout[marca + 8:])
        for turno, bracos in dados.items():
            for braco, m in bracos.items():
                registros.append({"semente": semente, "turno": turno,
                                  "braco": braco, **m})
        print(f"  semente {semente}/{n_sementes}", flush=True)

    df = pd.DataFrame(registros)
    df.to_csv(core.SAIDA / "sens_hash.csv", index=False)

    print("\n=== Dispersao entre sementes de hash (defeito D4) ===")
    print(f"{'turno':10s} {'braco':6s} {'solucoes':>8s} {'custo min':>10s} "
          f"{'custo max':>10s} {'dispersao':>10s} {'frota':>8s}")
    for (turno, braco), g in df.groupby(["turno", "braco"]):
        n_sol = g[["veiculos", "dist_km", "custo_brl"]].drop_duplicates().shape[0]
        lo, hi = g.custo_brl.min(), g.custo_brl.max()
        disp = 100.0 * (hi - lo) / lo if lo else 0.0
        frota = f"{g.veiculos.min()}-{g.veiculos.max()}"
        print(f"{turno:10s} {braco:6s} {n_sol:8d} {lo:10.2f} {hi:10.2f} "
              f"{disp:9.1f}% {frota:>8s}")


# ---------------------------------------------------------------- 2. lambda

def analise_lambda() -> None:
    from clarke_wright_multi import clarke_wright_multi_ovrp
    from copy import deepcopy

    registros = []
    for turno in core.TURNOS:
        inst = core.instancia_observada(turno)
        for i in range(20):
            lam = round(0.1 + i * 0.1, 1)
            rotas, _ = clarke_wright_multi_ovrp(
                nos=inst.nos, matriz_dist=inst.dist, matriz_tempo=inst.tempo,
                viagens=deepcopy(inst.viagens), deposito=inst.deposito,
                capacidade=core.CAPACIDADE, modelo=core.MODELO,
                lam=lam, conforto=core.CONFORTO, max_tempo=core.MAX_TEMPO,
                verbose=False,
            )
            sol = [{"paradas": list(r.paradas),
                    "viagens": list(r.viagens_atendidas)} for r in rotas]
            m = core.avaliar(sol, inst)
            registros.append({"turno": turno, "lam": lam,
                              **{k: m[k] for k in ("veiculos", "dist_km",
                                                   "custo_brl", "cobertura",
                                                   "pico")}})
        print(f"  {turno} concluído", flush=True)

    df = pd.DataFrame(registros)
    df.to_csv(core.SAIDA / "sens_lambda.csv", index=False)

    print("\n=== Varredura de lambda no modelo multi-objetivo (defeito D9) ===")
    print(f"{'turno':10s} {'solucoes distintas':>19s} {'cobertura min-max':>20s}")
    for turno, g in df.groupby("turno"):
        n_sol = g[["veiculos", "dist_km", "custo_brl"]].drop_duplicates().shape[0]
        print(f"{turno:10s} {n_sol:19d} "
              f"{g.cobertura.min():9.1f}% - {g.cobertura.max():.1f}%")


# -------------------------------------------------------------- 3. deposito

def criterios_deposito(turno: str) -> dict[str, str]:
    """Os quatro criterios comparados.

    'Maior movimento' reproduz escolher_deposito() de rodar_todos.py, que soma
    EMBARQUES + DESEMBARQUES (nao apenas embarques).
    """
    viagens = core.viagens_do_turno(turno)
    movimento: dict[str, int] = {}
    for t in viagens:
        movimento[t["embarque"]] = movimento.get(t["embarque"], 0) + 1
        movimento[t["desembarque"]] = movimento.get(t["desembarque"], 0) + 1
    maior = max(sorted(movimento), key=lambda p: movimento[p]) if movimento else "9"
    return {
        "Fixado no código (\\texttt{DEPOT\\_IDS})": core.DEPOT_IDS[turno],
        "Parada de maior movimento": maior,
        "Campus Petrolina": CAMPUS_PETROLINA,
        "Campus Juazeiro": CAMPUS_JUAZEIRO,
    }


def analise_deposito() -> None:
    registros = []
    for turno in core.TURNOS:
        for criterio, dep in criterios_deposito(turno).items():
            inst = core.Instancia(turno, core.viagens_do_turno(turno), dep)
            for braco in ("cw1", "multi"):
                m = core.avaliar(core.BRACOS[braco](inst), inst)
                registros.append({"turno": turno, "criterio": criterio,
                                  "deposito": dep, "braco": braco,
                                  "cobertura": m["cobertura"],
                                  "custo_brl": m["custo_brl"],
                                  "veiculos": m["veiculos"]})
        print(f"  {turno} concluído", flush=True)

    df = pd.DataFrame(registros)
    df.to_csv(core.SAIDA / "sens_deposito.csv", index=False)

    tabela = df.pivot_table(index="criterio", columns="braco",
                            values="cobertura", aggfunc="mean")
    print("\n=== Cobertura média (%) por critério de depósito (defeito D10) ===")
    print(tabela.round(1).to_string())

    ordem = ["Fixado no código (\\texttt{DEPOT\\_IDS})",
             "Parada de maior movimento", "Campus Petrolina", "Campus Juazeiro"]
    linhas = [f"  {c} & {tabela.loc[c, 'cw1']:.1f} & {tabela.loc[c, 'multi']:.1f} \\\\"
              .replace(".", ",") for c in ordem if c in tabela.index]
    tex = (
        "% gerado por scripts/sensibilidade.py — nao editar a mao\n"
        "\\begin{table}[htb]\n"
        "\\caption{\\label{tab:deposito}Cobertura média da demanda (\\%) sobre os\n"
        "         seis turnos, segundo o critério de escolha do depósito.}\n"
        "\\centering\n\\small\n"
        "\\begin{tabular}{@{}L{7.0cm}rr@{}}\n  \\toprule\n"
        "  \\textbf{Critério de escolha do depósito} & \\textbf{Clássico} &\n"
        "  \\textbf{Multi-objetivo} \\\\\n  \\midrule\n"
        + "\n".join(linhas) + "\n  \\bottomrule\n\\end{tabular}\n"
        "\\fonte{Elaboração própria.}\n"
        "\\nota{O critério de maior movimento já está implementado no\n"
        "      repositório, mas não é utilizado pelo \\textit{script} que gera o\n"
        "      comparativo publicado.}\n\\end{table}\n"
    )
    tab = core.SAIDA.parent / "tabelas"
    tab.mkdir(parents=True, exist_ok=True)
    (tab / "tab-deposito.tex").write_text(tex, encoding="utf-8")
    print(f"\ntabela gravada em {tab / 'tab-deposito.tex'}")


def main() -> None:
    if len(sys.argv) > 1 and sys.argv[1] == "_worker_hash":
        _worker_hash()
        return

    ap = argparse.ArgumentParser()
    ap.add_argument("analise", choices=["hash", "lambda", "deposito"])
    ap.add_argument("--sementes", type=int, default=40)
    args = ap.parse_args()

    core.SAIDA.mkdir(parents=True, exist_ok=True)
    if args.analise == "hash":
        analise_hash(args.sementes)
    elif args.analise == "lambda":
        analise_lambda()
    else:
        analise_deposito()


if __name__ == "__main__":
    main()
