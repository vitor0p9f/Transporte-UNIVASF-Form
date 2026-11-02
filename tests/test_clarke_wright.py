"""Testes do Clarke-Wright OVRP: medidas de rota e a chave de restrições."""

import numpy as np
import pytest

from algorithms.clarke_wright import (
    Atendimento,
    Contexto,
    ModeloOnibus,
    Restricoes,
    Rota,
    Saving,
    _atualizar_custo,
    _dist_rota,
    _fundir,
    _melhor_direcao,
    _shift_10,
    _swap_11,
    _tempo_rota,
    avaliar_atendimento,
    calcular_savings_ovrp,
    clarke_wright_ovrp,
    construir_carga_parada,
    detectar_sentido,
    montar_contexto,
    planos_e_resumo,
)
from entities.bus import Bus
from utils.instances import InstanceData

DEPOSITO = 1


def linear_data(demand: dict | None = None, size: int = 6) -> InstanceData:
    """Reta 1–2–…–size: distância = |a-b| km, tempo = 10 min por km."""
    nodes = list(range(1, size + 1))
    distancia = np.zeros((size + 1, size + 1), dtype=float)
    tempo = np.zeros((size + 1, size + 1), dtype=int)
    for a in nodes:
        for b in nodes:
            if a != b:
                distancia[a, b] = abs(a - b)
                tempo[a, b] = 10 * abs(a - b)
    demandas = np.zeros((size + 1, size + 1), dtype=int)
    for (origem, destino), quantidade in (demand or {}).items():
        demandas[origem, destino] = quantidade
    return InstanceData(nodes=nodes, distance=distancia, time=tempo, demand=demandas)


def manual_data(
    distancia: dict, tempo: dict, size: int = 6
) -> InstanceData:
    """Instância com as arestas exatamente como dadas (matrizes assimétricas)."""
    nodes = list(range(1, size + 1))
    d = np.zeros((size + 1, size + 1), dtype=float)
    t = np.zeros((size + 1, size + 1), dtype=int)
    for (a, b), valor in distancia.items():
        d[a, b] = valor
    for (a, b), valor in tempo.items():
        t[a, b] = valor
    demandas = np.zeros((size + 1, size + 1), dtype=int)
    return InstanceData(nodes=nodes, distance=d, time=t, demand=demandas)


def modelo(capacidade=10) -> ModeloOnibus:
    return ModeloOnibus(
        nome="teste", capacidade=capacidade, consumo_km_l=4.0, custo_litro=8.0
    )


def contexto(
    data: InstanceData,
    *,
    capacidade: int = 10,
    limite_tempo: float = float("inf"),
    restricoes: str = "ambas",
    carga_parada: dict | None = None,
    deposito: int = DEPOSITO,
) -> Contexto:
    if carga_parada is None:
        carga_parada, _ = construir_carga_parada(data.demand, deposito)
    return Contexto(
        distancia=data.distance.astype(float, copy=False),
        tempo=data.time,
        deposito=deposito,
        capacidade=capacidade,
        limite_tempo=limite_tempo,
        modelo=modelo(capacidade),
        carga_parada=carga_parada,
        demanda=data.demand,
        restricoes=Restricoes.da_chave(restricoes),
    )


class TestChaveDeRestricoes:
    def test_as_quatro_chaves(self):
        assert Restricoes.da_chave("capacidade") == Restricoes(True, False)
        assert Restricoes.da_chave("tempo") == Restricoes(False, True)
        assert Restricoes.da_chave("ambas") == Restricoes(True, True)
        assert Restricoes.da_chave("nenhuma") == Restricoes(False, False)

    @pytest.mark.parametrize("chave", ["capacidade", "tempo", "ambas", "nenhuma"])
    def test_chave_de_ida_e_volta(self, chave):
        assert Restricoes.da_chave(chave).chave == chave

    def test_chave_desconhecida_falha_com_a_lista_de_opcoes(self):
        with pytest.raises(ValueError, match="capacidade"):
            Restricoes.da_chave("distancia")

    def test_cabe_so_olha_a_restricao_ativa(self):
        data = linear_data()
        # carga 99 e tempo 999 estouram os dois limites
        assert contexto(data, restricoes="capacidade", capacidade=10,
                        limite_tempo=5).cabe(99, 999) is False
        assert contexto(data, restricoes="capacidade", capacidade=100,
                        limite_tempo=5).cabe(99, 999) is True
        assert contexto(data, restricoes="tempo", capacidade=10,
                        limite_tempo=5).cabe(99, 999) is False
        assert contexto(data, restricoes="tempo", capacidade=10,
                        limite_tempo=1000).cabe(99, 999) is True
        assert contexto(data, restricoes="ambas", capacidade=10,
                        limite_tempo=5).cabe(1, 1) is True
        assert contexto(data, restricoes="nenhuma", capacidade=1,
                        limite_tempo=1).cabe(99, 999) is True

    def test_sem_limite_de_tempo_a_restricao_de_tempo_nao_morde(self):
        data = linear_data()
        ctx = contexto(data, restricoes="tempo", limite_tempo=float("inf"))
        assert ctx.cabe(999, 10_000) is True


