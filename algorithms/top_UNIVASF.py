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

import itertools
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from entities.bus import Bus
from utils.instances import InstanceData, load_instance_data
from utils.scenarios import parse_node_labels

#: One served OD pair: (origin, destination, passengers).
ServedPair = tuple[int, int, int]
#: A route as node ids in visit order; nodes may repeat (dobradinha).
StopSequence = tuple[int, ...]
#: What two proposals fight over: ("point", node) or ("od", origin, destination).
ConflictKey = tuple[str, int] | tuple[str, int, int]


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


@dataclass(frozen=True)
class BusPlan:
    """Resultado de um ônibus: rota final + o que ela atendeu."""

    bus_id: int
    stops: StopSequence
    served_passengers: int
    travel_time_minutes: int
    peak_load: int
    score: float
    served_pairs: tuple[ServedPair, ...] = ()
    origin: int | None = None  # par travado: esta origem (None = livre)
    destination: int | None = None  # par travado: este destino (None = livre)


@dataclass(frozen=True)
class FleetSummary:
    """O que aconteceu na frota: rodadas, vitórias por ônibus e sobra."""

    rounds: int
    wins_per_bus: tuple[tuple[int, int], ...]  # (bus_id, commits)
    unserved_passengers: int
    unserved_pairs: tuple[ServedPair, ...]  # (o, d, q) por qtd desc


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


@dataclass(frozen=True, slots=True)
class BoardingOutcome:
    """What a candidate route would actually carry.

    `passengers` counts only the demand boarded now; `claimed` demand the
    bus already holds occupies seats but is never counted again.
    """

    passengers: int
    travel_minutes: int
    peak_load: int
    pairs: tuple[ServedPair, ...]


def simulate_stops(
    data: InstanceData,
    stops: StopSequence,
    capacity: int,
    remaining: np.ndarray,
    claimed: dict[tuple[int, int], int] | None = None,
) -> BoardingOutcome:
    """Simula uma sequência de paradas. Retorna (pax, tempo, pico, pares).

    Embarque com restrição de capacidade, na ordem da rota. `claimed`
    (demanda já internalizada pelo ônibus) ocupa assentos mas nunca é
    recontada nos pares retornados. Cada embarque abate uma cópia local da
    demanda, então um par nunca embarca duas vezes (rota com nó repetido)
    além do que existe — `remaining` nunca é alterada.
    """
    stops = tuple(stops)
    travel = sum(int(data.time[a, b]) for a, b in itertools.pairwise(stops))
    position = {node: i for i, node in enumerate(stops)}
    n_legs = max(0, len(stops) - 1)
    leg_loads = [0] * n_legs

    first_index: dict[int, int] = {}
    last_index: dict[int, int] = {}
    for idx, node in enumerate(stops):
        first_index.setdefault(node, idx)
        last_index[node] = idx

    if claimed:
        for (origin, destination), qty in sorted(claimed.items()):
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
            if int(remaining[origin, destination]) > 0:
                boardable.append((i, position[destination], origin, destination))
    boardable.sort(key=lambda item: (item[0], item[1]))

    left = remaining.copy()  # abate local: 2ª passagem não reembarca o mesmo par
    pairs: list[ServedPair] = []
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

    return BoardingOutcome(
        passengers=served,
        travel_minutes=travel,
        peak_load=max(leg_loads, default=0),
        pairs=tuple(pairs),
    )


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
class WorkState:
    """Estado interno: par OD travado + rota em crescimento."""

    bus: Bus
    origin: int
    destination: int
    stops: list[int]
    claimed: dict[tuple[int, int], int] = field(default_factory=dict)
    travel_time_minutes: int = 0
    peak_load: int = 0

    @property
    def served_passengers(self) -> int:
        return sum(self.claimed.values())


@dataclass(frozen=True)
class DraftProposal:
    """A bus without a locked OD pair proposes the base route of one pair.

    `stops` is already the scored stretch: [o, d] or [o, P, d]. The bus is
    born at `origin`, so there is no deadhead.
    """

    bus: Bus
    origin: int
    destination: int
    stops: StopSequence
    served_passengers: int
    travel_time_minutes: int
    score: float

    def conflict_keys(self) -> list[ConflictKey]:
        """Every point and every OD sub-pair of the base route."""
        return (
            [("point", node) for node in self.stops]
            + [
                ("od", self.stops[i], self.stops[j])
                for i in range(len(self.stops))
                for j in range(i + 1, len(self.stops))
            ]
        )

    def tie_break_key(self) -> tuple:
        """Highest score wins; then more passengers, less time, lower bus id."""
        return (
            self.score,
            self.served_passengers,
            -self.travel_time_minutes,
            -self.bus.id,
        )


