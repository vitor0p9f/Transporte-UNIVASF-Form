# Algoritmos de Otimização — Transporte UNIVASF

Branch: `python/algorithms`

Implementações dos algoritmos de otimização para o problema **OVRP** (Open Vehicle Routing Problem) do transporte universitário da UNIVASF.

Os ônibus partem de um depósito (campus), percorrem as paradas e **ficam no campus destino** — não retornam ao ponto de origem. Isso caracteriza o OVRP.

---

## Estrutura

```
algorithms/
├── data/
│   ├── viagens.csv        ← exportar do Supabase (não versionado — contém e-mails)
│   └── README.md          ← formato esperado do CSV
├── output/                ← resultados gerados (não versionado)
├── utils/
│   ├── loader.py          ← carrega e pré-processa o CSV do Supabase
│   ├── distance_matrix.py ← monta a matriz de distâncias a partir dos stops/*.json
│   └── fleet.py           ← modelos de ônibus (capacidade, consumo, custo/km)
├── clarke_wright.py       ← algoritmo Clarke-Wright OVRP (CW-1 + CW-2 + CW-3)
├── teste.py               ← testes com dados sintéticos (sem precisar do CSV)
├── requirements.txt
└── README.md
```

---

## Setup

```bash
cd algorithms
pip install -r requirements.txt
```

**Dependências:** `pandas >= 2.0`, `networkx >= 3.0`, `matplotlib >= 3.7`

---

## Dados de entrada

### 1. CSV do Supabase (`data/viagens.csv`)

Exportar a tabela `viagens` no painel do Supabase:
**Table Editor → viagens → Export → CSV**

| Coluna        | Tipo   | Descrição                                         |
|---------------|--------|---------------------------------------------------|
| `id`          | int    | Identificador único                               |
| `email`       | string | E-mail do participante (usado só para deduplicação) |
| `turno`       | string | Slug do turno: `manha_1`, `manha_2`, `tarde_1`, `tarde_2`, `noite_1`, `noite_2` |
| `embarque`    | string | Nome da parada de embarque                        |
| `desembarque` | string | Nome da parada de desembarque                     |
| `lotacao`     | int    | Índice de lotação percebida (1–5)                 |
| `created_at`  | string | Timestamp UTC da inserção                         |

O `loader.py` remove automaticamente **respostas duplicadas** por `(email, turno)`, mantendo a mais recente.

**Dados reais (Mai/2026):** 654 viagens válidas distribuídas em 6 turnos:

| Turno     | Viagens | Paradas c/ demanda | Lotação média |
|-----------|---------|-------------------|---------------|
| `manha_1` | 234     | 34                | 4.44 / 5      |
| `noite_1` | 164     | 34                | 4.04 / 5      |
| `tarde_1` | 95      | 27                | 3.82 / 5      |
| `noite_2` | 69      | 26                | 3.61 / 5      |
| `tarde_2` | 50      | 18                | 3.13 / 5      |
| `manha_2` | 42      | 12                | 3.60 / 5      |

### 2. Matriz de distâncias (`stops/*.json`)

Produzida pela branch `python/VRP`. Quando os arquivos estiverem disponíveis, basta copiar a pasta `stops/` para a raiz do projeto — o código a detecta automaticamente.

Enquanto isso, o algoritmo usa **distância euclidiana como fallback** (aviso exibido no terminal).

---

## Como usar

### Teste rápido com dados sintéticos (sem CSV)

```bash
python teste.py --turno manha_1 --sem-two-phase --sem-postimprove
python teste.py --todos     # testa manha_1, tarde_1 e noite_1
```

### Rodar com os dados reais

```bash
# Modo rápido (só CW-1): testa todos os lambdas, sem iterações extra
python clarke_wright.py --turno manha_1 --sem-two-phase --sem-postimprove

# Modo completo (CW-1 + CW-2 + CW-3): mais preciso, mais lento
python clarke_wright.py --turno manha_1

# Salvar resultado em output/
python clarke_wright.py --turno manha_1 --salvar

# Lambda fixo (pula a busca automática)
python clarke_wright.py --turno tarde_1 --lambda-val 1.2 --salvar

# Otimizar por tempo de viagem ao invés de distância
python clarke_wright.py --turno noite_1 --metrica estimated_travel_time

# Ver modelos de ônibus cadastrados
python clarke_wright.py --frota
```

### Parâmetros disponíveis

