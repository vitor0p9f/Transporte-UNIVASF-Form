"""The three scores the heuristic orders its decisions by."""


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
