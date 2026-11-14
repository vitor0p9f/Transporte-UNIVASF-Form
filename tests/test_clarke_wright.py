"""Testes do Clarke-Wright OVRP: medidas de rota e a chave de restrições."""

import numpy as np
import pytest

from algorithms.clarke_wright import (
    Attendance,
    BusModel,
    Context,
    Restrictions,
    Route,
    Saving,
    _best_direction,
    _merge,
    _route_distance,
    _route_time,
    _shift_10,
    _swap_11,
    _update_cost,
    build_context,
    build_stop_loads,
    clarke_wright_ovrp,
    compute_savings_ovrp,
    detect_sense,
    evaluate_attendance,
    limit_fleet,
    plans_and_summary,
    solve_scenario,
)
from tests import factories
from utils.fleet import load_fleet, parse_fleet_ids
from utils.instances import InstanceData
from utils.scenarios import load_scenarios

DEPOSITO = 1


def linear_data(demand: dict | None = None, size: int = 6) -> InstanceData:
    """Reta 1–2–…–size: distância = |a-b| km, tempo = 10 min por km."""
    nodes = list(range(1, size + 1))
    distance = np.zeros((size + 1, size + 1), dtype=float)
    time = np.zeros((size + 1, size + 1), dtype=int)
    for a in nodes:
        for b in nodes:
            if a != b:
                distance[a, b] = abs(a - b)
                time[a, b] = 10 * abs(a - b)
    demandas = np.zeros((size + 1, size + 1), dtype=int)
    for (origem, destino), quantidade in (demand or {}).items():
        demandas[origem, destino] = quantidade
    return InstanceData(nodes=nodes, distance=distance, time=time, demand=demandas)


def manual_data(
    distance: dict, time: dict, size: int = 6
) -> InstanceData:
    """Instância com as arestas exatamente como dadas (matrizes assimétricas)."""
    return factories.make_data(time=time, distance=distance, size=size)


def bus_model(capacity=10) -> BusModel:
    return BusModel(
        name="teste", capacity=capacity, km_per_liter=4.0, diesel_price=8.0
    )


def contexto(
    data: InstanceData,
    *,
    capacity: int = 10,
    max_time: float = float("inf"),
    restrictions: str = "ambas",
    stop_loads: dict | None = None,
    depot: int = DEPOSITO,
    max_routes: int | None = None,
) -> Context:
    if stop_loads is None:
        stop_loads, _ = build_stop_loads(data.demand, depot)
    return Context(
        distance=data.distance.astype(float, copy=False),
        time=data.time,
        depot=depot,
        capacity=capacity,
        max_time=max_time,
        bus_model=bus_model(capacity),
        stop_loads=stop_loads,
        demanda=data.demand,
        restrictions=Restrictions.from_key(restrictions),
        max_routes=max_routes,
    )


class TestChaveDeRestricoes:
    def test_as_quatro_chaves(self):
        assert Restrictions.from_key("capacidade") == Restrictions(True, False)
        assert Restrictions.from_key("tempo") == Restrictions(False, True)
        assert Restrictions.from_key("ambas") == Restrictions(True, True)
        assert Restrictions.from_key("nenhuma") == Restrictions(False, False)

    @pytest.mark.parametrize("key", ["capacidade", "tempo", "ambas", "nenhuma"])
    def test_chave_de_ida_e_volta(self, key):
        assert Restrictions.from_key(key).key == key

    def test_chave_desconhecida_falha_com_a_lista_de_opcoes(self):
        with pytest.raises(ValueError, match="capacidade"):
            Restrictions.from_key("distancia")

    def test_cabe_so_olha_a_restricao_ativa(self):
        data = linear_data()
        # carga 99 e tempo 999 estouram os dois limites
        assert contexto(data, restrictions="capacidade", capacity=10,
                        max_time=5).fits(99, 999) is False
        assert contexto(data, restrictions="capacidade", capacity=100,
                        max_time=5).fits(99, 999) is True
        assert contexto(data, restrictions="tempo", capacity=10,
                        max_time=5).fits(99, 999) is False
        assert contexto(data, restrictions="tempo", capacity=10,
                        max_time=1000).fits(99, 999) is True
        assert contexto(data, restrictions="ambas", capacity=10,
                        max_time=5).fits(1, 1) is True
        assert contexto(data, restrictions="nenhuma", capacity=1,
                        max_time=1).fits(99, 999) is True

    def test_sem_limite_de_tempo_a_restricao_de_tempo_nao_morde(self):
        data = linear_data()
        ctx = contexto(data, restrictions="tempo", max_time=float("inf"))
        assert ctx.fits(999, 10_000) is True