| Parâmetro           | Padrão                     | Descrição                                               |
|---------------------|----------------------------|---------------------------------------------------------|
| `--turno`           | `manha_1`                  | Slug do turno a otimizar                                |
| `--capacidade`      | `48`                       | Capacidade máxima do veículo (passageiros)              |
| `--deposito`        | `UNIVASF Campus Petrolina` | Ponto de partida da frota                               |
| `--csv`             | `data/viagens.csv`         | Caminho do CSV                                          |
| `--metrica`         | `distance`                 | `distance` (km) ou `estimated_travel_time` (min)        |
| `--lambda-val`      | automático                 | Valor fixo de λ; se omitido testa 0.1 a 2.0            |
| `--sem-two-phase`   | —                          | Desativa two-phase selection (execução mais rápida)     |
| `--sem-postimprove` | —                          | Desativa post-improvement (execução mais rápida)        |
| `--sentido`         | `auto`                     | `ida` (carga = embarques) / `volta` (carga = desembarques) / `auto` |
| `--conforto`        | do modelo (`36`)           | Lotação confortável por ônibus (sentados)               |
| `--peso-superlotacao` | `0`                      | Penalidade R$/passageiro acima do conforto (0 = custo puro) |
| `--pareto`          | —                          | Varre capacidades e mostra o trade-off custo × superlotação |
| `--salvar`          | —                          | Salva resultado JSON em `output/`                       |
| `--frota`           | —                          | Exibe modelos de ônibus cadastrados e sai               |

> **Windows:** rode com `python -X utf8 ...` (ou `set PYTHONUTF8=1`) para os acentos saírem corretos no terminal.

---

## Superlotação: sentido, conforto e Pareto

O problema de superlotação é tratado por três mecanismos:

1. **Carga por sentido.** Na *ida* (rumo ao campus) a carga de cada parada são os
   **embarques**; na *volta* (saindo do campus) são os **desembarques** — porque na
   volta quase todos embarcam no próprio campus. O `auto` detecta pelo depósito.
   *(Antes o código usava sempre embarques e zerava a demanda dos turnos noturnos.)*

2. **Objetivo consciente de superlotação.** Com `--peso-superlotacao > 0` o algoritmo
   passa a minimizar `combustível + peso·(passageiros acima do conforto)`, preferindo
   distribuir gente em mais ônibus a deixar veículos lotados. Com peso `0` é custo puro.

3. **Curva de Pareto** (`--pareto`). Varre o limite de lotação por ônibus e mostra,
   para cada nível de conforto, quantos ônibus são necessários e o custo — a tabela
   que responde *"quanto custa cada nível de conforto"*:

```bash
python clarke_wright.py --turno noite_1 --deposito "UNIVASF Campus CCA" --pareto
python clarke_wright.py --turno manha_1 --peso-superlotacao 10   # objetivo consciente
```

---

## Algoritmo: Clarke-Wright OVRP

Baseado em:
> Pichpibul, T. & Kawtummachai, R. (2013). *A Heuristic Approach Based on Clarke-Wright Algorithm for Open Vehicle Routing Problem*. The Scientific World Journal, Article ID 874349. https://doi.org/10.1155/2013/874349

### Fórmula de savings (OVRP)

```
s(i,j) = c(depot, j) − λ · c(i, j)
```

Diferença em relação ao CVRP clássico: remove o termo `c(i, depot)` pois o veículo **não retorna** ao depósito.

### Procedimentos implementados

| Etapa | Código         | Descrição                                                              |
|-------|----------------|------------------------------------------------------------------------|
| CW-1  | `calcular_savings_ovrp` | Fórmula OVRP com λ; testa 0.1–2.0 e mantém o melhor  |
| CW-2  | `_melhor_direcao` + `two_phase_selection` | Rota aberta em ambas as direções + reordenação probabilística da lista de savings (5000 iterações) |
| CW-3  | `post_improvement` | Busca local com 2-opt intra-rota, shift 1-0 e swap 1-1 inter-rotas (500 iterações sem melhora) |

### Função objetivo

```
minimizar: Σ distância_rota × (custo_litro / consumo_km_l)
sujeito a: carga_rota ≤ capacidade_veículo
```

O custo é calculado em **R$** usando os parâmetros de `ModeloOnibus`.

---

## Modelos de ônibus (`utils/fleet.py`)

Atualmente usa um **modelo genérico placeholder**. Substitua pelos dados reais da frota UNIVASF:

```python
# Em utils/fleet.py
ONIBUS_GENERICO = ModeloOnibus(
    nome         = "Mercedes-Benz OF 1721",  # modelo real
    capacidade   = 44,                        # passageiros sentados
    consumo_km_l = 3.1,                       # km/litro real
    custo_litro  = 6.80,                      # R$/litro do diesel
)
```

---

## Pipeline completo

```
Supabase → viagens.csv
              ↓
         loader.py
    (deduplica por email+turno,
     agrega embarques/desembarques)
              ↓
    distance_matrix.py
    (stops/*.json  →  matriz km)
    (fallback euclidiano se não disponível)
              ↓
    clarke_wright.py
    CW-1: savings OVRP com λ
    CW-2: rota aberta + two-phase
    CW-3: 2-opt / shift / swap
              ↓
    output/cw_ovrp_<turno>.json
```

---

## Algoritmos planejados

- [x] **Clarke-Wright OVRP** — CW-1 + CW-2 + CW-3 (Pichpibul & Kawtummachai, 2013)
- [ ] **Algoritmo Genético (GA)**
- [ ] **Ant Colony Optimization (ACO)**
- [ ] **Comparação com OR-Tools** (validação contra solver de referência)