@dataclass(frozen=True)
class ExpansionProposal:
    """A bus with a locked OD pair inserts one demand-driven point.

    `new_points` lists the nodes the insertion actually adds: in the
    dobradinha the repeated origin was already on the route.
    """

    state: WorkState
    stops: StopSequence
    claim: tuple[ServedPair, ...]
    new_points: tuple[int, ...]
    travel_time_minutes: int
    peak_load: int
    score: float

    def conflict_keys(self) -> list[ConflictKey]:
        """The inserted points plus every OD pair the insertion claims."""
        return (
            [("point", node) for node in self.new_points]
            + [("od", origin, destination) for origin, destination, _ in self.claim]
        )

    def tie_break_key(self) -> tuple:
        """Highest score wins; then more passengers, less time, lower bus id."""
        return (
            self.score,
            sum(quantity for _, _, quantity in self.claim),
            -self.travel_time_minutes,
            -self.state.bus.id,
        )


#: A step a bus asks to commit in one round.
Proposal = DraftProposal | ExpansionProposal


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
    bus: Bus,
    remaining: np.ndarray,
    time_limit_minutes: int,
    destinations: tuple[int, ...] | None = None,
    draft_origins: tuple[int, ...] | None = None,
    cache: dict[tuple, int] | None = None,
) -> DraftProposal | None:
    """Melhor par OD de um ônibus, já como proposta de rota base.

    Para cada par candidato (o, d) — `draft_origins`/`destinations` filtram
    as seleções possíveis — busca no grafo de demanda os pontos P com
    demanda `o→P` ou `P→d` e avalia o trecho `[o, P, d]`, além da opção
    direta `[o, d]`. Os embarques respeitam a capacidade na ordem dos
    trechos (quem desce em P libera assento) e o score é
    `servidos / (tempo[o, P] + tempo[P, d])`; vale o P de maior score. O par
    NÃO precisa ter demanda direta `o→d`. A proposta já traz a rota
    pontuada: o ônibus nasce na origem do par (sem deslocamento vazio).
    None se nada viável.
    """
    capacity = bus.passenger_capacity
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

    best: DraftProposal | None = None
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
            # Candidate stretches: the direct pair first (margin -1), then
            # every demand point P, in node order.
            options: list[tuple[int, StopSequence, int]] = [(-1, (o, d), direct_time)]
            for p in sorted(points):
                first_leg, second_leg = int(time[o, p]), int(time[p, d])
                if first_leg < 0 or second_leg < 0:
                    continue
                options.append((p, (o, p, d), first_leg + second_leg))
            for margin, stops, pair_time in options:
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
                # e, por fim, o P avaliado primeiro (o direto perde).
                key = (score, served, -pair_time, -o, -d, -margin)
                if best_key is None or key > best_key:
                    best_key = key
                    best = DraftProposal(
                        bus=bus,
                        origin=o,
                        destination=d,
                        stops=stops,
                        served_passengers=served,
                        travel_time_minutes=pair_time,
                        score=score,
                    )
    return best