class TestMedidasDeRota:
    def test_distancia_e_tempo_somam_os_trechos_a_partir_do_deposito(self):
        ctx = contexto(linear_data())
        assert _route_distance([2, 4, 5], ctx) == 1 + 2 + 1
        assert _route_time([2, 4, 5], ctx) == 10 + 20 + 10

    def test_rota_vazia_mede_zero(self):
        ctx = contexto(linear_data())
        assert _route_distance([], ctx) == 0.0
        assert _route_time([], ctx) == 0

    def test_atualizar_custo_preenche_tempo_min(self):
        ctx = contexto(linear_data())
        route = _update_cost(Route(stops=[2, 4]), ctx)
        assert route.time_minutes == 30
        assert route.distance_km == 3.0
        assert route.cost_brl == pytest.approx(3.0 * 2.0)

    def test_melhor_direcao_escolhe_a_mais_curta_sem_restricao(self):
        ctx = contexto(linear_data(), restrictions="capacidade")
        assert _best_direction([5, 2], ctx) == [2, 5]

    def test_melhor_direcao_ignora_tempo_quando_a_chave_nao_pede(self):
        # forward é mais curta (11 km) e mais lenta (120 min); reverse o oposto
        data = manual_data(
            distance={(1, 4): 10, (4, 2): 1, (1, 2): 1, (2, 4): 40},
            time={(1, 4): 60, (4, 2): 60, (1, 2): 1, (2, 4): 1},
        )
        ctx = contexto(data, restrictions="capacidade")
        assert _best_direction([4, 2], ctx) == [4, 2]

    def test_melhor_direcao_prefere_a_direcao_que_cabe_no_tempo(self):
        data = manual_data(
            distance={(1, 4): 10, (4, 2): 1, (1, 2): 1, (2, 4): 40},
            time={(1, 4): 60, (4, 2): 60, (1, 2): 1, (2, 4): 1},
        )
        ctx = contexto(data, restrictions="tempo", max_time=10)
        assert _best_direction([4, 2], ctx) == [2, 4]


class TestCargaPorParada:
    def test_ida_usa_embarques_e_volta_usa_desembarques(self):
        data = linear_data({(2, 3): 4, (4, 3): 2, (1, 5): 9})
        ida, _ = build_stop_loads(data.demand, DEPOSITO, sense="ida")
        volta, _ = build_stop_loads(data.demand, DEPOSITO, sense="volta")
        assert ida == {2: 4, 4: 2}
        assert volta == {3: 6, 5: 9}

    def test_o_deposito_nunca_entra_como_parada(self):
        data = linear_data({(1, 5): 3})
        load, _ = build_stop_loads(data.demand, DEPOSITO, sense="ida")
        assert DEPOSITO not in load

    def test_auto_detecta_volta_quando_o_deposito_concentra_embarques(self):
        data = linear_data({(DEPOSITO, 3): 10, (3, DEPOSITO): 1})
        assert detect_sense(data.demand, DEPOSITO) == "volta"

    def test_auto_detecta_ida_quando_o_deposito_concentra_desembarques(self):
        data = linear_data({(3, DEPOSITO): 10, (DEPOSITO, 3): 1})
        assert detect_sense(data.demand, DEPOSITO) == "ida"

    def test_sentido_invalido_falha(self):
        data = linear_data()
        with pytest.raises(ValueError, match="sentido"):
            build_stop_loads(data.demand, DEPOSITO, sense="lado")


