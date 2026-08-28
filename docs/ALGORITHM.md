# Algoritmo de Construção de Rotas - Greedy TOP

## Visão Geral

O sistema implementa uma heurística **Greedy Team Orienteering Problem (TOP)** para construir rotas de ônibus que maximizam o número de passageiros atendidos dentro de limites de tempo e capacidade.

```
┌─────────────────────────────────────────────────────────────────┐
│                        FLUXO PRINCIPAL                          │
├─────────────────────────────────────────────────────────────────┤
│  1. Carregar grafo e demanda por turno                          │
│  2. Para cada rodada (frota paralela):                          │
│     a. Avaliar todos os ônibus na mesma demanda residual        │
│     b. Maior prize vence a rodada (um movimento)                │
│     c. Commitar demanda servida pelo vencedor                   │
│  3. Gerar relatório de resultados                               │
└─────────────────────────────────────────────────────────────────┘
```

## 1. Estrutura de Dados

### Grafo (Graph)
```
Grafo = {Nodes, Edges, edges_by_label}

Node = {label: str}                          // Ex: "1", "10", "44"
Edge = {source: Node, destination: Node,
        distance_km: float, 
        travel_time_minutes: int}            // Direcional

edges_by_label = {(origem, destino): edge}   // Índice pré-computado O(1)
```

### Estado de Demanda (DemandState)
```
DemandState = {
    edge_demand: {(origem, destino): quantidade}
    // Ex: {("7", "44"): 5, ("9", "10"): 3}
}
```

A demanda é **residual** - diminui conforme ônibus atendem passageiros.

### Simulação de Rota (RouteSimulation)
```
RouteSimulation = {
    stops: tuple[str, ...],
    served_passengers: int,
    peak_load: int,
    travel_time_minutes: int,
    total_distance_km: int,
    total_cost: float,
    served_pairs: [(origem, destino, qtd), ...],
    route_valid: bool
}
```

## 2. Heurística Gulosa (Greedy TOP)

### 2.1 Construção em Paralelo (Interleaved)

O entry point da CLI é **`run_parallel_fleet_top`**: todos os ônibus competem a cada rodada pela **mesma demanda residual**, e apenas o ônibus com maior prize executa um único movimento.

```
┌─────────────────────────────────────────────────────────────────┐
│                 COORDENAÇÃO PARALELA DA FROTA                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Rodada N:                                                      │
│  ┌────────────┐ ┌────────────┐ ┌────────────┐                   │
│  │ Ônibus 1   │ │ Ônibus 2   │ │ Ônibus 3   │                   │
│  │  → candidatos│  → candidatos│  → candidatos│                  │
│  └─────┬──────┘ └─────┬──────┘ └─────┬──────┘                   │
│        └──────────────┼──────────────┘                          │
│                       ▼                                         │
│             maior prize vence a rodada                          │
│             └─► 1 único movimento (lock ou inserção)            │
│                 └─► commita demanda daquele movimento            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Regras:**
- **Sem destino ainda (lock)**: o ônibus é avaliado por uma **rota gulosa completa** (`run_greedy_top`). No modo com destino (lista `--destinations` informada), roda **uma rota por destino permitido**; no **modo livre** (sem destinos), roda uma única rota a partir da origem e o **terminal é a última parada** que a heurística escolheu. A rodada é vencida pelo melhor prize; ao vencer, o ônibus **trava** o destino (ou terminal) e **commita a rota gulosa completa avaliada** — toda a demanda que ela serve sai do pool, mantendo o residual coerente com o score.
- **Com destino travado (inserção)**: o ônibus propõe a melhor inserção de uma única parada via `rank_candidates`, usando a demanda residual para passageiros servidos e a demanda cheia para pico.
- **Desempate**: prize, depois passageiros servidos, depois menor tempo, depois índice do ônibus, depois rótulo do destino (tudo determinístico, sem RNG).
- **Parada global**: quando a demanda residual fica vazia (`edge_demand` vazio), o loop termina.
- Ônibus que nunca travam destino **ou cuja rota não atende ninguém** (zero passageiros) são omitidos do resultado final (aplicado também no mode `sequential`).

### 2.2 Algoritmo `run_greedy_top`

```python
def run_greedy_top(graph, demand_state, bus, origin, destination, time_limit):
    route_stops = (origin, destination)  # Rota inicial
    
    while True:
        # 1. Encontrar candidatos viáveis
        candidates = candidate_labels_for_demand(demand_state, route_stops)
        
        if not candidates:
            break
        
        # 2. Ranquear cada candidato
        ranking = rank_candidates(
            graph, demand_state, bus, route_stops,
            time_limit, candidate_labels=candidates
        )
        
        # 3. Selecionar melhor factível
        chosen = judge_competing_candidates(ranking, require_feasible=True)
        
        if chosen is None:
            break
        
        # 4. Inserir candidato e commitar demanda
        demand_state = commit_served_demand(demand_state, chosen.served_pairs)
        route_stops = chosen.route_stops  # Rota atualizada
    
    return route_stops