def _best_demand_driven_insertion(
    data: InstanceData,
    state: WorkState,
    remaining: np.ndarray,
    time_limit_minutes: int,
) -> ExpansionProposal | None:
    """Passo guiado pela demanda: a posição do ponto novo vem do par.

    Para cada ponto fora da rota: se chega demanda `A→B` com `A` na rota,
    testa `B` logo depois de `A` (se `A` é o destino final, faz a cruzada
    [..., d, B, d]); se sai demanda `B→Y` com `Y` na rota, testa `B` logo
    antes de `Y` — e, quando `Y` é a partida `o` (posição fixa), testa a
    dobradinha `[o, B, o, ...]`, exceto se `o == d` (aí o fim da rota já é
    o próprio `o` e o caso do destino final cobre). Cada trial é simulada
    inteira (capacidade por trecho, quem desce libera assento) e vale o
    score marginal (ganho de pax / minutos extras). Devolve a melhor
    proposta de expansão, ou None.
    """
    capacity = state.bus.passenger_capacity
    stops = state.stops
    last = len(stops) - 1
    current = simulate_stops(data, stops, capacity, remaining, state.claimed)
    current_qty = {(origin, destination): qty for origin, destination, qty in current.pairs}
    best: ExpansionProposal | None = None
    best_key: tuple | None = None

    def consider(candidate: int, trial: list[int]) -> None:
        nonlocal best, best_key
        outcome = simulate_stops(data, trial, capacity, remaining, state.claimed)
        if outcome.travel_minutes > time_limit_minutes or outcome.peak_load > capacity:
            return
        score = marginal_pax_per_min(
            outcome.passengers - current.passengers,
            outcome.travel_minutes - current.travel_minutes,
        )
        if score <= 0:
            return
        claim = tuple(
            sorted(
                (origin, destination, qty - current_qty.get((origin, destination), 0))
                for origin, destination, qty in outcome.pairs
                if qty > current_qty.get((origin, destination), 0)
            )
        )
        if not claim:
            return
        key = (score, outcome.passengers, -outcome.travel_minutes, -candidate, tuple(trial))
        if best_key is None or key > best_key:
            known = set(stops)
            best_key = key
            best = ExpansionProposal(
                state=state,
                stops=tuple(trial),
                claim=claim,
                new_points=tuple(dict.fromkeys(n for n in trial if n not in known)),
                travel_time_minutes=outcome.travel_minutes,
                peak_load=outcome.peak_load,
                score=score,
            )

    for candidate in candidate_nodes(remaining, stops):
        for index, stop in enumerate(stops):  # chega A→cand: cand logo depois de A
            if int(remaining[stop, candidate]) <= 0:
                continue
            if index == last:  # A é o destino final: cruzada [..., d, cand, d]
                consider(candidate, stops + [candidate, stops[-1]])
            else:
                consider(candidate, stops[:index + 1] + [candidate] + stops[index + 1:])
        for index, stop in enumerate(stops):  # sai cand→Y: cand logo antes de Y
            if int(remaining[candidate, stop]) <= 0:
                continue
            if index == 0:  # Y é a partida: dobradinha [o, cand, o, ...]
                if stops[0] == stops[-1]:  # o == d: o fim já é o o
                    continue
                consider(candidate, stops[:1] + [candidate] + stops[:1] + stops[1:])
            else:
                consider(candidate, stops[:index] + [candidate] + stops[index:])
    return best