class TestFusaoSobRestricao:
    """`_fundir` só bloqueia a fusão quando a restrição pedida está ativa."""

    def make(self, restrictions: str, capacity=10, max_time=float("inf")):
        data = linear_data()
        return contexto(
            data,
            capacity=capacity,
            max_time=max_time,
            restrictions=restrictions,
            stop_loads={2: 6, 3: 3},
        )

    @staticmethod
    def fundir(ctx: Context) -> list[list[int]]:
        fundidas = _merge([Saving(2, 3, 10.0)], {2, 3}, ctx)
        return sorted(route.stops for route in fundidas)

    def test_capacidade_ativa_bloqueia(self):
        ctx = self.make("capacidade", capacity=8)  # 6 + 3 > 8
        assert self.fundir(ctx) == [[2], [3]]

    def test_capacidade_desligada_permite(self):
        ctx = self.make("tempo", capacity=8)  # 1 -> 2 -> 3 = 20 min
        assert self.fundir(ctx) == [[2, 3]]

    def test_tempo_ativo_bloqueia(self):
        ctx = self.make("tempo", max_time=15)  # 1 -> 2 -> 3 = 20 min
        assert self.fundir(ctx) == [[2], [3]]

    def test_tempo_desligado_permite(self):
        ctx = self.make("capacidade", max_time=5)
        assert self.fundir(ctx) == [[2, 3]]

    def test_as_duas_ativas_exigem_as_duas(self):
        ctx = self.make("ambas", capacity=8, max_time=5)
        assert self.fundir(ctx) == [[2], [3]]
        ctx = self.make("ambas", capacity=8, max_time=100)
        assert self.fundir(ctx) == [[2], [3]]  # ainda estoura a capacidade
        ctx = self.make("ambas", capacity=100, max_time=100)
        assert self.fundir(ctx) == [[2, 3]]

    def test_nenhuma_ativa_funde_sempre(self):
        ctx = self.make("nenhuma", capacity=1, max_time=1)
        assert self.fundir(ctx) == [[2, 3]]

    def test_rota_fundida_sai_com_tempo_medido(self):
        ctx = self.make("nenhuma")
        (route,) = _merge([Saving(2, 3, 10.0)], {2, 3}, ctx)
        assert route.time_minutes == _route_time(route.stops, ctx)


class TestBuscaLocalSobRestricao:
    """Nenhum operador do CW-3 devolve rota acima do tempo com a chave ativa."""

    def setUp(self):
        data = linear_data()
        return data, contexto(
            data,
            capacity=20,
            max_time=40,
            restrictions="tempo",
            stop_loads={2: 2, 3: 2, 4: 2, 5: 2},
        )

    def rotas_iniciais(self, ctx):
        return [
            _update_cost(Route(stops=[2, 3], load=4), ctx),
            _update_cost(Route(stops=[4, 5], load=4), ctx),
        ]

    def test_shift_nao_cria_rota_fora_do_tempo(self):
        _, ctx = self.setUp()
        routes = _shift_10(self.rotas_iniciais(ctx), ctx)
        assert all(r.time_minutes <= ctx.max_time for r in routes)

    def test_swap_nao_cria_rota_fora_do_tempo(self):
        _, ctx = self.setUp()
        routes = _swap_11(self.rotas_iniciais(ctx), ctx)
        assert all(r.time_minutes <= ctx.max_time for r in routes)

    def test_shift_respeita_a_capacidade_quando_ativa(self):
        data = linear_data()
        ctx = contexto(
            data, capacity=4, restrictions="capacidade",
            stop_loads={2: 2, 3: 2, 4: 2, 5: 2},
        )
        routes = _shift_10(self.rotas_iniciais(ctx), ctx)
        assert all(r.load <= ctx.capacity for r in routes)


