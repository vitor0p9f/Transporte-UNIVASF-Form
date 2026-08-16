"""
estatistica.py — Comparacao pareada entre os bracos sobre as replicas bootstrap.

Para cada desfecho calcula:
  - media de cada braco;
  - variacao relativa das medias (%), com IC 95% por bootstrap percentilico
    pareado (4.000 reamostragens dos PARES);
  - teste de postos com sinais de Wilcoxon (bilateral) sobre as diferencas
    pareadas;
  - correlacao bisserial de postos pareada (formula da diferenca simples,
    Kerby 2014), em [-1, +1];
  - p ajustado para multiplicidade pelo procedimento de Holm.

Uso:
    python estatistica.py [--a cw1] [--b multi]

Saidas:
    artigo/dados/estatistica_<a>_vs_<b>.csv
    artigo/tabelas/tab-estatistica.tex   (apenas para o par principal)
"""

from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from scipy import stats

import core

B_BOOT = 4000
SEMENTE = 20260812

# desfecho -> (rotulo, direcao desejavel, casas decimais)
DESFECHOS = {
    "veiculos":       ("Veículos utilizados",              "menor", 2),
    "dist_km":        ("Distância total (km)",             "menor", 2),
    "custo_brl":      ("Custo de combustível (R\\$)",      "menor", 2),
    "cobertura":      ("Cobertura da demanda (\\%)",       "maior", 2),
    "custo_por_pass": ("Custo por pass.\\ servido (R\\$)", "menor", 2),
    "pico":           ("Pico de lotação (pass.)",          "menor", 2),
    "superlotados":   ("Veículos superlotados",            "menor", 3),
    "desconforto":    ("Passageiros em desconforto",       "menor", 2),
    "acima_tempo":    ("Rotas acima de 90 min",            "menor", 2),
}


def rank_biserial(d: np.ndarray) -> float:
    """Correlacao bisserial de postos pareada (Kerby 2014).

    +1 = b excede a sempre; -1 = b fica abaixo de a sempre; 0 = simetria.
    Empates (d == 0) sao descartados, como no proprio teste de Wilcoxon.
    """
    d = d[d != 0]
    if d.size == 0:
        return 0.0
    postos = stats.rankdata(np.abs(d))
    total = postos.sum()
    return float((postos[d > 0].sum() - postos[d < 0].sum()) / total)


def ic_variacao(x: np.ndarray, y: np.ndarray, rng) -> tuple[float, float]:
    """IC 95% percentilico da variacao relativa das medias, reamostrando PARES."""
    n = x.size
    idx = rng.integers(0, n, size=(B_BOOT, n))
    mx = x[idx].mean(axis=1)
    my = y[idx].mean(axis=1)
    with np.errstate(divide="ignore", invalid="ignore"):
        var = 100.0 * (my - mx) / mx
    var = var[np.isfinite(var)]
    return float(np.percentile(var, 2.5)), float(np.percentile(var, 97.5))


def holm(ps: list[float]) -> list[float]:
    """Ajuste sequencialmente rejeitivo de Holm (1979), com imposicao de monotonia."""
    m = len(ps)
    ordem = np.argsort(ps)
    ajust = np.empty(m, dtype=float)
    corrente = 0.0
    for posicao, i in enumerate(ordem):
        valor = (m - posicao) * ps[i]
        corrente = max(corrente, valor)
        ajust[i] = min(1.0, corrente)
    return ajust.tolist()


def comparar(df: pd.DataFrame, braco_a: str, braco_b: str) -> pd.DataFrame:
    a = df[df.braco == braco_a].sort_values(["turno", "replica"]).reset_index(drop=True)
    b = df[df.braco == braco_b].sort_values(["turno", "replica"]).reset_index(drop=True)
    assert (a.turno == b.turno).all() and (a.replica == b.replica).all(), \
        "pares desalinhados"

    rng = np.random.default_rng(SEMENTE)
    linhas, ps = [], []

    for chave, (rotulo, direcao, casas) in DESFECHOS.items():
        x = a[chave].to_numpy(dtype=float)
        y = b[chave].to_numpy(dtype=float)
        ok = np.isfinite(x) & np.isfinite(y)
        x, y = x[ok], y[ok]
        d = y - x

        mx, my = x.mean(), y.mean()
        var = 100.0 * (my - mx) / mx if mx != 0 else float("nan")
        lo, hi = ic_variacao(x, y, rng)

        if np.any(d != 0):
            p = stats.wilcoxon(x, y, zero_method="wilcox",
                               alternative="two-sided").pvalue
        else:
            p = 1.0
        ps.append(float(p))

        linhas.append({
            "desfecho": chave, "rotulo": rotulo, "direcao": direcao,
            "casas": casas, "n_pares": int(x.size),
            "media_a": mx, "media_b": my, "var_pct": var,
            "ic_lo": lo, "ic_hi": hi, "r": rank_biserial(d),
            "p_bruto": float(p),
            "n_favoravel_b": int((d < 0).sum() if direcao == "menor" else (d > 0).sum()),
            "n_empate": int((d == 0).sum()),
        })

    for linha, p_aj in zip(linhas, holm(ps)):
        linha["p_holm"] = p_aj
    return pd.DataFrame(linhas)


