"""
tabelas.py — Gera tab-instancias.tex (Tabela 1) a partir dos dados.

As demais tabelas sao geradas por:
    tab-estatistica.tex -> estatistica.py
    tab-deposito.tex    -> sensibilidade.py deposito

Uso: PYTHONHASHSEED=0 python tabelas.py
"""

from __future__ import annotations

import json

import core

FAIXA = {
    "manha_1": "6h--8h", "manha_2": "9h--10h", "tarde_1": "11h--13h",
    "tarde_2": "14h--16h", "noite_1": "17h--18h", "noite_2": "18h--23h",
}


def bonito(nome: str) -> str:
    """Converte O NOME EM CAIXA ALTA para Forma Legivel / Cidade."""
    if "/" in nome:
        local, cidade = nome.rsplit("/", 1)
    else:
        local, cidade = nome, ""
    minusculas = {"de", "da", "do", "das", "dos", "e", "av.", "2"}
    palavras = []
    for i, p in enumerate(local.strip().lower().split()):
        palavras.append(p if (i and p in minusculas) else p.capitalize())
    saida = " ".join(palavras)
    return f"{saida} / {cidade.strip().capitalize()}" if cidade else saida


def main() -> None:
    mapa = json.loads((core.SAIDA / "mapa_paradas.json").read_text(encoding="utf-8"))

    linhas, tot_v, tot_d = [], 0, 0
    for t in core.TURNOS:
        v = core.viagens_do_turno(t)
        dep = core.DEPOT_IDS[t]
        paradas = ({x["embarque"] for x in v} | {x["desembarque"] for x in v}) - {dep}
        n_dep = sum(1 for x in v if x["embarque"] == dep)
        tot_v += len(v)
        tot_d += n_dep
        # A coluna com o nome do deposito foi removida: o texto longo forcava a
        # tabela a ocupar a largura toda, e a informacao esta na prosa (cinco
        # dos seis turnos usam a mesma parada).
        linhas.append(
            f"  {core.ROTULO[t]} ({FAIXA[t]}) & {len(v)} & {len(paradas)} & "
            f"{dep} & {n_dep} \\\\"
        )

    tex = (
        "% gerado por scripts/tabelas.py — nao editar a mao\n"
        "\\begin{table}[htb]\n"
        "\\caption{\\label{tab:instancias}Instâncias por turno. A demanda é o número\n"
        "         de pares origem-destino declarados; o depósito é o fixado em\n"
        "         \\texttt{plotar\\_rotas.py} e identificado conforme a\n"
        "         Seção~\\ref{sec:instancias}.}\n"
        "\\centering\n\\small\n"
        "\\begin{tabular}{@{}lrrrr@{}}\n  \\toprule\n"
        "  \\textbf{Turno} & \\textbf{Viagens} & \\textbf{Paradas} &\n"
        "  \\textbf{Depósito} & \\textbf{Emb.\\ no dep.} \\\\\n"
        "  \\midrule\n" + "\n".join(linhas) + "\n  \\midrule\n"
        f"  \\textbf{{Total}} & \\textbf{{{tot_v}}} & & & \\textbf{{{tot_d}}} \\\\\n"
        "  \\bottomrule\n\\end{tabular}\n"
        "\\fonte{Elaboração própria a partir dos arquivos \\texttt{stops/}.}\n"
        "\\end{table}\n"
    )

    destino = core.SAIDA.parent / "tabelas"
    destino.mkdir(parents=True, exist_ok=True)
    (destino / "tab-instancias.tex").write_text(tex, encoding="utf-8")
    print(f"gravado em {destino / 'tab-instancias.tex'}")
    print(f"  total: {tot_v} viagens, {tot_d} embarques no depósito "
          f"({100 * tot_d / tot_v:.1f}%)")


if __name__ == "__main__":
    main()