```

### 2.3 Avaliação de Candidato

Para cada candidato, avaliamos **todas as posições de inserção** possíveis:

```
Rota atual: [1, 3, 20]
Candidato: 7

Inserções possíveis:
  [1, 7, 3, 20]  ──► Simular ──► Prize 1
  [1, 3, 7, 20]  ──► Simular ──► Prize 2
  
Melhor posição = max(Prize 1, Prize 2)
```

#### Função `evaluate_candidate`:
```python
def evaluate_candidate(graph, demand_state, bus, route_stops, candidate, time_limit):
    evaluations = []
    
    for position in range(1, len(route_stops)):
        # Inserir candidato na posição
        inserted_route = insert(route_stops, candidate, position)
        
        # Simular rota completa
        simulation = simulate_route(graph, demand_state, inserted_route)
        
        # Verificar factibilidade
        feasible = judge_route(simulation, bus, time_limit)
        
        # Calcular prize (métrica controlada por --score)
        prize = prize_for(simulation, score_metric, alpha=1.0)
        
        evaluations.append({
            'route': inserted_route,
            'simulation': simulation,
            'feasible': feasible,
            'prize': prize
        })
    
    return best(evaluations)
```

### 2.4 Cálculo do Prize

O prize é a métrica de qualidade de uma inserção, controlada por `--score`:

```
density (padrão):   prize = served_passengers / travel_time_minutes   (pax por minuto)
pax_minus_time:     prize = served_passengers - α × travel_time_minutes

Onde:
  - served_passengers: passageiros atendidos pela rota simulada
  - travel_time_minutes: tempo total da rota simulada
  - α: peso do tempo (padrão: 1.0; só usado em pax_minus_time)

Guardas do density: retorna 0.0 quando não há passageiros atendidos ou tempo <= 0.
```

**Exemplo (`density`):**
```
Inserção A: 10 passageiros, 60 minutos → 10/60 = 0.17 pax/min
Inserção B: 15 passageiros, 45 minutos → 15/45 = 0.33 pax/min

Melhor: Inserção B (0.33 > 0.17)
```

## 3. Simulação de Rota

### 3.1 Processo de Simulação

```python
def simulate_route(graph, demand_state, route_stops):
    # 1. Validar arestas
    edges = []
    for source, dest in zip(route_stops, route_stops[1:]):
        edge = find_edge(graph, source, dest)
        if edge is None:
            return invalid_route(missing_edges=True)
        edges.append(edge)
    
    # 2. Calcular distâncias e tempos
    total_distance = sum(e.distance_km for e in edges)
    total_time = sum(e.travel_time_minutes for e in edges)
    
    # 3. Simular embarque/desembarque
    onboard = {}
    peak_load = 0
    
    for stop in route_stops:
        # DESMBARQUE PRIMEIRO
        onboard.pop(stop, None)
        
        # Depois EMBARQUE
        for destination, qty in demand_by_origin[stop]:
            if destination > current_position:
                onboard[destination] += qty
        
        # Atualizar pico
        peak_load = max(peak_load, sum(onboard.values()))
    
    # 4. Identificar pares atendidos
    served_pairs = []
    for (origin, dest), qty in demand_state.edge_demand:
        if origin in route_stops and dest in route_stops:
            if position(origin) < position(dest):
                served_pairs.append((origin, dest, qty))
    
    return RouteSimulation(...)
```

### 3.2 Lógica Embarque/Desembarque

```
Regra: DESMBARQUE ANTES DO EMBARQUE

Parada: [3, 7, 20]
Estado onboard antes de 7: {7: 3, 20: 5}

Em 7:
  1. Desembarcar: onboard.pop(7) → onboard = {20: 5}
  2. Embarcar: adicionar passageiros com destino > 7
  
