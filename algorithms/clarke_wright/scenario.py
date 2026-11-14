"""Entrada de cenário/instância e conversão para o modelo de resultados."""

from pathlib import Path

from algorithms.top_univasf.model import BusPlan, FleetSummary
from entities.bus import Bus
from utils.fleet import load_fleet, parse_fleet_ids
from utils.instances import InstanceData, load_instance_data
from utils.scenarios import load_scenarios, parse_node_labels

from .constants import (
    CAPACIDADE_PADRAO,
    CONSUMO_PADRAO,
    DIESEL_PADRAO,
    ITER_POSTIMPROVE,
    ITER_TWO_PHASE,
    PERIODO_PADRAO,
)
from .context import montar_contexto
from .evaluation import avaliar_atendimento, limitar_frota
from .model import Atendimento, Contexto, ModeloOnibus, Rota, modelo_de_bus
from .solver import clarke_wright_ovrp

ROOT = Path(__file__).resolve().parents[2]


def _buscar_cenario(scenario_id: str) -> dict:
    for scenario in load_scenarios(ROOT):
        if str(scenario["scenario_id"]) == str(scenario_id):
            return scenario
    raise SystemExit(
        f"[erro] cenário '{scenario_id}' não encontrado em "
        "scenarios.csv / scenarios_base.csv"
    )


def _frota_do_cenario(cenario: dict | None) -> list[Bus]:
    if not cenario or not cenario.get("fleet_bus_ids"):
        return []
    return load_fleet(
        ROOT / "fleet.csv", parse_fleet_ids(cenario["fleet_bus_ids"])
    )


def _deposito_do_cenario(cenario: dict | None) -> int | None:
    if not cenario:
        return None
    origens = parse_node_labels(cenario.get("origin"))
    return origens[0] if origens else None


def modelo_de_referencia(
    cenario: dict | None, capacidade: int, diesel: float
) -> ModeloOnibus:
    """Modelo de custo único do cenário, aplicado às DUAS heurísticas.

    Escolhe o ônibus da frota com a capacidade efetiva (o critério que o CW
    sempre usou); sem correspondência, o menor da frota. Sem frota declarada,
    devolve um modelo genérico. O custo operacional dos relatórios usa este
    mesmo modelo para o TOP e para o CW, para que os valores sejam
    comparáveis.
    """
    buses = _frota_do_cenario(cenario)
    if not buses:
        return ModeloOnibus(
            nome="genérico",
            capacidade=capacidade,
            consumo_km_l=CONSUMO_PADRAO,
            custo_litro=diesel,
        )
    referencia = next(
        (b for b in buses if b.passenger_capacity == capacidade),
        min(buses, key=lambda b: b.passenger_capacity),
    )
    return modelo_de_bus(referencia, diesel)


def contexto_do_cenario(
    cenario: dict | None,
    *,
    instancia: str | None = None,
    periodo: str | None = None,
    deposito: int | None = None,
    capacidade: int | None = None,
    limite_tempo: float | None = None,
    diesel: float | None = None,
    restricoes: str = "ambas",
    sentido: str = "auto",
    max_rotas: int | None = None,
) -> tuple[InstanceData, Contexto]:
    """Resolve um cenário (instância, depósito, frota, limites) num contexto.

    Cada parâmetro explícito vence o que o cenário define; é o mesmo caminho
    que a CLI percorre, exposto para o `main.py` rodar as duas heurísticas
    com exatamente os mesmos limites.

    `max_rotas` é o teto de veículos; omitido, vale o tamanho da frota do
    cenário (None só quando não há frota declarada).
    """
    cenario = cenario or {}
    instancia = instancia or cenario.get("instance_id")
    if not instancia:
        raise ValueError("informe a instância (o cenário não define uma)")
    periodo = periodo or cenario.get("period") or PERIODO_PADRAO
    data = load_instance_data(ROOT / "instances" / instancia, period=periodo)

    if deposito is None:
        deposito = _deposito_do_cenario(cenario)
    if deposito is None:
        raise ValueError("informe o depósito (o cenário não define uma origem)")

    buses = _frota_do_cenario(cenario)
    if diesel is None:
        diesel = (
            float(cenario["diesel_price_per_liter"])
            if cenario.get("diesel_price_per_liter")
            else DIESEL_PADRAO
        )
    # Sem capacidade informada, vale a do menor ônibus da frota: assim toda
    # rota que o CW monta cabe em qualquer ônibus do cenário.
    if capacidade is None:
        capacidade = (
            min(b.passenger_capacity for b in buses)
            if buses
            else CAPACIDADE_PADRAO
        )
    modelo = modelo_de_referencia(cenario, capacidade, diesel)

    if limite_tempo is None and cenario.get("max_time_limit"):
        limite_tempo = int(cenario["max_time_limit"])

    if max_rotas is None:
        max_rotas = len(buses) or None

    ctx = montar_contexto(
        data,
        deposito,
        capacidade=capacidade,
        limite_tempo=limite_tempo,
        modelo=modelo,
        restricoes=restricoes,
        sentido=sentido,
        max_rotas=max_rotas,
    )
    return data, ctx


