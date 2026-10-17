"""UNIVASF TOP heuristic: greedy sequencial com trava no par OD.

Etapa 1 (draft do par): cada ônibus ainda sem par varre as seleções
possíveis (origem, destino) e, para cada par, busca no grafo de demanda
os pontos P com demanda vindo de `o` OU indo para `d`, avaliando o
trecho [o, P, d] (mais a opção direta [o, d]):
    servível = embarques do trecho com trava de capacidade
               (o→P desembarca, então embarca P→d, mais o o→d no caminho)
    score = servível / (tempo[o, P] + tempo[P, d])
Vale o P de maior score. O par NÃO precisa ter demanda direta `o→d`. O
maior score global trava a rota base [o, P, d] primeiro (o ônibus nasce
na origem do par — não há deslocamento vazio) e abate da demanda o que o
trecho embarcou. Os demais repetem sobre a demanda atualizada.

Etapa 2 (rodadas globais): a cada rodada, cada ônibus com par travado
(o, d) propõe um passo guiado pela demanda — ponto novo entra onde o par
manda: `A→B` põe `B` depois de `A` (se `A` é o destino final, cruzada
[..., d, B, d]); `B→Y` põe `B` antes de `Y` (início fixo); em conflito de
ponto ou par, sempre o maior score marginal committa e assume a demanda;
os demais replanejam na rodada seguinte, até estourar tempo/capacidade
ou zerar o score.

`destinations`/`draft_origins` (quando dados) filtram as seleções
possíveis de destino/origem do par.
"""

from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from entities.bus import Bus
from utils.demand import load_demand_matrix
from utils.matrices import load_square_matrix


def pax_per_min(served_passengers: int, travel_time_minutes: int) -> float:
    """Passageiros por minuto. Rota vazia ou sem tempo → 0.0."""
    if served_passengers <= 0 or travel_time_minutes <= 0:
        return 0.0
    return served_passengers / travel_time_minutes


def od_pair_score(servable_passengers: int, pair_time_minutes: int) -> float:
    """Score do par OD: servível / tempo do trecho do par. Sem pax ou sem tempo → 0.0.

    `servable_passengers` são os embarques do trecho [o, P, d] com trava de
    capacidade; `pair_time_minutes` é tempo[o, P] + tempo[P, d] (ou tempo[o, d]
    na opção direta).
    """
    if servable_passengers <= 0 or pair_time_minutes <= 0:
        return 0.0
    return servable_passengers / pair_time_minutes


def marginal_pax_per_min(delta_passengers: int, delta_time_minutes: int) -> float:
    """Pax/min do GANHO de inserir uma parada (ordena a etapa 2)."""
    if delta_passengers <= 0:
        return 0.0
    if delta_time_minutes <= 0:
        return float("inf")
    return delta_passengers / delta_time_minutes


@dataclass
class InstanceData:
    """Matrices of one instance, indexed directly by node id."""

    nodes: list[int]
    distance: np.ndarray
    time: np.ndarray
    demand: np.ndarray


def load_instance_data(instance_dir: str | Path, period: str) -> InstanceData:
    """Load distance, time and demand matrices for one instance/period."""
    instance_dir = Path(instance_dir)
    nodes, distance = load_square_matrix(instance_dir / "distance.csv")
    _, time = load_square_matrix(instance_dir / "time.csv", dtype=int)
    _, demand = load_demand_matrix(instance_dir / "demand.csv", period=period)
    return InstanceData(nodes=nodes, distance=distance, time=time, demand=demand)


def run(scenario: dict, buses: list[Bus], root: str | Path) -> InstanceData:
    """Load everything the greedy heuristics need for one scenario."""
    instance_dir = Path(root) / "instances" / scenario["instance_id"]
    return load_instance_data(instance_dir, period=scenario["period"])


@dataclass(frozen=True)
class BusPlan:
    """Resultado de um ônibus: rota final + o que ela atendeu."""

    bus_id: int
    stops: tuple[int, ...]
    served_passengers: int
    travel_time_minutes: int
    peak_load: int
    score: float
    served_pairs: tuple[tuple[int, int, int], ...] = ()
    origin: int | None = None  # par travado: esta origem (None = livre)
    destination: int | None = None  # par travado: este destino (None = livre)


