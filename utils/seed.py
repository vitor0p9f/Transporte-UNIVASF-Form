"""Seed raiz da geração sintética de dados.

Todo dado sintético do projeto sai da MESMA seed raiz `DEFAULT_SEED`:

    tempos de viagem + demandas  -> scripts/generate_instances.py
    frota (fleet.csv)            -> scripts/generate_fleet.py
    cenários (scenarios.csv)     -> scripts/generate_scenarios.py
    matrizes ausentes            -> utils.synth.ensure_matrices

Rodar os três geradores com o mesmo `--seed` reproduz exatamente as mesmas
instâncias, frota e cenários; para trocar o experimento inteiro, troque só
`DEFAULT_SEED` aqui (ou passe `--seed` em cada gerador).

O `scripts/run_all.py` registra a seed usada no cabeçalho do `results.md`.
"""

DEFAULT_SEED = 42