class TestAlgoritmoCompleto:
    def test_deterministico_com_a_mesma_semente(self):
        data = linear_data({(2, 6): 3, (3, 6): 4, (4, 6): 3, (5, 6): 2})
        ctx = contexto(data, capacity=6, max_time=200)
        first, lam1 = clarke_wright_ovrp(
            ctx, iterations=5, post_improvement_iterations=2, seed=7, verbose=False
        )
        segunda, lam2 = clarke_wright_ovrp(
            ctx, iterations=5, post_improvement_iterations=2, seed=7, verbose=False
        )
        assert lam1 == lam2
        assert [r.stops for r in first] == [r.stops for r in segunda]

    @pytest.mark.parametrize(
        "restrictions,capacity,limit",
        [
            ("capacidade", 6, 5),
            ("tempo", 1000, 40),
            ("ambas", 6, 40),
            ("nenhuma", 1, 1),
        ],
    )
    def test_respeita_as_restricoes_da_chave(self, restrictions, capacity, limit):
        data = linear_data({(2, 6): 3, (3, 6): 4, (4, 6): 3, (5, 6): 2})
        ctx = contexto(
            data, capacity=capacity, max_time=limit, restrictions=restrictions
        )
        routes, _ = clarke_wright_ovrp(
            ctx, iterations=20, post_improvement_iterations=5, seed=1, verbose=False
        )
        assert routes
        if ctx.restrictions.capacity:
            assert all(r.load <= capacity for r in routes)
        if ctx.restrictions.time:
            assert all(r.time_minutes <= limit for r in routes)

    def test_sem_demanda_nao_gera_rota(self):
        data = linear_data()
        ctx = contexto(data, capacity=6)
        assert clarke_wright_ovrp(ctx, verbose=False) == ([], 0.0)

    def test_savings_usa_a_formula_ovrp(self):
        ctx = contexto(linear_data())
        savings = compute_savings_ovrp([2, 3], ctx, lam=0.5)
        # s(2,3) = c(depot,3) - 0.5 * c(2,3) = 2 - 0.5*1
        assert savings[0].value == pytest.approx(1.5)
        assert (savings[0].i, savings[0].j) == (2, 3)


class TestMontarContexto:
    def test_sem_limite_informa_um_infinito(self):
        ctx = build_context(linear_data(), DEPOSITO, capacity=10)
        assert ctx.max_time == float("inf")
        assert ctx.restrictions.key == "ambas"

    def test_capacidade_vem_do_modelo_quando_omitida(self):
        ctx = build_context(linear_data(), DEPOSITO, bus_model=bus_model(37))
        assert ctx.capacity == 37

    def test_chave_por_string_e_aceita(self):
        ctx = build_context(linear_data(), DEPOSITO, restrictions="tempo")
        assert ctx.restrictions == Restrictions(time=True, capacity=False)

    def test_sentido_fica_registrado_no_contexto(self):
        data = linear_data({(2, 3): 4})
        ctx = build_context(data, DEPOSITO, capacity=10, sense="volta")
        assert ctx.sense == "volta"
        assert ctx.stop_loads == {3: 4}