def parse_destination_labels(value: object) -> tuple[int, ...] | None:
    """Parse '44;45;43' em tupla de destinos. Vazio/None → None (terminal livre)."""
    if value is None:
        return None
    ids = [v.strip() for v in str(value).split(";") if v.strip()]
    return tuple(int(v) for v in ids) or None


def parse_origin_labels(value: object) -> tuple[int, ...] | None:
    """Parse '43;44;45' em tupla de origens. Vazio/None → None (origem livre)."""
    if value is None:
        return None
    ids = [v.strip() for v in str(value).split(";") if v.strip()]
    return tuple(int(v) for v in ids) or None


@dataclass(frozen=True)
class FleetSummary:
    """O que aconteceu na frota: rodadas, vitórias por ônibus e sobra."""

    rounds: int
    wins_per_bus: tuple[tuple[int, int], ...]  # (bus_id, commits)
    unserved_passengers: int
    unserved_pairs: tuple[tuple[int, int, int], ...]  # (o, d, q) por qtd desc


def _fleet_summary(
    remaining: np.ndarray,
    wins: dict[int, int],
    rounds: int,
) -> FleetSummary:
    pairs = sorted(
        (
            (int(origin), int(destination), int(qty))
            for (origin, destination), qty in np.ndenumerate(remaining)
            if qty > 0
        ),
        key=lambda item: (-item[2], item[0], item[1]),
    )
    return FleetSummary(
        rounds=rounds,
        wins_per_bus=tuple(sorted(wins.items())),
        unserved_passengers=int(remaining.sum()),
        unserved_pairs=tuple(pairs),
    )


def simulate_stops(
    data: InstanceData,
    stops: list[int] | tuple[int, ...],
    capacity: int,
    demand: np.ndarray,
    background: dict[tuple[int, int], int] | None = None,
) -> tuple[int, int, int, list[tuple[int, int, int]]]:
    """Simula uma sequência de paradas. Retorna (pax, tempo, pico, pares).

    Embarque com restrição de capacidade, na ordem da rota. `background`
    (demanda já internalizada pelo ônibus) ocupa assentos mas nunca é
    recontada nos pares retornados. Cada embarque abate uma cópia local da
    demanda, então um par nunca embarca duas vezes (rota com nó repetido)
    além do que existe — `demand` nunca é alterada.
    """
    stops = tuple(stops)
    travel = sum(int(data.time[a, b]) for a, b in zip(stops, stops[1:]))
    position = {node: i for i, node in enumerate(stops)}
    n_legs = max(0, len(stops) - 1)
    leg_loads = [0] * n_legs

    first_index: dict[str | int, int] = {}
    last_index: dict[str | int, int] = {}
    for idx, node in enumerate(stops):
        first_index.setdefault(node, idx)
        last_index[node] = idx

    if background:
        for (origin, destination), qty in sorted(background.items()):
            if qty <= 0 or origin == destination:
                continue
            i = first_index.get(origin, -1)
            j = last_index.get(destination, -1)
            if i < 0 or j < 0 or i >= j:
                continue
            for leg in range(i, j):
                leg_loads[leg] += qty

    boardable: list[tuple[int, int, int, int]] = []
    for i, origin in enumerate(stops):
        for destination in stops[i + 1:]:
            if int(demand[origin, destination]) > 0:
                boardable.append((i, position[destination], origin, destination))
    boardable.sort(key=lambda item: (item[0], item[1]))

    left = demand.copy()  # abate local: 2ª passagem não reembarca o mesmo par
    pairs: list[tuple[int, int, int]] = []
    served = 0
    for origin_idx, dest_idx, origin, destination in boardable:
        qty = int(left[origin, destination])
        if qty <= 0:
            continue
        peak_in_range = max(leg_loads[origin_idx:dest_idx], default=0)
        boarded = min(qty, max(0, capacity - peak_in_range))
        if boarded <= 0:
            continue
        for leg in range(origin_idx, dest_idx):
            leg_loads[leg] += boarded
        left[origin, destination] -= boarded
        pairs.append((origin, destination, boarded))
        served += boarded

    return served, travel, max(leg_loads, default=0), pairs