def resolver_cenario(
    cenario: dict,
    *,
    instancia: str | None = None,
    periodo: str | None = None,
    deposito: int | None = None,
    capacidade: int | None = None,
    limite_tempo: float | None = None,
    diesel: float | None = None,
    restricoes: str = "ambas",
    sentido: str = "auto",
    max_rotas: int | None = None,
    lam: float | None = None,
    usar_two_phase: bool = True,
    usar_postimprove: bool = True,
    iteracoes: int = ITER_TWO_PHASE,
    iter_postimprov: int = ITER_POSTIMPROVE,
    seed: int = 42,
    verbose: bool = False,
) -> tuple[InstanceData, list[Rota], Contexto, Atendimento, float]:
    """Roda o CW num cenário e devolve a solução já avaliada.

    Devolve `(data, rotas, ctx, atendimento, lambda_usado)` — é o que o
    `main.py` consome para montar a linha do CW na tabela comparativa.
    """
    data, ctx = contexto_do_cenario(
        cenario,
        instancia=instancia,
        periodo=periodo,
        deposito=deposito,
        capacidade=capacidade,
        limite_tempo=limite_tempo,
        diesel=diesel,
        restricoes=restricoes,
        sentido=sentido,
        max_rotas=max_rotas,
    )
    rotas, lam_usado = clarke_wright_ovrp(
        ctx,
        lam=lam,
        usar_two_phase=usar_two_phase,
        usar_postimprove=usar_postimprove,
        iteracoes=iteracoes,
        iter_postimprov=iter_postimprov,
        seed=seed,
        verbose=verbose,
    )
    rotas = limitar_frota(rotas, ctx)
    atend = avaliar_atendimento(rotas, ctx)
    return data, rotas, ctx, atend, lam_usado


def planos_e_resumo(
    rotas: list[Rota],
    ctx: Contexto,
    atend: Atendimento,
    buses: list[Bus] | None = None,
) -> tuple[list[BusPlan], FleetSummary]:
    """Converte a solução do CW no modelo de resultado que o `reporting` lê.

    O CW não tem par travado nem "rounds": a rota nasce no depósito, então
    `origin` é o depósito e `destination` é a última parada. Os ids dos ônibus
    vêm da frota do cenário em ordem; `resolver_cenario` já descarta as rotas
    que passariam do tamanho da frota, mas, numa chamada direta a
    `clarke_wright_ovrp` sem esse teto, os excedentes ainda recebem ids
    sequenciais depois do maior id.
    """
    ids = [bus.id for bus in (buses or [])]
    proximo = (max(ids) + 1) if ids else 1
    planos: list[BusPlan] = []

    for indice, rota in enumerate(rotas):
        if indice < len(ids):
            bus_id = ids[indice]
        else:
            bus_id = proximo
            proximo += 1
        planos.append(
            BusPlan(
                bus_id=bus_id,
                origin=ctx.deposito,
                destination=(
                    rota.paradas[-1] if rota.paradas else ctx.deposito
                ),
                stops=(ctx.deposito, *rota.paradas),
                served_passengers=rota.pax,
                travel_time_minutes=rota.tempo_min,
                peak_load=rota.pico,
                score=(
                    rota.pax / rota.tempo_min if rota.tempo_min else 0.0
                ),
                served_pairs=tuple(rota.pares),
            )
        )

    resumo = FleetSummary(
        rounds=0,
        wins_per_bus=(),
        unserved_passengers=atend.nao_atendida,
        unserved_pairs=atend.pares_nao_atendidos,
    )
    return planos, resumo
