"""Loading helper for the scenario CSVs.

Os cenários executados são a soma de dois arquivos na raiz do projeto,
lidos nesta ordem:

    scenarios.csv       gerado por scripts/generate_scenarios.py (arqueti)
    scenarios_base.csv  configuração fixa da instância ``base`` — escrita à
                        mão, não sorteada (ver o docstring do gerador)

Ambos usam as mesmas colunas (ver SCENARIO_FIELDS em
``scripts/generate_scenarios.py``). Por padrão as linhas cuja instância não
tem ``distance.csv`` no disco são descartadas — é o mesmo filtro que os
executores (`main.py`, `scripts/run_all.py`) já aplicavam.
"""

import csv
from pathlib import Path

#: Arquivos de cenário somados, na ordem.
SCENARIO_FILES = ("scenarios.csv", "scenarios_base.csv")


def parse_node_labels(value: object) -> tuple[int, ...] | None:
    """Lê um campo de nós separados por ponto e vírgula, ex.: ``"43;44;45"``.

    Usado pelas colunas ``origin`` (origens permitidas do draft) e
    ``destination_labels`` (destinos permitidos do par). Campo vazio ou
    ausente significa "livre" (None), não "nenhum nó".
    """
    if value is None:
        return None
    ids = [item.strip() for item in str(value).split(";") if item.strip()]
    return tuple(int(item) for item in ids) or None


def load_scenarios(
    root: str | Path,
    files: tuple[str, ...] = SCENARIO_FILES,
    require_matrices: bool = True,
) -> list[dict]:
    """Lê e soma os arquivos de cenário existentes em `root`.

    Args:
        root: Raiz do projeto (onde ficam os CSVs).
        files: Nomes dos arquivos, na ordem de leitura.
        require_matrices: Descarta cenários de instâncias sem `distance.csv`.

    Returns:
        Linhas de cenário (dicts) na ordem dos arquivos; arquivos ausentes
        são simplesmente ignorados.
    """
    root = Path(root)
    scenarios: list[dict] = []
    for name in files:
        path = root / name
        if not path.exists():
            continue
        with path.open(newline="", encoding="utf-8") as f:
            scenarios.extend(csv.DictReader(f))
    if require_matrices:
        scenarios = [
            s for s in scenarios
            if (root / "instances" / s["instance_id"] / "distance.csv").exists()
        ]
    return scenarios