def fmt_num(v: float, casas: int) -> str:
    """Numero em notacao brasileira para MODO TEXTO (1.234,56)."""
    return f"{v:,.{casas}f}".replace(",", "@").replace(".", ",").replace("@", ".")


def fmt_mat(v: float, casas: int) -> str:
    """Idem, mas para MODO MATEMATICO: a virgula vira {,} para nao ser tratada
    como pontuacao (o que insere um espaco fino indevido)."""
    return fmt_num(v, casas).replace(",", "{,}")


def fmt_p(p: float) -> str:
    return "$<0{,}001$" if p < 0.001 else f"${fmt_mat(p, 3)}$"


def fmt_sinal(v: float, casas: int = 1) -> str:
    return ("$+" if v >= 0 else "$-") + fmt_mat(abs(v), casas) + r"\%$"


def fmt_ic(lo: float, hi: float) -> str:
    def com_sinal(v):
        return ("+" if v >= 0 else "-") + fmt_mat(abs(v), 1)
    return f"$[{com_sinal(lo)};\\,{com_sinal(hi)}]$"


def gerar_tabela_tex(res: pd.DataFrame, braco_a: str, braco_b: str) -> str:
    destaque = {"cobertura", "custo_por_pass"}
    linhas = []
    for _, r in res.iterrows():
        neg = r.desfecho in destaque
        env = (lambda s: r"\textbf{" + s + "}") if neg else (lambda s: s)
        matenv = (lambda s: s.replace("$", r"$\bm{", 1) + "}"
                  if False else s)  # mantido simples
        rotulo = env(r.rotulo)
        ma = env(fmt_num(r.media_a, int(r.casas)))
        mb = env(fmt_num(r.media_b, int(r.casas)))
        var = fmt_sinal(r.var_pct)
        ic = (fmt_ic(r.ic_lo, r.ic_hi)
              if np.isfinite(r.ic_lo) and abs(r.var_pct) < 99.99 else "---")
        rr = ("$+" if r.r >= 0 else "$-") + fmt_mat(abs(r.r), 2) + "$"
        if neg:
            var = var.replace("$", r"$\bm{", 1)[:-1] + r"}$"
            ic = ic.replace("$[", r"$\bm{[", 1)[:-1] + r"}$"
            rr = rr.replace("$", r"$\bm{", 1)[:-1] + r"}$"
        linhas.append(f"  {rotulo} & {ma} & {mb} & {var} &\n"
                      f"    {ic} & {rr} & {fmt_p(r.p_holm)} \\\\")
    corpo = "\n".join(linhas)
    n = int(res.n_pares.max())
    return (
        "% gerado por scripts/estatistica.py — nao editar a mao\n"
        "\\begin{table}[htb]\n"
        f"\\caption{{\\label{{tab:estatistica}}Comparação pareada entre o modelo\n"
        f"         multi-objetivo e o Clarke-Wright clássico (CW-1) sobre "
        f"{fmt_num(n, 0)}\n         instâncias. Valores médios por instância.}}\n"
        "\\centering\n\\scriptsize\n"
        "\\begin{tabular}{@{}L{3.6cm}rrrcrc@{}}\n"
        "  \\toprule\n"
        "  \\textbf{Desfecho} & \\textbf{Cláss.} & \\textbf{Multi} &\n"
        "  \\textbf{Var.} & \\textbf{IC 95\\%} & $\\bm{r}$ & $\\bm{p}$ \\\\\n"
        "  \\midrule\n" + corpo + "\n"
        "  \\bottomrule\n"
        "\\end{tabular}\n"
        "\\fonte{Elaboração própria.}\n"
        "\\nota{IC 95\\% obtido por \\textit{bootstrap} pareado com 4.000\n"
        "      reamostragens; $r$ é a correlação bisserial de postos pareada;\n"
        "      $p$ ajustado pelo procedimento de Holm.}\n"
        "\\end{table}\n"
    )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", default="cw1")
    ap.add_argument("--b", default="multi")
    args = ap.parse_args()

    df = pd.read_csv(core.SAIDA / "replicas.csv")
    res = comparar(df, args.a, args.b)

    core.SAIDA.mkdir(parents=True, exist_ok=True)
    res.to_csv(core.SAIDA / f"estatistica_{args.a}_vs_{args.b}.csv", index=False)

    print(f"\n=== {core.NOME_BRACO[args.b]} vs {core.NOME_BRACO[args.a]} "
          f"({int(res.n_pares.max())} pares) ===\n")
    largura = max(len(r) for r in res.rotulo)
    for _, r in res.iterrows():
        limpo = r.rotulo.replace("\\\\", "").replace("\\", "")
        print(f"{limpo:<{largura}} | {r.media_a:9.3f} -> {r.media_b:9.3f} | "
              f"{r.var_pct:+7.1f}% [{r.ic_lo:+6.1f};{r.ic_hi:+6.1f}] | "
              f"r={r.r:+.2f} | p={r.p_holm:.2e} | "
              f"emp={r.n_empate}")

    if args.a == "cw1" and args.b == "multi":
        tab = core.SAIDA.parent / "tabelas"
        tab.mkdir(parents=True, exist_ok=True)
        (tab / "tab-estatistica.tex").write_text(
            gerar_tabela_tex(res, args.a, args.b), encoding="utf-8")
        print(f"\ntabela gravada em {tab / 'tab-estatistica.tex'}")


if __name__ == "__main__":
    main()
