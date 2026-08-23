# Algoritmo de Construção de Rotas - Greedy TOP

## Visão Geral

O sistema implementa uma heurística **Greedy Team Orienteering Problem (TOP)** para construir rotas de ônibus que maximizam o número de passageiros atendidos dentro de limites de tempo e capacidade.

```
┌─────────────────────────────────────────────────────────────────┐
│                        FLUXO PRINCIPAL                          │
├─────────────────────────────────────────────────────────────────┤
│  1. Carregar grafo e demanda por turno                          │
│  2. Para cada ônibus (sequencialmente):                         │
│     a. Avaliar todos os destinos possíveis                      │
│     b. Construir rota gulosa para o melhor destino              │
│     c. Commitar demanda servida                                 │
│  3. Gerar relatório de resultados                               │
└─────────────────────────────────────────────────────────────────┘
```

## 1. Estrutura de Dados

### Grafo (Graph)
```
Grafo = {Nodes, Edges}

Node = {label: str}                          // Ex: "1", "10", "44"
Edge = {source: Node, destination: Node,
        distance_km: float, 
        travel_time_minutes: int}            // Direcional
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

### 2.1 Construção Sequencial

```
┌─────────────────────────────────────────────────────────────────┐
│                  COORDENAÇÃO DA FROTA                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Ônibus 1 ──────► Constrói rota completa ──────► Commita demanda│
│                                                                 │
│  Ônibus 2 ──────► Constrói rota completa ──────► Commita demanda│
│  (com demanda residual)                                         │
│                                                                 │
│  Ônibus 3 ──────► Constrói rota completa ──────► Commita demanda│
│  (com demanda residual)                                         │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**IMPORTANTE:** Cada ônibus constrói sua rota **completamente** antes do próximo. Não há iteração interleaved.

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
        
        # Calcular prize
        prize = calculate_node_prize(simulation, alpha=1.0)
        
        evaluations.append({
            'route': inserted_route,
            'simulation': simulation,
            'feasible': feasible,
            'prize': prize
        })
    
    return best(evaluations)
```

### 2.4 Cálculo do Prize

O prize é a métrica de qualidade de uma inserção:

```
prize = served_passengers - α × travel_time_minutes

Onde:
  - served_passengers: passageiros atendidos pela rota simulada
  - travel_time_minutes: tempo total da rota simulada
  - alpha: peso do tempo (padrão: 1.0)
```

**Exemplo:**
```
Inserção A: 10 passageiros, 60 minutos
  prize = 10 - 1.0 × 60 = -50

Inserção B: 15 passageiros, 45 minutos  
  prize = 15 - 1.0 × 45 = -30

Melhor: Inserção B (-30 > -50)
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

### 4.1 Seleção Balanceada de Destinos

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

### 4.2 Exemplo de Balanceamento

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

### 4.3 Validação de Capacidade

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
│     └── Chamar run_balanced_fleet_top()                         │
│                                                                 │
│  2. fleet.py: run_balanced_fleet_top()                          │
│     ├── Para cada ônibus:                                       │
│     │   ├── evaluate_destination_options()                      │
│     │   │   └── evaluate_bus_plan() × N destinos                │
│     │   │       ├── run_greedy_top() → construção gulosa        │
│     │   │       └── simulate_route() → cálculo final            │
│     │   ├── select_balanced_bus_plan()                          │
│     │   └── commit_served_demand()                              │
│     └── Retornar FleetResult                                    │
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
| 1            | 20      | 51                  | 30   | 158.90     | 85    | 44.77     | True   |
| 2            | 30      | 9                   | 9    | 136.64     | 84    | 36.40     | True   |
| 3            | 10      | 6                   | 6    | 159.98     | 87    | 44.80     | True   |
| Σ            |         | 66                  | 30   | 455.52     | 256   | 125.97    |        |

**Ônibus 1 (20):** 1 → 2 → 10 → 3 → 43 → 7 → 25 → 19 → ... → 20
**Ônibus 2 (30):** 1 → 41 → 16 → 10 → 3 → 13 → ... → 30
**Ônibus 3 (10):** 1 → 3 → 19 → 7 → 25 → 36 → ... → 10
```

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
| `alpha` | Peso do tempo no prize | 1.0 |
| `time_limit_minutes` | Limite de tempo por ônibus | 90 |
| `seed` | Semente RNG para desempate | 0 |
| `max_iterations` | Limite de iterações por ônibus | None |
| `diesel_price_per_liter` | Preço do diesel (R$/L) | 0.0 |
| `driver_hourly_rate` | Custo do motorista (R$/h) | 0.0 |