def run_fleet(
    data: InstanceData,
    buses: list[Bus],
    time_limit_minutes: int,
    *,
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
    Tudo abate da demanda global. A rota nasce na origem do par: não há
    deslocamento vazio e a origem do cenário não é usada como posição fixa.
    """
    if not buses:
        return [], _fleet_summary(data.demand.copy(), {}, 0)
    ids = [bus.id for bus in buses]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate bus ids in fleet: {sorted(ids)}")
    remaining = data.demand.copy()
    wins: dict[int, int] = {}
    rounds = 0

    state_by_id: dict[int, WorkState] = {}

    while int(remaining.sum()) > 0:
        if max_rounds is not None and rounds >= max_rounds:
            break
        proposals = _collect_proposals(
            data,
            buses,
            state_by_id,
            remaining,
            time_limit_minutes,
            destinations=destinations,
            draft_origins=draft_origins,
        )
        if not proposals:
            break

        winners = [
            max(group, key=lambda index: proposals[index].tie_break_key())
            for group in _conflict_groups(
                [proposal.conflict_keys() for proposal in proposals]
            )
        ]
        committed = 0
        for index in sorted(winners):
            proposal = proposals[index]
            if isinstance(proposal, DraftProposal):
                # A rota base já é [o, P, d]: abate exatamente o que ela
                # embarca com trava de capacidade (caronas incluídas).
                outcome = simulate_stops(
                    data, proposal.stops, proposal.bus.passenger_capacity, remaining
                )
                claimed: dict[tuple[int, int], int] = {}
                for origin, destination, quantity in outcome.pairs:
                    claimed[(origin, destination)] = (
                        claimed.get((origin, destination), 0) + quantity
                    )
                    remaining[origin, destination] = max(
                        0, int(remaining[origin, destination]) - quantity
                    )
                state_by_id[proposal.bus.id] = WorkState(
                    bus=proposal.bus,
                    origin=proposal.origin,
                    destination=proposal.destination,
                    stops=list(proposal.stops),
                    claimed=claimed,
                    travel_time_minutes=proposal.travel_time_minutes,
                    peak_load=outcome.peak_load,
                )
                wins[proposal.bus.id] = wins.get(proposal.bus.id, 0) + 1
            else:
                state = proposal.state
                state.stops = list(proposal.stops)
                state.travel_time_minutes = proposal.travel_time_minutes
                state.peak_load = proposal.peak_load
                for origin, destination, quantity in proposal.claim:
                    state.claimed[(origin, destination)] = (
                        state.claimed.get((origin, destination), 0) + quantity
                    )
                    remaining[origin, destination] = max(
                        0, int(remaining[origin, destination]) - quantity
                    )
                wins[state.bus.id] = wins.get(state.bus.id, 0) + 1
            rounds += 1
            committed += 1
        if committed == 0:
            break

    return _build_plans(buses, state_by_id), _fleet_summary(remaining, wins, rounds)


def _collect_proposals(
    data: InstanceData,
    buses: list[Bus],
    state_by_id: dict[int, WorkState],
    remaining: np.ndarray,
    time_limit_minutes: int,
    *,
    destinations: tuple[int, ...] | None = None,
    draft_origins: tuple[int, ...] | None = None,
) -> list[Proposal]:
    """Todo ônibus propõe um passo sobre a MESMA foto de `remaining`.

    Ônibus sem par travado propõe a rota base do par; com par travado,
    propõe a inserção guiada pela demanda. Ninguém abate demanda aqui.
    """
    proposals: list[Proposal] = []
    draft_cache: dict[tuple, int] = {}
    for bus in buses:
        state = state_by_id.get(bus.id)
        if state is None:
            draft = best_pair_for_bus(
                data,
                bus,
                remaining,
                time_limit_minutes,
                destinations=destinations,
                draft_origins=draft_origins,
                cache=draft_cache,
            )
            if draft is not None:
                proposals.append(draft)
        elif state.travel_time_minutes < time_limit_minutes:
            expansion = _best_demand_driven_insertion(
                data, state, remaining, time_limit_minutes
            )
            if expansion is not None:
                proposals.append(expansion)
    return proposals


def _build_plans(
    buses: list[Bus], state_by_id: dict[int, WorkState]
) -> list[BusPlan]:
    """Um plano por ônibus que atendeu alguém, em ordem de id.

    O draft de score 0 que nunca pegou carona vira estado com pax 0 e é
    descartado: plano é o que de fato atendeu passageiro.
    """
    plans = [
        BusPlan(
            bus_id=state.bus.id,
            stops=tuple(state.stops),
            served_passengers=state.served_passengers,
            travel_time_minutes=state.travel_time_minutes,
            peak_load=state.peak_load,
            score=pax_per_min(state.served_passengers, state.travel_time_minutes),
            served_pairs=tuple(
                (origin, destination, quantity)
                for (origin, destination), quantity in sorted(state.claimed.items())
                if quantity > 0
            ),
            destination=state.destination,
            origin=state.origin,
        )
        for state in (state_by_id[bus.id] for bus in buses if bus.id in state_by_id)
        if state.served_passengers > 0
    ]
    plans.sort(key=lambda plan: plan.bus_id)
    return plans


def solve_scenario(
    scenario: dict,
    buses: list[Bus],
    root: str | Path,
    *,
    origin: int | None = None,
) -> tuple[InstanceData, list[BusPlan], FleetSummary]:
    """Pipeline completo: carrega instância e resolve a frota.

    As origens permitidas do draft vêm da coluna ``origin`` do cenário
    (vazio = livre); o parâmetro `origin` sobrescreve o cenário e força uma
    única origem permitida, para experimentos.
    """
    data = load_instance_data(
        Path(root) / "instances" / scenario["instance_id"], period=scenario["period"]
    )
    draft_origins = parse_node_labels(scenario.get("origin"))
    if origin is not None:
        draft_origins = (origin,)
    plans, summary = run_fleet(
        data,
        buses,
        int(scenario["max_time_limit"]),
        destinations=parse_node_labels(scenario.get("destination_labels")),
        draft_origins=draft_origins,
    )
    return data, plans, summary