class TestMedidasDeRota:
    def test_distancia_e_tempo_somam_os_trechos_a_partir_do_deposito(self):
        ctx = contexto(linear_data())
        assert _dist_rota([2, 4, 5], ctx) == 1 + 2 + 1
        assert _tempo_rota([2, 4, 5], ctx) == 10 + 20 + 10

    def test_rota_vazia_mede_zero(self):
        ctx = contexto(linear_data())
        assert _dist_rota([], ctx) == 0.0
        assert _tempo_rota([], ctx) == 0

    def test_atualizar_custo_preenche_tempo_min(self):
        ctx = contexto(linear_data())
        rota = _atualizar_custo(Rota(paradas=[2, 4]), ctx)
        assert rota.tempo_min == 30
        assert rota.dist_km == 3.0
        assert rota.custo_brl == pytest.approx(3.0 * 2.0)

    def test_melhor_direcao_escolhe_a_mais_curta_sem_restricao(self):
        ctx = contexto(linear_data(), restricoes="capacidade")
        assert _melhor_direcao([5, 2], ctx) == [2, 5]

    def test_melhor_direcao_ignora_tempo_quando_a_chave_nao_pede(self):
        # forward é mais curta (11 km) e mais lenta (120 min); reverse o oposto
        data = manual_data(
            distancia={(1, 4): 10, (4, 2): 1, (1, 2): 1, (2, 4): 40},
            tempo={(1, 4): 60, (4, 2): 60, (1, 2): 1, (2, 4): 1},
        )
        ctx = contexto(data, restricoes="capacidade")
        assert _melhor_direcao([4, 2], ctx) == [4, 2]

    def test_melhor_direcao_prefere_a_direcao_que_cabe_no_tempo(self):
        data = manual_data(
            distancia={(1, 4): 10, (4, 2): 1, (1, 2): 1, (2, 4): 40},
            tempo={(1, 4): 60, (4, 2): 60, (1, 2): 1, (2, 4): 1},
        )
        ctx = contexto(data, restricoes="tempo", limite_tempo=10)
        assert _melhor_direcao([4, 2], ctx) == [2, 4]


class TestCargaPorParada:
    def test_ida_usa_embarques_e_volta_usa_desembarques(self):
        data = linear_data({(2, 3): 4, (4, 3): 2, (1, 5): 9})
        ida, _ = construir_carga_parada(data.demand, DEPOSITO, sentido="ida")
        volta, _ = construir_carga_parada(data.demand, DEPOSITO, sentido="volta")
        assert ida == {2: 4, 4: 2}
        assert volta == {3: 6, 5: 9}

    def test_o_deposito_nunca_entra_como_parada(self):
        data = linear_data({(1, 5): 3})
        carga, _ = construir_carga_parada(data.demand, DEPOSITO, sentido="ida")
        assert DEPOSITO not in carga

    def test_auto_detecta_volta_quando_o_deposito_concentra_embarques(self):
        data = linear_data({(DEPOSITO, 3): 10, (3, DEPOSITO): 1})
        assert detectar_sentido(data.demand, DEPOSITO) == "volta"

    def test_auto_detecta_ida_quando_o_deposito_concentra_desembarques(self):
        data = linear_data({(3, DEPOSITO): 10, (DEPOSITO, 3): 1})
        assert detectar_sentido(data.demand, DEPOSITO) == "ida"

    def test_sentido_invalido_falha(self):
        data = linear_data()
        with pytest.raises(ValueError, match="sentido"):
            construir_carga_parada(data.demand, DEPOSITO, sentido="lado")


