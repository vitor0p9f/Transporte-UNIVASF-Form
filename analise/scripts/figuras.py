"""
figuras.py — Gera as figuras do artigo em PNG a partir dos CSV de dados.

Edite as constantes de PALETA/estilo abaixo para mudar a aparencia; nenhuma
figura e desenhada a mao, todas saem dos dados em artigo/dados/.

Uso:
    python figuras.py            # todas
    python figuras.py cobertura  # apenas uma

Saida: artigo/figuras/*.png
"""

from __future__ import annotations

import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402
import pandas as pd                      # noqa: E402
from matplotlib.lines import Line2D      # noqa: E402

import core                              # noqa: E402

FIGS = core.SAIDA.parent / "figuras"

# ---- Paleta categorica (3 primeiros slots; validados em all-pairs) ----------
COR = {"cw1": "#2a78d6", "cw13": "#eb6834", "multi": "#1baf7a"}
# ---- Paleta de estado (nunca sozinha: sempre acompanhada de rotulo) --------
BOM, RUIM = "#0ca30c", "#d03b3b"
# ---- Tinta e superficie ----------------------------------------------------
TINTA, TINTA2, TINTA3 = "#0b0b0b", "#52514e", "#8a8880"
FUNDO = "#ffffff"
GRADE = "#e3e2dd"

plt.rcParams.update({
    "figure.facecolor": FUNDO, "axes.facecolor": FUNDO,
    "savefig.facecolor": FUNDO, "font.family": "DejaVu Sans",
    "font.size": 10, "axes.titlesize": 11, "axes.labelsize": 10,
    "axes.edgecolor": TINTA3, "axes.linewidth": 0.8,
    "xtick.color": TINTA2, "ytick.color": TINTA2,
    "text.color": TINTA, "axes.labelcolor": TINTA,
    "legend.frameon": False, "axes.spines.top": False,
    "axes.spines.right": False,
})


def _grade(ax, eixo="y"):
    ax.grid(axis=eixo, color=GRADE, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)


def _salvar(fig, nome):
    FIGS.mkdir(parents=True, exist_ok=True)
    destino = FIGS / nome
    fig.savefig(destino, dpi=200, bbox_inches="tight")
    plt.close(fig)
    print(f"  gravado: {destino.name}")


def _obs() -> pd.DataFrame:
    """Instancia observada = replica 0."""
    df = pd.read_csv(core.SAIDA / "replicas.csv")
    return df[df.replica == 0].copy()


# ------------------------------------------------------------- fig 1 cobertura

def fig_cobertura():
    df = _obs()
    turnos = core.TURNOS
    bracos = ["cw1", "cw13", "multi"]
    larg = 0.26
    x = np.arange(len(turnos))

    fig, ax = plt.subplots(figsize=(8.8, 3.2))
    _grade(ax)
    for k, br in enumerate(bracos):
        vals = [df[(df.turno == t) & (df.braco == br)].cobertura.iloc[0]
                for t in turnos]
        pos = x + (k - 1) * larg
        ax.bar(pos, vals, larg * 0.92, color=COR[br], zorder=3,
               label=core.NOME_BRACO[br])
        for p, v in zip(pos, vals):          # rotulo direto (regra de relevo)
            ax.text(p, v + 1.5, f"{v:.0f}", ha="center", va="bottom",
                    fontsize=7.5, color=TINTA2)

    ax.axhline(100, color=TINTA3, linestyle=(0, (4, 3)), linewidth=1, zorder=2)
    ax.text(-0.52, 101.5, "demanda total", fontsize=8, color=TINTA2, ha="left")
    ax.set_xticks(x, [core.ROTULO[t] for t in turnos])
    # Rotulo curto: com a figura mais baixa, o texto longo nao cabe na altura
    # do eixo e era cortado no topo.
    ax.set_ylabel("Demanda transportada (%)")
    ax.set_ylim(0, 116)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.legend(loc="lower center", bbox_to_anchor=(0.5, -0.22), ncol=3)
    _salvar(fig, "fig1-cobertura.png")