def candidate_nodes(demand: np.ndarray, stops: list[int]) -> list[int]:
    """Nós com demanda (embarque ou desembarque) ainda fora da rota."""
    blocked = set(stops)
    candidates: set[int] = set()
    for origin, destination in zip(*np.nonzero(demand)):
        if int(origin) not in blocked:
            candidates.add(int(origin))
        if int(destination) not in blocked:
            candidates.add(int(destination))
    return sorted(candidates)


@dataclass
class _BusWorkState:
    """Estado interno: par OD travado + rota em crescimento."""

    bus: Bus
    locked_o: int
    locked_d: int
    stops: list[int]
    held: dict[tuple[int, int], int] = field(default_factory=dict)
    travel_time_minutes: int = 0
    peak_load: int = 0

    @property
    def served_passengers(self) -> int:
        return sum(self.held.values())


def _conflict_groups(key_lists: list[list[tuple]]) -> list[list[int]]:
    """Agrupa índices que compartilham alguma chave (união por transitividade).

    Propostas sem chave em comum comitam juntas na mesma rodada; de cada
    grupo em conflito, só a de maior score age.
    """
    parent = list(range(len(key_lists)))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    owner: dict[tuple, int] = {}
    for idx, keys in enumerate(key_lists):
        for key in keys:
            if key in owner:
                a, b = find(idx), find(owner[key])
                if a != b:
                    parent[a] = b
            else:
                owner[key] = idx

    groups: dict[int, list[int]] = {}
    for idx in range(len(key_lists)):
        groups.setdefault(find(idx), []).append(idx)
    return list(groups.values())


def _stretch_passengers(
    stops: tuple[int, ...], capacity: int, remaining: np.ndarray
) -> int:
    """Embarques de um trecho curto do draft, com trava de capacidade.

    Mesma conta gulosa de `simulate_stops` (origem crescente, depois
    destino), mas sem copiar a matriz de demanda: o draft avalia milhares
    de trechos minúsculos por rodada.
    """
    n = len(stops)
    leg_loads = [0] * (n - 1)
    served = 0
    for i in range(n):
        for j in range(i + 1, n):
            qty = int(remaining[stops[i], stops[j]])
            if qty <= 0:
                continue
            room = capacity - max(leg_loads[i:j], default=0)
            if room <= 0:
                continue
            boarded = min(qty, room)
            for leg in range(i, j):
                leg_loads[leg] += boarded
            served += boarded
    return served


