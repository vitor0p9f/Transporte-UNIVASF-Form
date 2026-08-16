# Scripts de análise do artigo

Tudo que aparece no `main.tex` como número, tabela ou figura sai daqui. Nenhum
valor é digitado à mão no LaTeX.

## Pré-requisitos

```
python 3.12+, numpy, scipy, pandas, matplotlib
```

O repositório auditado precisa estar em `../../Transporte-UNIVASF-Form/`
(estrutura: `artigo/scripts/` e `Transporte-UNIVASF-Form/algorithms/` irmãos
dentro da mesma pasta).

## Ordem de execução

```bash
cd artigo/scripts

# 1. Mapa de rótulos das paradas (lê a branch origin/python/VRP via git)
PYTHONHASHSEED=0 python mapear_paradas.py

# 2. Experimento pareado — 6 turnos x 400 réplicas x 3 braços (~20 min)
PYTHONHASHSEED=0 python experimento.py --replicas 400

# 3. Estatística pareada -> tabelas/tab-estatistica.tex
PYTHONHASHSEED=0 python estatistica.py --a cw1 --b multi

# 4. Tabela de instâncias -> tabelas/tab-instancias.tex
PYTHONHASHSEED=0 python tabelas.py

# 5. Análises de sensibilidade
PYTHONHASHSEED=0 python sensibilidade.py deposito   # -> tabelas/tab-deposito.tex
PYTHONHASHSEED=0 python sensibilidade.py lambda
python sensibilidade.py hash --sementes 40          # SEM fixar a semente!

# 6. Figuras -> figuras/*.png
PYTHONHASHSEED=0 python figuras.py

# 7. Conferência: imprime todos os números citados no texto
PYTHONHASHSEED=0 python numeros.py
```

**`PYTHONHASHSEED=0` não é opcional.** Os dois modelos iteram sobre `set` não
ordenados (defeito D4), então o resultado muda entre processos. A única exceção
é `sensibilidade.py hash`, cujo objetivo é justamente medir essa variação.

## O que cada arquivo faz

| Arquivo | Papel |
|---|---|
| `core.py` | Carrega instâncias, executa os 3 braços e **recomputa** todos os indicadores de forma independente do código auditado |
| `experimento.py` | Bootstrap por casos + gravação de `dados/replicas.csv` |
| `estatistica.py` | Wilcoxon pareado, correlação bisserial de postos, Holm, IC bootstrap |
| `sensibilidade.py` | Semente de hash (D4), varredura de λ (D9), critério de depósito (D10) |
| `mapear_paradas.py` | Reconstrói número → nome da parada casando demanda e geometria |
| `figuras.py` | Todas as figuras; edite as constantes de cor no topo |
| `tabelas.py` | Tabela 1 em LaTeX |
| `numeros.py` | Despeja todos os números do texto para conferência |

## Pontos de atenção em `core.py`

- `perfil_carga()` é a recomputação **correta**: cada passageiro embarca uma
  única vez. É o que corrige o defeito D3.
- `perfil_carga_repositorio()` reproduz o defeito D3 de propósito, para medir o
  tamanho do erro. Aplica-se **apenas ao braço clássico** — o modelo
  multi-objetivo calcula a carga durante a construção e não passa por essa
  rotina.
- `_sequenciar_desembarques()` itera sobre um `set` de propósito, para ser fiel
  a `converter_rota_classica_para_multi()`. **Não "conserte" isso**: o objetivo
  é medir o código como publicado.

## Editando as figuras

As cores estão no topo de `figuras.py`. A paleta categórica usa os três
primeiros slots de uma paleta validada para daltonismo (ΔE ≥ 8 em todos os
pares, deutan/protan/tritan). Se trocar as cores, revalide antes de usar.

Para regerar só uma figura: `python figuras.py cobertura` (ou `pico`,
`efeitos`, `tradeoff`).