class TestFusaoSobRestricao:
    """`_fundir` só bloqueia a fusão quando a restrição pedida está ativa."""

    def make(self, restricoes: str, capacidade=10, limite_tempo=float("inf")):
        data = linear_data()
        return contexto(
            data,
            capacidade=capacidade,
            limite_tempo=limite_tempo,
            restricoes=restricoes,
            carga_parada={2: 6, 3: 3},
        )

    @staticmethod
    def fundir(ctx: Contexto) -> list[list[int]]:
        fundidas = _fundir([Saving(2, 3, 10.0)], {2, 3}, ctx)
        return sorted(rota.paradas for rota in fundidas)

    def test_capacidade_ativa_bloqueia(self):
        ctx = self.make("capacidade", capacidade=8)  # 6 + 3 > 8
        assert self.fundir(ctx) == [[2], [3]]

    def test_capacidade_desligada_permite(self):
        ctx = self.make("tempo", capacidade=8)  # 1 -> 2 -> 3 = 20 min
        assert self.fundir(ctx) == [[2, 3]]

    def test_tempo_ativo_bloqueia(self):
        ctx = self.make("tempo", limite_tempo=15)  # 1 -> 2 -> 3 = 20 min
        assert self.fundir(ctx) == [[2], [3]]

    def test_tempo_desligado_permite(self):
        ctx = self.make("capacidade", limite_tempo=5)
        assert self.fundir(ctx) == [[2, 3]]

    def test_as_duas_ativas_exigem_as_duas(self):
        ctx = self.make("ambas", capacidade=8, limite_tempo=5)
        assert self.fundir(ctx) == [[2], [3]]
        ctx = self.make("ambas", capacidade=8, limite_tempo=100)
        assert self.fundir(ctx) == [[2], [3]]  # ainda estoura a capacidade
        ctx = self.make("ambas", capacidade=100, limite_tempo=100)
        assert self.fundir(ctx) == [[2, 3]]

    def test_nenhuma_ativa_funde_sempre(self):
        ctx = self.make("nenhuma", capacidade=1, limite_tempo=1)
        assert self.fundir(ctx) == [[2, 3]]

    def test_rota_fundida_sai_com_tempo_medido(self):
        ctx = self.make("nenhuma")
        (rota,) = _fundir([Saving(2, 3, 10.0)], {2, 3}, ctx)
        assert rota.tempo_min == _tempo_rota(rota.paradas, ctx)


class TestBuscaLocalSobRestricao:
    """Nenhum operador do CW-3 devolve rota acima do tempo com a chave ativa."""

    def setUp(self):
        data = linear_data()
        return data, contexto(
            data,
            capacidade=20,
            limite_tempo=40,
            restricoes="tempo",
            carga_parada={2: 2, 3: 2, 4: 2, 5: 2},
        )

    def rotas_iniciais(self, ctx):
        return [
            _atualizar_custo(Rota(paradas=[2, 3], carga=4), ctx),
            _atualizar_custo(Rota(paradas=[4, 5], carga=4), ctx),
        ]

    def test_shift_nao_cria_rota_fora_do_tempo(self):
        _, ctx = self.setUp()
        rotas = _shift_10(self.rotas_iniciais(ctx), ctx)
        assert all(r.tempo_min <= ctx.limite_tempo for r in rotas)

    def test_swap_nao_cria_rota_fora_do_tempo(self):
        _, ctx = self.setUp()
        rotas = _swap_11(self.rotas_iniciais(ctx), ctx)
        assert all(r.tempo_min <= ctx.limite_tempo for r in rotas)

    def test_shift_respeita_a_capacidade_quando_ativa(self):
        data = linear_data()
        ctx = contexto(
            data, capacidade=4, restricoes="capacidade",
            carga_parada={2: 2, 3: 2, 4: 2, 5: 2},
        )
        rotas = _shift_10(self.rotas_iniciais(ctx), ctx)
        assert all(r.carga <= ctx.capacidade for r in rotas)