# ------------------------------------------------------------------ fig 2 pico

def fig_pico():
    df = _obs()
    turnos = core.TURNOS[::-1]
    y = np.arange(len(turnos))

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.4), sharex=True, sharey=True)
    for ax, br in zip(axes, ["cw1", "multi"]):
        _grade(ax, "x")
        rep = [df[(df.turno == t) & (df.braco == br)].pico_repositorio.iloc[0]
               for t in turnos]
        rec = [df[(df.turno == t) & (df.braco == br)].pico.iloc[0] for t in turnos]

        for i, (a, b) in enumerate(zip(rep, rec)):
            if a != b:
                ax.plot([b, a], [i, i], color=TINTA3, linewidth=1.6, zorder=3)
                ax.text((a + b) / 2, i + 0.22, f"+{a - b}", ha="center",
                        va="bottom", fontsize=8, color=TINTA2)
        ax.scatter(rep, y, s=52, color="#eb6834", zorder=4, label="Reportado")
        ax.scatter(rec, y, s=52, color="#2a78d6", zorder=5, label="Recomputado")

        ax.axvline(core.CAPACIDADE, color=RUIM, linestyle=(0, (4, 3)),
                   linewidth=1.1, zorder=2)
        # Anotacao na BASE do painel: no topo ela colidia com o rotulo "+22"
        # da linha da Manha 1.
        ax.annotate(f"capacidade = {core.CAPACIDADE}",
                    xy=(core.CAPACIDADE, -0.62), xytext=(3, 0),
                    textcoords="offset points", fontsize=8, color=RUIM,
                    ha="left", va="bottom")
        ax.set_title(core.NOME_BRACO[br], color=TINTA, pad=10)
        ax.set_xlabel("Pico de lotação (passageiros)")

    axes[0].set_yticks(y, [core.ROTULO[t] for t in turnos])
    axes[0].set_ylim(-0.7, len(turnos) - 0.15)
    axes[0].legend(loc="lower center", bbox_to_anchor=(1.06, -0.32), ncol=2)
    _salvar(fig, "fig2-pico-lotacao.png")


# ---------------------------------------------------------------- fig 4 efeitos

def fig_efeitos():
    res = pd.read_csv(core.SAIDA / "estatistica_cw1_vs_multi.csv")
    res = res.iloc[::-1].reset_index(drop=True)

    # Um efeito cujo IC 95% contem zero NAO e pintado como melhora nem piora:
    # a direcao nao e distinguivel do acaso. Cinza + rotulo "sem efeito".
    nulo = (res.ic_lo <= 0) & (res.ic_hi >= 0)
    melhora = np.where(res.direcao == "menor", res.var_pct < 0, res.var_pct > 0)
    cores = np.where(nulo, TINTA3, np.where(melhora, BOM, RUIM))
    marcas = np.where(nulo, "sem efeito", np.where(melhora, "melhora", "piora"))
    y = np.arange(len(res))

    fig, ax = plt.subplots(figsize=(9.2, 4.0))
    _grade(ax, "x")
    ax.barh(y, res.var_pct, 0.62, color=cores, zorder=3)
    ax.errorbar(res.var_pct, y,
                xerr=[np.maximum(res.var_pct - res.ic_lo, 0),
                      np.maximum(res.ic_hi - res.var_pct, 0)],
                fmt="none", ecolor=TINTA, elinewidth=1.1, capsize=3, zorder=4)
    ax.axvline(0, color=TINTA3, linewidth=1, zorder=2)

    # Rotulo sempre no lado externo da barra, com folga suficiente no eixo.
    for i, r in res.iterrows():
        fora_dir = r.var_pct >= 0
        x = (max(r.var_pct, r.ic_hi) + 2.5) if fora_dir else (min(r.var_pct, r.ic_lo) - 2.5)
        ax.text(x, i, f"{r.var_pct:+.1f}%  ({marcas[i]}, r={r.r:+.2f})",
                va="center", ha="left" if fora_dir else "right",
                fontsize=8.5, color=TINTA2)

    rotulos = [r.replace("\\%", "%").replace("\\$", "$").replace("\\ ", " ")
               for r in res.rotulo]
    ax.set_yticks(y, rotulos)
    ax.set_xlabel("Variação relativa da média em relação ao Clarke-Wright clássico (%)")
    ax.set_xlim(-192, 108)   # folga a esquerda p/ o rotulo da barra de -100%
    ax.set_ylim(-1.35, len(res) - 0.35)
    ax.legend(handles=[
        Line2D([], [], color=BOM, linewidth=7, label="Melhora"),
        Line2D([], [], color=RUIM, linewidth=7, label="Piora"),
        Line2D([], [], color=TINTA3, linewidth=7, label="IC contém zero"),
        Line2D([], [], color=TINTA, linewidth=1.1, label="IC 95%"),
    ], loc="lower center", bbox_to_anchor=(0.5, -0.30), ncol=4)
    _salvar(fig, "fig4-efeitos.png")


