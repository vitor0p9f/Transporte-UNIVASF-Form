"""
experimento.py — Experimento pareado por reamostragem bootstrap.

Para cada turno gera B replicas bootstrap do conjunto de viagens, resolve cada
uma pelos tres bracos (CW-1, CW-1+CW-3, multi-objetivo) e grava um CSV longo
com todos os indicadores recomputados.

A replica 0 de cada turno e a instancia OBSERVADA (sem reamostragem), usada
nas figuras 1 e 2.

Uso:
    PYTHONHASHSEED=0 python experimento.py [--replicas 400]

Saida:
    artigo/dados/replicas.csv
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import time

import numpy as np

import core

SEMENTE_BASE = 20260812

CAMPOS = ["turno", "replica", "braco", "veiculos", "dist_km", "tempo_min",
          "custo_brl", "servidas", "demanda_total", "cobertura",
          "custo_por_pass", "pico", "pico_repositorio", "superlotados",
          "desconforto", "acima_tempo", "paradas_repetidas"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--replicas", type=int, default=400,
                    help="replicas por turno, incluindo a instancia observada")
    args = ap.parse_args()

    if os.environ.get("PYTHONHASHSEED") != "0":
        print("[aviso] PYTHONHASHSEED != 0: os resultados NAO serao "
              "reproduziveis (defeito D4).", file=sys.stderr)

    core.SAIDA.mkdir(parents=True, exist_ok=True)
    destino = core.SAIDA / "replicas.csv"

    t_inicio = time.time()
    linhas = 0
    with open(destino, "w", newline="", encoding="utf-8") as fh:
        escritor = csv.DictWriter(fh, fieldnames=CAMPOS)
        escritor.writeheader()

        for i_turno, turno in enumerate(core.TURNOS):
            base = core.instancia_observada(turno)
            rng = np.random.default_rng(SEMENTE_BASE + i_turno)
            t0 = time.time()

            for b in range(args.replicas):
                inst = base if b == 0 else core.reamostrar(base, rng)
                for braco, fn in core.BRACOS.items():
                    m = core.avaliar(fn(inst), inst)
                    escritor.writerow({
                        "turno": turno, "replica": b, "braco": braco,
                        **{k: m[k] for k in CAMPOS[3:]},
                    })
                    linhas += 1

                if (b + 1) % 50 == 0:
                    fh.flush()
                    print(f"  {turno}: {b + 1}/{args.replicas} réplicas "
                          f"({time.time() - t0:.0f}s)", flush=True)

            print(f"[OK] {turno} concluído em {time.time() - t0:.0f}s "
                  f"(n={base.n} viagens)", flush=True)

    print(f"\n{linhas} linhas gravadas em {destino}")
    print(f"Tempo total: {time.time() - t_inicio:.0f}s")


if __name__ == "__main__":
    main()