class TestAvaliacaoDeAtendimento:
    """A simulação só mede: nenhuma decisão pode depender dela."""

    def test_par_completo_conta_e_preenche_a_rota(self):
        ctx = contexto(linear_data({(2, 4): 1}), capacity=10)
        route = Route(stops=[2, 3, 4], load=3)

        attendance = evaluate_attendance([route], ctx)

        assert (route.passengers, route.peak_load) == (1, 1)
        assert route.pairs == ((2, 4, 1),)
        assert attendance.served == 1
        assert attendance.total_demand == 1
        assert attendance.unserved == 0
        assert attendance.served_pct == pytest.approx(100.0)
        assert attendance.allocated == 3

    def test_origem_sem_destino_na_rota_nao_conta(self):
        ctx = contexto(linear_data({(2, 5): 1}))
        route = Route(stops=[2, 3, 4], load=1)

        evaluate_attendance([route], ctx)

        assert route.passengers == 0
        assert route.pairs == ()

    def test_destino_antes_da_origem_nao_conta(self):
        ctx = contexto(linear_data({(4, 2): 1}))
        route = Route(stops=[2, 3, 4], load=1)

        evaluate_attendance([route], ctx)

        assert route.passengers == 0

    def test_deposito_e_a_primeira_parada_da_simulacao(self):
        ctx = contexto(linear_data({(1, 3): 1}))
        route = Route(stops=[3, 4], load=1)

        evaluate_attendance([route], ctx)

        assert route.passengers == 1

    def test_cobranca_sequencial_nao_conta_o_par_duas_vezes(self):
        ctx = contexto(linear_data({(2, 4): 1}))
        r1 = Route(stops=[2, 4], load=2)
        r2 = Route(stops=[2, 4], load=2)

        attendance = evaluate_attendance([r1, r2], ctx)

        assert (r1.passengers, r2.passengers) == (1, 0)
        assert attendance.served == 1

    def test_capacidade_limita_o_embarque_e_sobra_demanda(self):
        ctx = contexto(linear_data({(2, 5): 3}), capacity=2)
        route = Route(stops=[2, 5], load=3)

        attendance = evaluate_attendance([route], ctx)

        assert route.passengers == 2
        assert route.peak_load == 2
        assert attendance.unserved == 1

    def test_pico_e_a_ocupacao_maxima_simultanea(self):
        # 2->5 e 3->6 dividem o trecho 3->5: dois a bordo ao mesmo tempo
        ctx = contexto(linear_data({(2, 5): 1, (3, 6): 1}), capacity=10)
        route = Route(stops=[2, 3, 5, 6], load=2)

        evaluate_attendance([route], ctx)

        assert route.passengers == 2
        assert route.peak_load == 2

    def test_rota_vazia_nao_quebra(self):
        ctx = contexto(linear_data({(2, 4): 1}))
        route = Route(stops=[], load=0)

        attendance = evaluate_attendance([route], ctx)

        assert (route.passengers, route.peak_load, route.pairs) == (0, 0, ())
        assert attendance.served == 0

    def test_avaliacao_nao_muda_as_decisoes(self):
        ctx = contexto(linear_data({(2, 4): 1, (3, 5): 1}), capacity=10)
        routes, _ = clarke_wright_ovrp(
            ctx, iterations=5, post_improvement_iterations=2, seed=3, verbose=False
        )
        paradas_antes = [list(r.stops) for r in routes]
        cargas_antes = [r.load for r in routes]

        evaluate_attendance(routes, ctx)

        assert [list(r.stops) for r in routes] == paradas_antes
        assert [r.load for r in routes] == cargas_antes

    def test_sem_demanda_os_percentuais_sao_zero(self):
        attendance = Attendance(
            total_demand=0, allocated=0, served=0, unserved=0, peak_load=0
        )

        assert attendance.allocated_pct == 0.0
        assert attendance.served_pct == 0.0

    def test_pares_nao_atendidos_sobram_com_a_demanda_restante(self):
        ctx = contexto(linear_data({(2, 5): 3, (3, 5): 1}), capacity=10)
        route = Route(stops=[2, 3], load=4)

        attendance = evaluate_attendance([route], ctx)

        # a rota não visita o 5: ninguém embarca, e os dois pares sobram
        assert attendance.served == 0
        assert attendance.unserved_pairs == ((2, 5, 3), (3, 5, 1))