class TestAlgoritmoCompleto:
    def test_deterministico_com_a_mesma_semente(self):
        data = linear_data({(2, 6): 3, (3, 6): 4, (4, 6): 3, (5, 6): 2})
        ctx = contexto(data, capacidade=6, limite_tempo=200)
        primeira, lam1 = clarke_wright_ovrp(
            ctx, iteracoes=5, iter_postimprov=2, seed=7, verbose=False
        )
        segunda, lam2 = clarke_wright_ovrp(
            ctx, iteracoes=5, iter_postimprov=2, seed=7, verbose=False
        )
        assert lam1 == lam2
        assert [r.paradas for r in primeira] == [r.paradas for r in segunda]

    @pytest.mark.parametrize(
        "restricoes,capacidade,limite",
        [
            ("capacidade", 6, 5),
            ("tempo", 1000, 40),
            ("ambas", 6, 40),
            ("nenhuma", 1, 1),
        ],
    )
    def test_respeita_as_restricoes_da_chave(self, restricoes, capacidade, limite):
        data = linear_data({(2, 6): 3, (3, 6): 4, (4, 6): 3, (5, 6): 2})
        ctx = contexto(
            data, capacidade=capacidade, limite_tempo=limite, restricoes=restricoes
        )
        rotas, _ = clarke_wright_ovrp(
            ctx, iteracoes=20, iter_postimprov=5, seed=1, verbose=False
        )
        assert rotas
        if ctx.restricoes.capacidade:
            assert all(r.carga <= capacidade for r in rotas)
        if ctx.restricoes.tempo:
            assert all(r.tempo_min <= limite for r in rotas)

    def test_sem_demanda_nao_gera_rota(self):
        data = linear_data()
        ctx = contexto(data, capacidade=6)
        assert clarke_wright_ovrp(ctx, verbose=False) == ([], 0.0)

    def test_savings_usa_a_formula_ovrp(self):
        ctx = contexto(linear_data())
        savings = calcular_savings_ovrp([2, 3], ctx, lam=0.5)
        # s(2,3) = c(depot,3) - 0.5 * c(2,3) = 2 - 0.5*1
        assert savings[0].valor == pytest.approx(1.5)
        assert (savings[0].i, savings[0].j) == (2, 3)


class TestMontarContexto:
    def test_sem_limite_informa_um_infinito(self):
        ctx = montar_contexto(linear_data(), DEPOSITO, capacidade=10)
        assert ctx.limite_tempo == float("inf")
        assert ctx.restricoes.chave == "ambas"

    def test_capacidade_vem_do_modelo_quando_omitida(self):
        ctx = montar_contexto(linear_data(), DEPOSITO, modelo=modelo(37))
        assert ctx.capacidade == 37

    def test_chave_por_string_e_aceita(self):
        ctx = montar_contexto(linear_data(), DEPOSITO, restricoes="tempo")
        assert ctx.restricoes == Restricoes(tempo=True, capacidade=False)

    def test_sentido_fica_registrado_no_contexto(self):
        data = linear_data({(2, 3): 4})
        ctx = montar_contexto(data, DEPOSITO, capacidade=10, sentido="volta")
        assert ctx.sentido == "volta"
        assert ctx.carga_parada == {3: 4}