def best_pair_for_bus(
    data: InstanceData,
    capacity: int,
    remaining: np.ndarray,
    time_limit_minutes: int,
    destinations: tuple[int, ...] | None = None,
    draft_origins: tuple[int, ...] | None = None,
    cache: dict[tuple, int] | None = None,
) -> tuple[int, int, int, int, tuple[int, ...], float] | None:
    """Melhor par OD de um ônibus: (o, d, servidos, tempo, stops, score).

    Para cada par candidato (o, d) — `draft_origins`/`destinations` filtram
    as seleções possíveis — busca no grafo de demanda os pontos P com
    demanda `o→P` ou `P→d` e avalia o trecho `[o, P, d]`, além da opção
    direta `[o, d]`. Os embarques respeitam a capacidade na ordem dos
    trechos (quem desce em P libera assento) e o score é
    `servidos / (tempo[o, P] + tempo[P, d])`; vale o P de maior score. O par
    NÃO precisa ter demanda direta `o→d`. `stops` já é a rota pontuada: o
    ônibus nasce na origem do par (sem deslocamento vazio). None se nada
    viável.
    """
    time = data.time
    nodes = data.nodes
    if cache is None:
        cache = {}
    dest_set = set(destinations) if destinations else None
    draft_set = set(draft_origins) if draft_origins else None
    out_demand = {
        o: [p for p in nodes if p != o and int(remaining[o, p]) > 0]
        for o in nodes
    }
    in_demand = {
        d: [p for p in nodes if p != d and int(remaining[p, d]) > 0]
        for d in nodes
    }

    best: tuple[int, int, int, int, tuple[int, ...], float] | None = None
    best_key: tuple | None = None
    for o in nodes:
        if draft_set is not None and o not in draft_set:
            continue
        out_list = out_demand[o]
        for d in nodes:
            if dest_set is not None and d not in dest_set:
                continue
            if o == d and int(remaining[o, d]) > 0:
                continue  # self-loop nunca embarca
            direct_time = int(time[o, d])
            if direct_time < 0:
                continue
            points = set(out_list)
            points.update(in_demand[d])
            points.discard(o)
            points.discard(d)
            options: list[tuple[int | None, tuple[int, ...], int]] = [
                (None, (o, d), direct_time)
            ]
            for p in sorted(points):
                first_leg, second_leg = int(time[o, p]), int(time[p, d])
                if first_leg < 0 or second_leg < 0:
                    continue
                options.append((p, (o, p, d), first_leg + second_leg))
            for p, stops, pair_time in options:
                if pair_time < 0 or pair_time > time_limit_minutes:
                    continue
                key_cache = (capacity, stops)
                served = cache.get(key_cache)
                if served is None:
                    served = _stretch_passengers(stops, capacity, remaining)
                    cache[key_cache] = served
                if pair_time == 0 and served > 0:
                    continue  # sem tempo p/ servir
                score = od_pair_score(served, pair_time)
                if score < 0:
                    continue
                # Empate de score: mais pax, trecho mais curto, menor (o, d)
                # e, por fim, o P avaliado primeiro.
                key = (score, served, -pair_time, -o, -d,
                       -(p if p is not None else -1))
                if best_key is None or key > best_key:
                    best_key = key
                    best = (o, d, served, pair_time, stops, score)
    return best


def _best_demand_driven_insertion(
    data: InstanceData,
    state: _BusWorkState,
    remaining: np.ndarray,
    time_limit_minutes: int,
) -> tuple[tuple[int, ...], tuple[tuple[int, int, int], ...], int, int, float] | None:
    """Passo guiado pela demanda: a posição do ponto novo vem do par.

    Para cada ponto fora da rota: se chega demanda `A→B` com `A` na rota,
    testa `B` logo depois de `A` (se `A` é o destino final, faz a cruzada
    [..., d, B, d]); se sai demanda `B→Y` com `Y` na rota, testa `B` logo
    antes de `Y` — e, quando `Y` é a partida `o` (posição fixa), testa a
    dobradinha `[o, B, o, ...]`, exceto se `o == d` (aí o fim da rota já é
    o próprio `o` e o caso do destino final cobre). Cada trial é simulada
    inteira (capacidade por trecho, quem desce libera assento) e vale o
    score marginal (ganho de pax / minutos extras). Retorna a melhor
    (trial, claim, travel, peak, score) ou None.
    """
    capacity = state.bus.passenger_capacity
    stops = state.stops
    last = len(stops) - 1
    cur_served, cur_travel, _, cur_pairs = simulate_stops(
        data, stops, capacity, remaining, state.held
    )
    cur_qty = {(o, d): q for o, d, q in cur_pairs}
    best_trial: tuple[int, ...] | None = None
    best_claim: tuple[tuple[int, int, int], ...] = ()
    best_metrics: tuple[int, int] | None = None
    best_score = 0.0
    best_key: tuple | None = None

    def consider(cand: int, trial: list[int]) -> None:
        nonlocal best_trial, best_claim, best_metrics, best_score, best_key
        s2, t2, p2, pairs2 = simulate_stops(
            data, trial, capacity, remaining, state.held
        )
        if t2 > time_limit_minutes or p2 > capacity:
            return
        score = marginal_pax_per_min(s2 - cur_served, t2 - cur_travel)
        if score <= 0:
            return
        claim = tuple(
            sorted(
                (o, d, q - cur_qty.get((o, d), 0))
                for o, d, q in pairs2
                if q > cur_qty.get((o, d), 0)
            )
        )
        if not claim:
            return
        key = (score, s2, -t2, -cand, tuple(trial))
        if best_key is None or key > best_key:
            best_key = key
            best_trial = tuple(trial)
            best_claim = claim
            best_metrics = (t2, p2)
            best_score = score

    for cand in candidate_nodes(remaining, stops):
        for a, A in enumerate(stops):  # chega A→B: B logo depois de A
            if int(remaining[A, cand]) <= 0:
                continue
            if a == last:  # A é o destino final: cruzada [..., d, B, d]
                consider(cand, stops + [cand, stops[-1]])
            else:
                consider(cand, stops[:a + 1] + [cand] + stops[a + 1:])
        for y, Y in enumerate(stops):  # sai B→Y: B logo antes de Y
            if int(remaining[cand, Y]) <= 0:
                continue
            if y == 0:  # Y é a partida: dobradinha [o, B, o, ...]
                if stops[0] == stops[-1]:  # o == d: o fim já é o o
                    continue
                consider(cand, stops[:1] + [cand] + stops[:1] + stops[1:])
            else:
                consider(cand, stops[:y] + [cand] + stops[y:])
    if best_trial is None or best_metrics is None:
        return None
    t2, p2 = best_metrics
    return best_trial, best_claim, t2, p2, best_score