class TestLimiteDeFrota:
    def test_sem_teto_e_um_no_op(self):
        ctx = contexto(linear_data({(2, 4): 1}), capacity=10)
        routes = [Route(stops=[2, 4], load=1), Route(stops=[3, 5], load=1)]

        assert limit_fleet(routes, ctx) == routes

    def test_solucao_que_ja_cabe_fica_intacta(self):
        ctx = contexto(linear_data({(2, 4): 1}), capacity=10, max_routes=2)
        routes = [Route(stops=[2, 4], load=1), Route(stops=[3, 5], load=1)]

        assert limit_fleet(routes, ctx) == routes

    def test_descarta_as_rotas_que_menos_atendem(self):
        ctx = contexto(
            linear_data({(2, 5): 4, (3, 6): 1}), capacity=10, max_routes=1
        )
        cheia = Route(stops=[2, 5], load=4)
        vazia = Route(stops=[3, 6], load=1)

        assert limit_fleet([vazia, cheia], ctx) == [cheia]

    def test_resolver_nunca_devolve_mais_rotas_que_a_frota(self, root):
        scenario = next(
            s for s in load_scenarios(root) if str(s["scenario_id"]) == "54"
        )
        buses = load_fleet(
            root / "fleet.csv", parse_fleet_ids(scenario["fleet_bus_ids"])
        )
        # Cenário 54 é o caso conhecido: o CW-1 puro gera mais rotas que
        # ônibus (9 para 5); o limite corta antes da avaliação.
        _data, routes, ctx, _atend, _lam = solve_scenario(
            scenario,
            restrictions="tempo",
            lam=1.0,
            use_two_phase=False,
            use_post_improvement=False,
            seed=42,
        )

        assert ctx.max_routes == len(buses)
        assert len(routes) <= len(buses)

    def test_par_parcialmente_atendido_sobra_com_o_que_faltou(self):
        ctx = contexto(linear_data({(2, 5): 3}), capacity=2)
        route = Route(stops=[2, 5], load=3)

        attendance = evaluate_attendance([route], ctx)

        assert attendance.served_pairs == ((2, 5, 2),)
        assert attendance.unserved_pairs == ((2, 5, 1),)


class TestPlanosEResumo:
    """A conversão da solução do CW no modelo que o `reporting` lê."""

    @staticmethod
    def make_bus(bus_id: int):
        return factories.make_bus(bus_id, capacity=24, fuel_capacity=150.0)

    def test_rota_vira_plano_com_deposito_na_frente(self):
        ctx = contexto(linear_data({(2, 4): 1}), capacity=10)
        route = Route(stops=[2, 4], load=2)
        attendance = evaluate_attendance([route], ctx)

        plans, summary = plans_and_summary([route], ctx, attendance, [self.make_bus(1)])

        assert len(plans) == 1
        assert plans[0].stops == (1, 2, 4)
        assert plans[0].origin == 1
        assert plans[0].destination == 4
        assert plans[0].served_passengers == 1
        assert plans[0].peak_load == 1
        assert plans[0].served_pairs == ((2, 4, 1),)
        assert summary.unserved_passengers == 0
        assert summary.unserved_pairs == ()

    def test_ids_da_frota_seguem_a_ordem_das_rotas(self):
        ctx = contexto(linear_data({(2, 4): 1, (3, 5): 1}), capacity=10)
        routes = [Route(stops=[2, 4], load=1), Route(stops=[3, 5], load=1)]
        attendance = evaluate_attendance(routes, ctx)

        plans, _ = plans_and_summary(
            routes, ctx, attendance, [self.make_bus(7), self.make_bus(9)]
        )

        assert [plan.bus_id for plan in plans] == [7, 9]

    def test_rota_alem_da_frota_recebe_id_sequencial(self):
        ctx = contexto(linear_data({(2, 4): 1}), capacity=10)
        route = Route(stops=[2, 4], load=1)
        attendance = evaluate_attendance([route], ctx)

        plans, _ = plans_and_summary([route], ctx, attendance, [])

        assert [plan.bus_id for plan in plans] == [1]

    def test_resumo_leva_a_demanda_que_sobrou(self):
        ctx = contexto(linear_data({(2, 5): 3}), capacity=2)
        route = Route(stops=[2, 5], load=3)
        attendance = evaluate_attendance([route], ctx)

        _, summary = plans_and_summary([route], ctx, attendance, [self.make_bus(1)])

        assert summary.unserved_passengers == 1
        assert summary.unserved_pairs == ((2, 5, 1),)