Isso evita contar passageiros que não viajam na aresta atual.
```

### 3.3 Cálculo de Custos

```python
# Custos operacionais
rate_km = diesel_price_per_liter / km_autonomy_per_liter
rate_minute = driver_hourly_rate / 60.0

fuel_cost = total_distance_km × rate_km
driver_cost = travel_time_minutes × rate_minute
total_cost = fuel_cost + driver_cost
```

**Exemplo:**
```
Distância: 45 km
Tempo: 85 minutos
Diesel: R$ 6.50/L
Autonomia: 2.5 km/L
Motorista: R$ 30.00/h

rate_km = 6.50 / 2.5 = R$ 2.60/km
rate_minute = 30.00 / 60 = R$ 0.50/min

fuel_cost = 45 × 2.60 = R$ 117.00
driver_cost = 85 × 0.50 = R$ 42.50
total_cost = R$ 159.50
```

## 4. Coordenação da Frota

### 4.1 Coordenação Paralela (novo, usado pela CLI)

```python
def run_parallel_fleet_top(graph, demand_state, buses, origin, destinations, time_limit):
    current_state = demand_state
    served_per_bus = [{} for _ in buses]

    while True:
        round_options = []

        for state in states:                       # todos os ônibus na MESMA demanda
            if state.destination is None:
                moves = _destination_lock_moves(...)   # 1 rota gulosa por destino
            else:
                moves = _locked_destination_moves(...) # 1 melhor inserção
            if moves:
                round_options.append(max(moves, key=move_sort_key))

        if not round_options:
            break

        chosen = max(round_options, key=move_sort_key)   # maior prize global
        state.atualizado; se lock: destino travado
        served = _served_pairs_map(chosen.simulation)
        served_per_bus[chosen.bus] += served        # contabiliza só o que o ônibus
        current_state = commit_served_demand(current_state, served)
        if not current_state.edge_demand:
            break

    # Relatório final usa APENAS a demanda realmente commitada por ônibus,
    # evitando contagem dupla entre ônibus.
```

- **Contagem honesta**: o relatório final refaz `simulate_route` com um `DemandState` contendo **somente** os pares que aquele ônibus commitou (`_demand_state_from_pairs`), não a demanda original — senão passageiros seriam contados múltiplas vezes.
- Bus 1→ destino 20, bus 2 → destino 30, etc. dependem dos prizes das rotas gulosas completas.

### 4.1.1 Otimização 2-opt antes do commit do destino

Quando uma trava de destino vence, a rota gulosa completa é **reordenada via 2-opt** (`improve_route_with_two_opt`) **antes** de ser commitada:

1. Para cada par de pontos de corte `(i, j)` (origem e destino fixos), gera o reverso do segmento `route[i:j]`.
2. Aceita o candidato se: `route_valid`, `tempo ≤ time_limit`, `pico ≤ capacidade` (reusa `judge_route`).
3. Critério de aceite lexicográfico `(served_passengers, -travel_time_minutes)` — **aceita crescer o tempo se atender mais passageiros**; com atendidos iguais, prefere tempo menor.
4. Repete até nenhuma troca melhorar.

Após a reordenação, `simulate_route` é refeita sobre a rota otimizada e **a demanda dessa simulação é a que será deduzida** (`commit_served_demand`) — ou seja, a dedução reflete o que a rota otimizada de fato atendeu, não a rota avaliada originalmente.

- Efeito medido (MORNING_1): `tl=120` atendeu 196/198 → **198/198** (recuperou pares bloqueados por ordem), ônibus 6 → 5, custo R$ 1191 → R$ 922.
- O 2-opt age **só sobre a rota vencedora**, na fase de commit; a competição (`move_sort_key`) continua pontuando as rotas gulosas originais.

### 4.2 Seleção Balanceada de Destinos (legado: `run_balanced_fleet_top`, movido para `fleet_legacy.py`)

> ⚠️ **Legado/deprecado**: substituído por `run_parallel_fleet_top`. Mantido em `application/orienteering/fleet_legacy.py` apenas para comparação. O CLI não o utiliza.

```python
def select_balanced_bus_plan(plans, destination_usage, rng):
    # Filtrar planos viáveis
    feasible = [p for p in plans if p.simulation.route_valid]
    
    # Encontrar menor uso de destino
    min_usage = min(destination_usage[p.destination_label] for p in feasible)
    
    # Filtrar planos com menor uso
    pool = [p for p in feasible 
            if destination_usage[p.destination_label] == min_usage]
    
    # Desempate por prize, depois alfabético
    best_prize = max(p.prize for p in pool)
    best_pool = [p for p in pool if p.prize == best_prize]
    
    return rng.choice(sorted(best_pool, key=lambda p: p.destination_label))
