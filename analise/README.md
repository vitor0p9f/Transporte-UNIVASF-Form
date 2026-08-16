# Camada de auditoria e avaliação

Código que gera os números, tabelas e figuras do artigo de reexame dos dois
modelos de roteamento (`clarke_wright.py` e `clarke_wright_multi.py`).

**Os algoritmos auditados não são modificados.** Esta camada apenas os invoca e
recomputa os indicadores por fora, a partir da sequência de paradas e do
conjunto de viagens atribuídas a cada rota. É essa recomputação independente
que revela as divergências entre o que o repositório reporta e o que as rotas
de fato entregam.

## Como rodar

Sempre com `PYTHONHASHSEED=0` — os dois modelos iteram sobre `set` não
ordenados e produzem soluções diferentes a cada processo sem a semente fixa.

```bash
cd analise/scripts

PYTHONHASHSEED=0 python mapear_paradas.py     # nomes das paradas (45/46)
PYTHONHASHSEED=0 python experimento.py        # 7.200 execuções (~20 min)
PYTHONHASHSEED=0 python estatistica.py        # comparação pareada
PYTHONHASHSEED=0 python tabelas.py            # tabela de instâncias
PYTHONHASHSEED=0 python sensibilidade.py deposito
PYTHONHASHSEED=0 python sensibilidade.py lambda
python sensibilidade.py hash                  # 40 sementes, em subprocessos
PYTHONHASHSEED=0 python figuras.py            # PNGs
PYTHONHASHSEED=0 python numeros.py            # confere todos os números citados
```

`experimento.py` é pré-requisito de `estatistica.py` e `figuras.py`. Os demais
são independentes entre si.

Dependências: `numpy`, `scipy`, `pandas`, `matplotlib`.

## Arquivos

| Script | Função |
|---|---|
| `core.py` | Base: carrega instâncias, executa os três braços, recomputa indicadores |
| `experimento.py` | Bootstrap pareado: 6 turnos × 400 réplicas × 3 braços |
| `estatistica.py` | Wilcoxon, correlação bisserial, Holm, IC bootstrap |
| `figuras.py` | As 4 figuras do artigo |
| `tabelas.py` | Tabela de instâncias em LaTeX |
| `sensibilidade.py` | Semente de hash (D4), varredura de λ (D9), depósito (D10) |
| `mapear_paradas.py` | Recupera os nomes das paradas a partir da branch `python/VRP` |
| `numeros.py` | Imprime todos os números citados no texto, para conferência |

`dados/` guarda as saídas. `replicas.csv` (660 KB) tem uma linha por
(turno, réplica, braço) com todos os indicadores recomputados.

## Os três braços comparados

- **`cw1`** — Clarke-Wright clássico, como o `plotar_rotas.py` o invoca
  (`usar_two_phase=False`, `usar_postimprove=False`).
- **`cw13`** — o mesmo, com o pós-processamento CW-3 ativado. Existe porque
  comparar contra um *baseline* na sua melhor configuração é requisito
  metodológico, e o script publicado desativa duas das três etapas do método
  que diz implementar.
- **`multi`** — o modelo multi-objetivo, sem alteração.

## Convenção do perfil de carga

Em cada parada, primeiro **desembarcam** os passageiros cujo destino é aquela
parada, depois **embarcam** os que a têm como origem. Cada passageiro embarca
no máximo uma vez, na primeira ocorrência da sua origem.

Essa regra é o que separa o valor real do reportado: o repositório recalcula os
embarques a cada visita, filtrando a lista completa de viagens, de modo que uma
parada repetida na rota embarca os mesmos passageiros outra vez. `core.py`
mantém as duas contagens lado a lado — `pico` (correta) e `pico_repositorio`
(reproduzindo o defeito) — justamente para medir a diferença.