def run_fleet(
    data: InstanceData,
    buses: list[Bus],
    origin: int,
    time_limit_minutes: int,
    *,
    max_workers: int | None = None,
    max_rounds: int | None = None,
    destinations: tuple[int, ...] | None = None,
    draft_origins: tuple[int, ...] | None = None,
) -> tuple[list[BusPlan], FleetSummary]:
    """Loop único: todo ônibus propõe o melhor passo; sem conflito comitam
    juntos, em conflito só o maior score age.

    Sem par travado propõe a rota base do par (score = embarques do trecho
    `[o, P, d]` / tempo do trecho — ver `best_pair_for_bus`), só entre
    origens informadas (`draft_origins`, None = livre) e destinos informados
    (`destinations`, None = livre); com par propõe o passo guiado pela
    demanda (`_best_demand_driven_insertion`).
    Tudo abate da demanda global. `max_workers` é ignorado e `origin` fica
    sem uso: a rota nasce na origem do par (sem deslocamento vazio).
    """
    _ = max_workers  # sequencial por definição: sem threads
    _ = origin  # sem deadhead: o ônibus nasce na origem do par travado
    if not buses:
        return [], _fleet_summary(data.demand.copy(), {}, 0)
    ids = [bus.id for bus in buses]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate bus ids in fleet: {sorted(ids)}")
    remaining = data.demand.copy()
    wins: dict[int, int] = {}
    rounds = 0

    bus_by_id = {bus.id: bus for bus in buses}
    state_by_id: dict[int, _BusWorkState] = {}
    locked: dict[int, tuple[int, int]] = {}

    while int(remaining.sum()) > 0:
        if max_rounds is not None and rounds >= max_rounds:
            break
        entries: list[tuple] = []
        keys: list[list[tuple]] = []
        draft_cache: dict[tuple, int] = {}
        for bus in buses:
            if bus.id not in state_by_id:
                capacity = bus.passenger_capacity
                best = best_pair_for_bus(
                    data, capacity, remaining, time_limit_minutes,
                    destinations=destinations, draft_origins=draft_origins,
                    cache=draft_cache,
                )
                if best is not None:
                    o, d, served, total, stops, score = best
                    base = list(stops)
                    entry_keys = (
                        [("point", node) for node in base]
                        + [("od", base[i], base[j])
                           for i in range(len(base)) for j in range(i + 1, len(base))]
                    )
                    entries.append(("draft", bus, o, d, served, total, tuple(base), score))
                    keys.append(entry_keys)
            else:
                state = state_by_id[bus.id]
                if state.travel_time_minutes >= time_limit_minutes:
                    continue
                found = _best_demand_driven_insertion(data, state, remaining, time_limit_minutes)
                if found is not None:
                    trial, claim, travel, peak, score = found
                    # Pontos que a inserção de fato acrescenta — o `o` da
                    # dobradinha repete um nó que já estava na rota.
                    known = set(state.stops)
                    new_points = tuple(dict.fromkeys(n for n in trial if n not in known))
                    entry_keys = (
                        [("point", node) for node in new_points]
                        + [("od", o, d) for o, d, _ in claim]
                    )
                    entries.append(("expand", state, trial, claim, travel, peak, score))
                    keys.append(entry_keys)
        if not entries:
            break

        winners = [
            max(group, key=lambda i: (
                entries[i][-1],
                entries[i][4] if entries[i][0] == "draft"
                else sum(q for _, _, q in entries[i][3]),
                -entries[i][5] if entries[i][0] == "draft" else -entries[i][4],
                -(entries[i][1].id if entries[i][0] == "draft" else entries[i][1].bus.id),
            ))
            for group in _conflict_groups(keys)
        ]
        committed = 0
        for i in sorted(winners):
            entry = entries[i]
            if entry[0] == "draft":
                _, bus, o, d, _served, total, stops, _score = entry
                # A rota base já é [o, P, d]: abate exatamente o que ela
                # embarca com trava de capacidade (caronas incluídas).
                _, _, peak, fill_pairs = simulate_stops(
                    data, list(stops), bus.passenger_capacity, remaining
                )
                held: dict[tuple[int, int], int] = {}
                for fo, fd, fq in fill_pairs:
                    held[(fo, fd)] = held.get((fo, fd), 0) + fq
                    remaining[fo, fd] = max(0, int(remaining[fo, fd]) - fq)
                rounds += 1
                committed += 1
                wins[bus.id] = wins.get(bus.id, 0) + 1
                locked[bus.id] = (o, d)
                state_by_id[bus.id] = _BusWorkState(
                    bus=bus, locked_o=o, locked_d=d, stops=list(stops),
                    held=held,
                    travel_time_minutes=total, peak_load=peak,
                )
            else:
                _, state, trial, claim, travel, peak, _score = entry
                rounds += 1
                committed += 1
                wins[state.bus.id] = wins.get(state.bus.id, 0) + 1
                state.stops = list(trial)
                state.travel_time_minutes = travel
                state.peak_load = peak
                for co, cd, qty in claim:
                    state.held[(co, cd)] = state.held.get((co, cd), 0) + qty
                    remaining[co, cd] = max(0, int(remaining[co, cd]) - qty)
        if committed == 0:
            break

    states = [state_by_id[bus.id] for bus in buses if bus.id in state_by_id]

    plans = [
        BusPlan(
            bus_id=state.bus.id,
            stops=tuple(state.stops),
            served_passengers=state.served_passengers,
            travel_time_minutes=state.travel_time_minutes,
            peak_load=state.peak_load,
            score=pax_per_min(state.served_passengers, state.travel_time_minutes),
            served_pairs=tuple(
                (o, d, q) for (o, d), q in sorted(state.held.items()) if q > 0
            ),
            destination=state.locked_d,
            origin=state.locked_o,
        )
        for state in states
        if state.served_passengers > 0
    ]
    plans.sort(key=lambda plan: plan.bus_id)
    return plans, _fleet_summary(remaining, wins, rounds)


def solve_scenario(
    scenario: dict,
    buses: list[Bus],
    root: str | Path,
    *,
    origin: int | None = None,
) -> tuple[InstanceData, list[BusPlan], FleetSummary]:
    """Pipeline completo: carrega instância e resolve a frota."""
    data = run(scenario, buses, root)
    raw_origin = scenario.get("origin") if isinstance(scenario, dict) else None
    origins = parse_origin_labels(raw_origin)
    if origin is None and origins:
        origin = origins[0]
    start = origin if origin is not None else min(data.nodes)
    if origins:
        draft_origins = origins
    elif origin is not None:
        draft_origins = (origin,)
    else:
        draft_origins = None
    raw_dest = scenario.get("destination_labels") if isinstance(scenario, dict) else None
    plans, summary = run_fleet(
        data, buses, start, int(scenario["max_time_limit"]),
        destinations=parse_destination_labels(raw_dest),
        draft_origins=draft_origins,
    )
    return data, plans, summary