```

### 4.3 Exemplo de Balanceamento (legado)

```
Destinos disponíveis: [10, 20, 30]
Uso atual: {10: 0, 20: 0, 30: 0}

Ônibus 1: Todos com uso 0
  → Escolhe destino com melhor prize (ex: 20)
  → Uso atualiza: {10: 0, 20: 1, 30: 0}

Ônibus 2: Menor uso é 10 e 30
  → Escolhe entre 10 e 30 (melhor prize)
  → Se empate, escolhe alfabeticamente (10)
  → Uso atualiza: {10: 1, 20: 1, 30: 0}

Ônibus 3: Menor uso é 30
  → Escolhe 30
  → Uso final: {10: 1, 20: 1, 30: 1}
```

### 4.4 Validação de Capacidade

```python
def select_balanced_bus_plan(plans, ...):
    feasible = [
        plan for plan in plans
        if plan.simulation.route_valid
        and plan.simulation.peak_load <= plan.bus.passenger_capacity  # ← capacidade
    ]
```

Se `peak_load > capacidade`, o plano é descartado como inviável.

## 5. Commit de Demanda

### 5.1 Processo

```python
def commit_served_demand(demand_state, served_pairs):
    new_edge_demand = demand_state.edge_demand.copy()
    
    for (origin, destination), quantity in served_pairs.items():
        if (origin, destination) in new_edge_demand:
            new_edge_demand[(origin, destination)] -= quantity
    
    return DemandState(edge_demand=new_edge_demand)
```

### 5.2 Fluxo entre Ônibus

```
Estado inicial:
  edge_demand = {("7","44"): 5, ("9","10"): 3, ("10","20"): 4}

Ônibus 1 atende: [("7","44"): 3, ("9","10"): 2]
  → DemandState residual:
    edge_demand = {("7","44"): 2, ("9","10"): 1, ("10","20"): 4}

Ônibus 2 atende: [("10","20"): 4, ("7","44"): 1]
  → DemandState residual:
    edge_demand = {("7","44"): 1, ("9","10"): 1}

Ônibus 3 atende: [("7","44"): 1, ("9","10"): 1]
  → DemandState residual:
    edge_demand = {} (esvaziou)
```

## 6. Validação de Factibilidade

### 6.1 Critérios

```python
def judge_route(simulation, bus, time_limit):
    # 1. Rota deve ter arestas válidas
    if not simulation.route_valid:
        return False
    
    # 2. Tempo não pode exceder limite
    if simulation.travel_time_minutes > time_limit:
        return False
    
    # 3. Pico de passageiros não pode exceder capacidade
    if simulation.peak_load > bus.passenger_capacity:
        return False
    
    # 4. Não pode ter passageiros sem desembarque
    if simulation.leftover_onboard_passengers > 0:
        return False
    
    return True
```

### 6.2 Ordem de Verificação

```
1. route_valid → arestas existem no grafo?
2. travel_time_minutes ≤ time_limit?
3. peak_load ≤ capacidade do ônibus?
4. leftover_onboard_passengers = 0?
```

## 7. Fluxo Completo de Execução

```
┌─────────────────────────────────────────────────────────────────┐
│                    EXECUÇÃO PRINCIPAL                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  1. main_orienteering.py                                        │
│     ├── Ler graph.json, fleet.json                              │
│     ├── Criar Graph, Buses, DemandState                         │
│     └── Chamar run_parallel_fleet_top()                         │
│                                                                 │
│  2. fleet.py: run_parallel_fleet_top()                          │
│     ├── Rodadas: todos os ônibus na mesma demanda residual      │
│     │   ├── sem destino: rota gulosa completa p/ cada destino   │
│     │   ├── com destino: melhor inserção única (rank_candidates)│
│     │   ├── vencedor: max(move_sort_key) — 1 único movimento   │
│     │   └── commit daquele movimento; para se demanda vazia     │
│     └── Relatório com demanda commitada por ônibus (sem dupla)  │
│                                                                 │
│  3. report.py                                                   │
│     ├── fleet_result_rows() → tabela markdown                   │
│     ├── fleet_summary_row() → linha Σ                           │
│     └── render_routes_section() → descrição das rotas           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