# --------------------------------------------------------------- fig 6 tradeoff

def fig_tradeoff():
    df = pd.read_csv(core.SAIDA / "replicas.csv")
    df = df[np.isfinite(df.custo_por_pass)]
    bracos = ["cw1", "cw13", "multi"]

    # Pequenos multiplos: as tres nuvens se sobrepoem quase por completo num
    # unico painel, escondendo o braco desenhado por baixo. Facetar preserva a
    # comparacao (eixos compartilhados) sem sobreplotagem.
    fig, axes = plt.subplots(1, 3, figsize=(9.8, 3.0), sharex=True, sharey=True)
    for ax, br in zip(axes, bracos):
        _grade(ax, "both")
        rep = df[(df.braco == br) & (df.replica > 0)]
        ax.scatter(rep.cobertura, rep.custo_por_pass, s=6, alpha=0.20,
                   color=COR[br], linewidths=0, zorder=3)
        ob = df[(df.braco == br) & (df.replica == 0)]
        ax.scatter(ob.cobertura, ob.custo_por_pass, s=80, marker="D",
                   color=COR[br], edgecolor=TINTA, linewidth=1.1, zorder=5)
        ax.set_title(core.NOME_BRACO[br], color=TINTA)
        ax.set_xlabel("Cobertura da demanda (%)")
        ax.set_xlim(15, 105)

    axes[0].set_ylabel("Custo por passageiro servido (R\\$)")
    axes[0].annotate("melhor", xy=(0.955, 0.02), xytext=(0.60, 0.13),
                     xycoords="axes fraction", textcoords="axes fraction",
                     fontsize=9, color=TINTA2, va="center",
                     arrowprops=dict(arrowstyle="->", color=TINTA2, lw=1.1))
    fig.legend(handles=[
        Line2D([], [], marker="o", linestyle="", color=TINTA3, markersize=5,
               label="Réplica \\textit{bootstrap}".replace("\\textit{", "")
                     .replace("}", "")),
        Line2D([], [], marker="D", linestyle="", color=TINTA3, markersize=8,
               markeredgecolor=TINTA, label="Instância observada"),
    ], loc="lower center", bbox_to_anchor=(0.5, -0.06), ncol=2)
    _salvar(fig, "fig6-tradeoff.png")


TODAS = {"cobertura": fig_cobertura, "pico": fig_pico,
         "efeitos": fig_efeitos, "tradeoff": fig_tradeoff}


def main():
    alvos = sys.argv[1:] or list(TODAS)
    for a in alvos:
        if a not in TODAS:
            print(f"[erro] figura desconhecida: {a} (opções: {', '.join(TODAS)})")
            continue
        print(f"gerando {a}...")
        TODAS[a]()


if __name__ == "__main__":
    main()