class TestAvaliacaoDeAtendimento:
    """A simulação só mede: nenhuma decisão pode depender dela."""

    def test_par_completo_conta_e_preenche_a_rota(self):
        ctx = contexto(linear_data({(2, 4): 1}), capacidade=10)
        rota = Rota(paradas=[2, 3, 4], carga=3)

        atend = avaliar_atendimento([rota], ctx)

        assert (rota.pax, rota.pico) == (1, 1)
        assert rota.pares == ((2, 4, 1),)
        assert atend.atendida == 1
        assert atend.demanda_total == 1
        assert atend.nao_atendida == 0
        assert atend.pct_atendida == pytest.approx(100.0)
        assert atend.alocada == 3

    def test_origem_sem_destino_na_rota_nao_conta(self):
        ctx = contexto(linear_data({(2, 5): 1}))
        rota = Rota(paradas=[2, 3, 4], carga=1)

        avaliar_atendimento([rota], ctx)

        assert rota.pax == 0
        assert rota.pares == ()

    def test_destino_antes_da_origem_nao_conta(self):
        ctx = contexto(linear_data({(4, 2): 1}))
        rota = Rota(paradas=[2, 3, 4], carga=1)

        avaliar_atendimento([rota], ctx)

        assert rota.pax == 0

    def test_deposito_e_a_primeira_parada_da_simulacao(self):
        ctx = contexto(linear_data({(1, 3): 1}))
        rota = Rota(paradas=[3, 4], carga=1)

        avaliar_atendimento([rota], ctx)

        assert rota.pax == 1

    def test_cobranca_sequencial_nao_conta_o_par_duas_vezes(self):
        ctx = contexto(linear_data({(2, 4): 1}))
        r1 = Rota(paradas=[2, 4], carga=2)
        r2 = Rota(paradas=[2, 4], carga=2)

        atend = avaliar_atendimento([r1, r2], ctx)

        assert (r1.pax, r2.pax) == (1, 0)
        assert atend.atendida == 1

    def test_capacidade_limita_o_embarque_e_sobra_demanda(self):
        ctx = contexto(linear_data({(2, 5): 3}), capacidade=2)
        rota = Rota(paradas=[2, 5], carga=3)

        atend = avaliar_atendimento([rota], ctx)

        assert rota.pax == 2
        assert rota.pico == 2
        assert atend.nao_atendida == 1

    def test_pico_e_a_ocupacao_maxima_simultanea(self):
        # 2->5 e 3->6 dividem o trecho 3->5: dois a bordo ao mesmo tempo
        ctx = contexto(linear_data({(2, 5): 1, (3, 6): 1}), capacidade=10)
        rota = Rota(paradas=[2, 3, 5, 6], carga=2)

        avaliar_atendimento([rota], ctx)

        assert rota.pax == 2
        assert rota.pico == 2

    def test_rota_vazia_nao_quebra(self):
        ctx = contexto(linear_data({(2, 4): 1}))
        rota = Rota(paradas=[], carga=0)

        atend = avaliar_atendimento([rota], ctx)

        assert (rota.pax, rota.pico, rota.pares) == (0, 0, ())
        assert atend.atendida == 0

    def test_avaliacao_nao_muda_as_decisoes(self):
        ctx = contexto(linear_data({(2, 4): 1, (3, 5): 1}), capacidade=10)
        rotas, _ = clarke_wright_ovrp(
            ctx, iteracoes=5, iter_postimprov=2, seed=3, verbose=False
        )
        paradas_antes = [list(r.paradas) for r in rotas]
        cargas_antes = [r.carga for r in rotas]

        avaliar_atendimento(rotas, ctx)

        assert [list(r.paradas) for r in rotas] == paradas_antes
        assert [r.carga for r in rotas] == cargas_antes

    def test_sem_demanda_os_percentuais_sao_zero(self):
        atend = Atendimento(
            demanda_total=0, alocada=0, atendida=0, nao_atendida=0, pico=0
        )

        assert atend.pct_alocada == 0.0
        assert atend.pct_atendida == 0.0

    def test_pares_nao_atendidos_sobram_com_a_demanda_restante(self):
        ctx = contexto(linear_data({(2, 5): 3, (3, 5): 1}), capacidade=10)
        rota = Rota(paradas=[2, 3], carga=4)

        atend = avaliar_atendimento([rota], ctx)

        # a rota não visita o 5: ninguém embarca, e os dois pares sobram
        assert atend.atendida == 0
        assert atend.pares_nao_atendidos == ((2, 5, 3), (3, 5, 1))

    def test_par_parcialmente_atendido_sobra_com_o_que_faltou(self):
        ctx = contexto(linear_data({(2, 5): 3}), capacidade=2)
        rota = Rota(paradas=[2, 5], carga=3)

        atend = avaliar_atendimento([rota], ctx)

        assert atend.pares_atendidos == ((2, 5, 2),)
        assert atend.pares_nao_atendidos == ((2, 5, 1),)


class TestPlanosEResumo:
    """A conversão da solução do CW no modelo que o `reporting` lê."""

    def make_bus(self, bus_id: int) -> Bus:
        return Bus(
            id=bus_id,
            passenger_capacity=24,
            fuel_capacity=150.0,
            km_autonomy_per_liter=4.0,
        )

    def test_rota_vira_plano_com_deposito_na_frente(self):
        ctx = contexto(linear_data({(2, 4): 1}), capacidade=10)
        rota = Rota(paradas=[2, 4], carga=2)
        atend = avaliar_atendimento([rota], ctx)

        plans, summary = planos_e_resumo([rota], ctx, atend, [self.make_bus(1)])

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
        ctx = contexto(linear_data({(2, 4): 1, (3, 5): 1}), capacidade=10)
        rotas = [Rota(paradas=[2, 4], carga=1), Rota(paradas=[3, 5], carga=1)]
        atend = avaliar_atendimento(rotas, ctx)

        plans, _ = planos_e_resumo(
            rotas, ctx, atend, [self.make_bus(7), self.make_bus(9)]
        )

        assert [plan.bus_id for plan in plans] == [7, 9]

    def test_rota_alem_da_frota_recebe_id_sequencial(self):
        ctx = contexto(linear_data({(2, 4): 1}), capacidade=10)
        rota = Rota(paradas=[2, 4], carga=1)
        atend = avaliar_atendimento([rota], ctx)

        plans, _ = planos_e_resumo([rota], ctx, atend, [])

        assert [plan.bus_id for plan in plans] == [1]

    def test_resumo_leva_a_demanda_que_sobrou(self):
        ctx = contexto(linear_data({(2, 5): 3}), capacidade=2)
        rota = Rota(paradas=[2, 5], carga=3)
        atend = avaliar_atendimento([rota], ctx)

        _, summary = planos_e_resumo([rota], ctx, atend, [self.make_bus(1)])

        assert summary.unserved_passengers == 1
        assert summary.unserved_pairs == ((2, 5, 1),)