## 8. Exemplo de Saída

```markdown
| id do ônibus | destino | pasageiros atendidos | pico | custo (R$) | tempo | distancia | viável |
|--------------|---------|---------------------|------|------------|-------|-----------|--------|
| 1            | 20      | 50                  | 30   | 158.90     | 85    | 44.77     | True   |
| 2            | 30      | 10                  | 9    | 145.66     | 88    | 39.10     | True   |
| 3            | 20      | 4                   | 4    | 152.82     | 81    | 43.20     | True   |
| Σ            |         | 64                  | 30   | 457.38     | 254   | 127.07    |        |

**Ônibus 1 (20):** 1 → 2 → 10 → 3 → 43 → 7 → 25 → 19 → ... → 20
**Ônibus 2 (30):** 1 → 41 → 16 → 10 → 3 → 13 → ... → 30
**Ônibus 3 (20):** 1 → 41 → 16 → 10 → 3 → 19 → 7 → ... → 20
```

A soma dos passageiros nunca excede a demanda total do turno: cada ônibus
reporta apenas o que de fato commitou à demanda residual.

## 9. Complexidade Computacional

### Por Iteração
- **Candidatos**: C × I × S
  - C = número de candidatos
  - I = posições de inserção (Tamanho da rota)
  - S = simulação O(T) onde T = tamanho da rota

### Total
- **B × (C × I × S) × K**
  - B = número de ônibus
  - K = itérios médios por ônibus

### Otimizações
1. **Filtro de candidatos**: Apenas nós com demanda residual são avaliados
2. **Poda por factibilidade**: Rotas inviáveis são descartadas cedo
3. **Seleção gulosa**: Não há backtracking, apenas melhor candidato

## 10. Parâmetros de Configuração

| Parâmetro | Descrição | Padrão |
|-----------|-----------|--------|
| `alpha` | Peso do tempo no prize (só `score=pax_minus_time`) | 1.0 |
| `time_limit_minutes` | Limite de tempo por ônibus | 90 |
| `destination_labels` | Destinos finais permitidos (`--destinations`); vazio = modo livre (terminal = última parada da heurística) | — |
| `--score` | `density` (pax/min) ou `pax_minus_time` (served − α·time) | `density` |
| `--mode` | `parallel` (competição por rodada) ou `sequential` (balanceada legada) | `parallel` |
| `--two-opt` / `--no-two-opt` | Liga/desliga o 2-opt no commit da rota (qualquer modo) | `on` |
| `--seed` | Semente RNG (só `--mode sequential`) | 0 |
| `diesel_price_per_liter` | Preço do diesel (R$/L) — só custo | 0.0 |
| `driver_hourly_rate` | Custo do motorista (R$/h) — só custo | 0.0 |

Exemplo não-interativo de comparação:

```bash
# Com destino (constrendo terminais aos nós 10/20/30)
python3 main_orienteering.py --origin 1 --destinations "10 20 30" --shift MORNING_1 \
  --time-limit 120 --diesel-price 6.5 --driver-rate 30 --mode parallel --two-opt

# Modo livre (a heurística decide o terminal)
python3 main_orienteering.py --origin 1 --destinations "" --shift MORNING_1 \
  --time-limit 120 --diesel-price 6.5 --driver-rate 30 --mode parallel --two-opt

# Métrica de prize alternativa
python3 main_orienteering.py --origin 1 --destinations "10 20 30" --shift MORNING_1 \
  --time-limit 120 --diesel-price 6.5 --driver-rate 30 --mode parallel --two-opt --score pax_minus_time
```

Resultados de referência (MORNING_1, tl=120): parallel `density` 2-opt **198** (R$ 829) · parallel `density` livre 2-opt **198** (R$ 753) · parallel `pax_minus_time` 2-opt 198 (R$ 922) · parallel sem 2-opt (pax_minus_time) 196 (R$ 1 191).

> A CLI oferece um **menu seletivo interativo** no terminal para ativar/desativar as opções (origem, destinos [livre/constrangido], turno, limites, modo, 2-opt, score); rodar sem flags abre esse menu. As flags permanecem como atalho não-interativo para scripts.
