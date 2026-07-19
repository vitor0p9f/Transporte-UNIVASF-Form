"""
clarke_wright_multi.py
----------------------
Implementação do algoritmo Clarke-Wright multi-objetivo para o problema
de roteamento de ônibus da UNIVASF (OVRP), com controle estrito de capacidade
e paradas de desembarque intermediárias (Pick-up and Delivery).
"""

import math
import random
from dataclasses import dataclass, field
from typing import Optional, Union
from utils.fleet import ModeloOnibus, ONIBUS_GENERICO

@dataclass
class RotaMulti:
    paradas: list[str] = field(default_factory=list)
    cargas_trecho: list[int] = field(default_factory=list)  # Carga a bordo em cada trecho (segmento)
    carga_maxima: int = 0
    dist_km: float = 0.0
    tempo_min: float = 0.0
    custo_brl: float = 0.0
    viagens_atendidas: list[dict] = field(default_factory=list)

    def __repr__(self) -> str:
        return (
            f"RotaMulti({len(self.paradas)} paradas | "
            f"max_load={self.carga_maxima} | "
            f"{self.dist_km:.1f} km | "
            f"{self.tempo_min:.1f} min | "
            f"R${self.custo_brl:.2f})"
        )

# Peso padrão dos termos do objetivo
W_OCC_REWARD = 100.0   # Recompensa por boa ocupação (entre C/2 e C)
W_OCC_PENALTY = 1000.0 # Penalidade exponencial massiva por superlotação ou sub-ocupação
W_HETEROGENEITY = 50.0 # Penalidade por destinos diferentes
W_TIME_PENALTY = 500.0 # Penalidade exponencial por passar do tempo máximo

def calcular_custo_total_multi(rotas: list[RotaMulti]) -> float:
    return sum(r.custo_brl for r in rotas)

def safe_exp(x: float) -> float:
    # Evita overflow de float calculando math.exp com limite superior
    try:
        return math.exp(min(x, 50.0))
    except Exception:
        return math.exp(50.0)

def avaliar_fitness_rota(
    paradas: list[str],
    cargas_trecho: list[int],
    dist_km: float,
    tempo_min: float,
    viagens: list[dict],
    capacidade: int,
    conforto: int,
    modelo: ModeloOnibus,
    max_tempo: float,
) -> float:
    """
    Calcula a função de custo multi-objetivo para uma rota.
    Retorna o custo total da rota (combustível + penalidades).
    """
    custo_combustivel = modelo.custo_rota(dist_km)

    # 1. Lotação / Ocupação
    carga_maxima = max(cargas_trecho) if cargas_trecho else 0
    penalidade_ocupacao = 0.0
    metade = capacidade / 2.0

    if metade <= carga_maxima <= capacidade:
        # Linear e positivo: recompensa reduz o custo
        proporcao = (carga_maxima - metade) / max(1.0, capacidade - metade)
        penalidade_ocupacao = - W_OCC_REWARD * proporcao
    elif carga_maxima < metade:
        # Sub-ocupação: penalidade exponencial massiva
        penalidade_ocupacao = W_OCC_PENALTY * (safe_exp(metade - carga_maxima) - 1.0)
    else:
        # Superlotação: penalidade exponencial massiva
        penalidade_ocupacao = W_OCC_PENALTY * (safe_exp(carga_maxima - capacidade) - 1.0)

    # 2. Heterogeneidade: destinos diferentes
    destinos = set(t["desembarque"] for t in viagens)
    n_destinos = len(destinos)
    penalidade_heterogeneidade = W_HETEROGENEITY * ((n_destinos - 1) ** 2) if n_destinos > 1 else 0.0

    # 3. Horário de funcionamento: tempo de rota
    penalidade_tempo = 0.0
    if tempo_min > max_tempo:
        penalidade_tempo = W_TIME_PENALTY * (safe_exp(tempo_min - max_tempo) - 1.0)

    return custo_combustivel + penalidade_ocupacao + penalidade_heterogeneidade + penalidade_tempo

def calcular_tempo_retorno_estimado(curr: str, on_board_list: list[dict], matriz_tempo: dict) -> float:
    # Retorna o tempo estimado para realizar todos os desembarques restantes usando Nearest Neighbor
    restantes = set(t["desembarque"] for t in on_board_list)
    tempo = 0.0
    no_atual = curr
    while restantes:
        proximo = None
        menor_t = float("inf")
        for r in restantes:
            t = matriz_tempo.get(no_atual, {}).get(r, float("inf"))
            if t < menor_t:
                menor_t = t
                proximo = r
        if proximo is not None:
            tempo += menor_t
            restantes.remove(proximo)
            no_atual = proximo
        else:
            break
    return tempo

def construir_rota_multi_objetivo(
    remaining_boardings: set[str],
    viagens_restantes: list[dict],
    matriz_dist: dict,
    matriz_tempo: dict,
    deposito: str,
    capacidade: int,
    conforto: int,
    modelo: ModeloOnibus,
    max_tempo: float,
    lam: float,
) -> RotaMulti:
    """
    Constrói uma única rota sequencial com base nas regras de capacidade,
    tempo máximo estrito de 90 min e desembarque guloso de menor custo.
    """
    rota = RotaMulti(paradas=[deposito])
    current_node = deposito
    on_board: list[dict] = []
    
    total_dist = 0.0
    total_time = 0.0
    cargas_trecho = []

    while True:
        # Se o tempo limite foi excedido, paramos de aceitar embarques e vamos apenas descarregar
        excedeu_tempo = total_time > max_tempo

        # Identificar candidatos a embarque válidos
        valid_candidates = []
        if not excedeu_tempo:
            for j in sorted(remaining_boardings):
                # Passageiros aguardando nesta parada
                passageiros_j = [t for t in viagens_restantes if t["embarque"] == j]
                if not passageiros_j:
                    continue
                
                # Regra: A lotação nunca deve passar do máximo do ônibus
                # Ao chegar em j, descarregamos quem desce em j primeiro!
                descem_em_j = [t for t in on_board if t["desembarque"] == j]
                on_board_apos_desemb = len(on_board) - len(descem_em_j)
                vagas_restantes = capacidade - on_board_apos_desemb
                
                if len(passageiros_j) <= vagas_restantes:
                    # Cabe todo mundo!
                    valid_candidates.append((j, passageiros_j, False))

        # Se temos candidatos que cabem inteiros, nós os pontuamos usando o score multi-objetivo
        if valid_candidates:
            melhor_candidato = None
            melhor_score = -float("inf")

            for j, passageiros_j, _ in valid_candidates:
                # Simula a adição do ponto j
                dist_j = matriz_dist.get(current_node, {}).get(j, float("inf"))
                tempo_j = matriz_tempo.get(current_node, {}).get(j, float("inf"))

                if dist_j == float("inf") or tempo_j == float("inf"):
                    continue

                # Carga simulada após desembarques e embarques em j
                sim_on_board = list(on_board)
                descem_em_j_sim = [t for t in sim_on_board if t["desembarque"] == j]
                for t in descem_em_j_sim:
                    sim_on_board.remove(t)
                sim_on_board.extend(passageiros_j)
                
                # Limite estrito de tempo: calcula tempo total simulado incluindo desembarques futuros
                tempo_retorno = calcular_tempo_retorno_estimado(j, sim_on_board, matriz_tempo)
                tempo_total_rota = total_time + tempo_j + tempo_retorno
                if tempo_total_rota > max_tempo:
                    # Estoura o limite de tempo estrito de 90 min!
                    continue

                sim_cargas = cargas_trecho + [len(sim_on_board)]
                sim_dist = total_dist + dist_j
                sim_tempo = total_time + tempo_j

                # Score de Clarke-Wright básico com lambda
                savings_val = matriz_dist.get(deposito, {}).get(j, 0.0) - lam * dist_j

                # Avaliação multi-objetivo
                fitness = avaliar_fitness_rota(
                    paradas=rota.paradas + [j],
                    cargas_trecho=sim_cargas,
                    dist_km=sim_dist,
                    tempo_min=sim_tempo,
                    viagens=sim_on_board,
                    capacidade=capacidade,
                    conforto=conforto,
                    modelo=modelo,
                    max_tempo=max_tempo,
                )

                score = savings_val - fitness
                if score > melhor_score:
                    melhor_score = score
                    melhor_candidato = (j, passageiros_j, dist_j, tempo_j)

            if melhor_candidato:
                j, passageiros_j, dist_j, tempo_j = melhor_candidato
                rota.paradas.append(j)
                cargas_trecho.append(len(on_board)) # Carga no trecho anterior
                
                # Desembarca quem desce em j primeiro!
                descem_em_j = [t for t in on_board if t["desembarque"] == j]
                for t in descem_em_j:
                    on_board.remove(t)
                
                # Carrega passageiros
                on_board.extend(passageiros_j)
                rota.viagens_atendidas.extend(passageiros_j)
                
                # Remove das viagens restantes
                for t in passageiros_j:
                    viagens_restantes.remove(t)
                if j in remaining_boardings:
                    remaining_boardings.remove(j)

                total_dist += dist_j
                total_time += tempo_j
                current_node = j
                continue

        # Se nenhum ponto pôde ser atendido inteiramente por limite de capacidade (ou por tempo, ou lista vazia)
        # Finaliza a rota e inicia a etapa de encontrar qual desembarque gera menor custo
        if on_board:
            # Encontrar qual desembarque gera o menor custo
            desembarques_possiveis = list(set(t["desembarque"] for t in on_board))
            
            melhor_desemb = None
            menor_custo_desemb = float("inf")

            for d in desembarques_possiveis:
                dist_d = matriz_dist.get(current_node, {}).get(d, float("inf"))
                tempo_d = matriz_tempo.get(current_node, {}).get(d, float("inf"))

                if dist_d == float("inf"):
                    continue

                if dist_d < menor_custo_desemb:
                    menor_custo_desemb = dist_d
                    melhor_desemb = (d, dist_d, tempo_d)

            if melhor_desemb:
                d, dist_d, tempo_d = melhor_desemb
                rota.paradas.append(d)
                cargas_trecho.append(len(on_board)) # Carga no trecho current_node -> d

                # Desembarca passageiros
                passageiros_desembarcados = [t for t in on_board if t["desembarque"] == d]
                for t in passageiros_desembarcados:
                    on_board.remove(t)

                total_dist += dist_d
                total_time += tempo_d
                current_node = d
                continue

        # Se não há mais passageiros a bordo e não há candidatos válidos que caibam inteiros, mas ainda restam embarques
        # Realizamos split escolhendo a parada com melhor score e enchendo o ônibus, respeitando limite de tempo
        if remaining_boardings and not on_board and not excedeu_tempo:
            melhor_split = None
            melhor_score = -float("inf")

            for j in sorted(remaining_boardings):
                passageiros_j = [t for t in viagens_restantes if t["embarque"] == j]
                dist_j = matriz_dist.get(current_node, {}).get(j, float("inf"))
                tempo_j = matriz_tempo.get(current_node, {}).get(j, float("inf"))

                if dist_j == float("inf") or tempo_j == float("inf"):
                    continue

                # Como não cabe tudo, simulamos carregar apenas até a capacidade C
                carga_lota = passageiros_j[:capacidade]
                
                # Valida limite estrito de tempo
                tempo_retorno = calcular_tempo_retorno_estimado(j, carga_lota, matriz_tempo)
                tempo_total_rota = total_time + tempo_j + tempo_retorno
                if tempo_total_rota > max_tempo:
                    continue

                sim_cargas = cargas_trecho + [len(carga_lota)]
                sim_dist = total_dist + dist_j
                sim_tempo = total_time + tempo_j

                savings_val = matriz_dist.get(deposito, {}).get(j, 0.0) - lam * dist_j
                fitness = avaliar_fitness_rota(
                    paradas=rota.paradas + [j],
                    cargas_trecho=sim_cargas,
                    dist_km=sim_dist,
                    tempo_min=sim_tempo,
                    viagens=carga_lota,
                    capacidade=capacidade,
                    conforto=conforto,
                    modelo=modelo,
                    max_tempo=max_tempo,
                )

                score = savings_val - fitness
                if score > melhor_score:
                    melhor_score = score
                    melhor_split = (j, carga_lota, dist_j, tempo_j)

            if melhor_split:
                j, carga_lota, dist_j, tempo_j = melhor_split
                rota.paradas.append(j)
                cargas_trecho.append(0) # Inicia vazio
                
                on_board.extend(carga_lota)
                rota.viagens_atendidas.extend(carga_lota)

                for t in carga_lota:
                    viagens_restantes.remove(t)

                sobrou_j = [t for t in viagens_restantes if t["embarque"] == j]
                if not sobrou_j:
                    remaining_boardings.remove(j)

                total_dist += dist_j
                total_time += tempo_j
                current_node = j
                continue

        # Se não há mais nada a fazer (boardings vazios, on_board vazio)
        break

    # Completa as estatísticas da rota
    rota.dist_km = round(total_dist, 2)
    rota.tempo_min = round(total_time, 2)
    rota.custo_brl = modelo.custo_rota(rota.dist_km)
    rota.carga_maxima = max(cargas_trecho) if cargas_trecho else 0
    
    rota.cargas_trecho = cargas_trecho + [0]
    return rota


def tentar_inserir_viagem(r: RotaMulti, t: dict, matriz_dist: dict, matriz_tempo: dict, capacidade: int, max_tempo: float) -> bool:
    """
    Tenta inserir a viagem `t` (embarque, desembarque) na rota `r` sem violar a capacidade
    e tentando respeitar o limite de tempo (com uma tolerância de 20%).
    Retorna True se conseguir inserir com sucesso, modificando a rota `r` in-place.
    """
    emb = t["embarque"]
    des = t["desembarque"]
    
    melhor_dist_aumento = float("inf")
    melhor_seq = None
    melhor_cargas = None
    melhor_tempo = None
    
    paradas_orig = list(r.paradas)
    # Tenta todas as posições para inserir 'emb'
    for i in range(1, len(paradas_orig) + 1):
        seq_com_emb = paradas_orig[:i] + [emb] + paradas_orig[i:]
        # Tenta todas as posições para inserir 'des' após 'emb'
        for j in range(i + 1, len(seq_com_emb) + 1):
            seq_final = seq_com_emb[:j] + [des] + seq_com_emb[j:]
            
            # Valida capacidade ao longo da rota
            on_board_sim = []
            viagens_sim = list(r.viagens_atendidas) + [t]
            cargas_sim = []
            valid = True
            
            for idx in range(len(seq_final) - 1):
                node = seq_final[idx]
                next_node = seq_final[idx+1]
                
                # Embarques neste ponto
                b_here = [vt for vt in viagens_sim if vt["embarque"] == node]
                on_board_sim.extend(b_here)
                
                # Desembarques neste ponto
                a_here = [vt for vt in on_board_sim if vt["desembarque"] == node]
                for vt in a_here:
                    on_board_sim.remove(vt)
                    
                cargas_sim.append(len(on_board_sim))
                if len(on_board_sim) > capacidade:
                    valid = False
                    break
                    
            if not valid:
                continue
                
            # Calcula a nova distância e tempo da rota
            nova_dist = 0.0
            novo_tempo = 0.0
            for idx in range(len(seq_final) - 1):
                origem = seq_final[idx]
                destino = seq_final[idx+1]
                nova_dist += matriz_dist.get(origem, {}).get(destino, 0.0)
                novo_tempo += matriz_tempo.get(origem, {}).get(destino, 0.0)
                
            # Permite estourar o tempo em até 20% para evitar criar um ônibus novo
            if novo_tempo > max_tempo * 1.2:
                continue
                
            dist_aumento = nova_dist - r.dist_km
            if dist_aumento < melhor_dist_aumento:
                melhor_dist_aumento = dist_aumento
                melhor_seq = seq_final
                melhor_cargas = cargas_sim
                melhor_tempo = novo_tempo
                
    if melhor_seq is not None:
        r.paradas = melhor_seq
        r.cargas_trecho = melhor_cargas + [0]
        r.carga_maxima = max(melhor_cargas)
        r.dist_km = round(r.dist_km + melhor_dist_aumento, 2)
        r.tempo_min = round(melhor_tempo, 2)
        r.viagens_atendidas.append(t)
        return True
        
    return False

def consolidar_rotas_pequenas(rotas: list[RotaMulti], matriz_dist: dict, matriz_tempo: dict, capacidade: int, max_tempo: float, limiar: int = 8) -> list[RotaMulti]:
    """
    Tenta eliminar rotas que têm pouquíssimos passageiros (<= limiar) distribuindo
    suas viagens para outras rotas existentes.
    """
    rotas_ativas = []
    
    # Ordena as rotas para tentar consolidar as menores primeiro
    rotas_ordenadas = sorted(rotas, key=lambda r: r.carga_maxima)
    
    for r in rotas_ordenadas:
        if r.carga_maxima <= limiar and len(rotas_ativas) > 0:
            # Tenta distribuir todas as viagens desta rota pequena nas rotas já ativas
            todas_inseridas = True
            copias_backup = [
                (other_r, list(other_r.paradas), list(other_r.cargas_trecho), other_r.carga_maxima, other_r.dist_km, other_r.tempo_min, list(other_r.viagens_atendidas))
                for other_r in rotas_ativas
            ]
            
            for t in r.viagens_atendidas:
                inserida = False
                for other_r in rotas_ativas:
                    if tentar_inserir_viagem(other_r, t, matriz_dist, matriz_tempo, capacidade, max_tempo):
                        inserida = True
                        break
                if not inserida:
                    todas_inseridas = False
                    break
                    
            if todas_inseridas:
                # Sucesso: A rota r foi eliminada e suas viagens foram distribuídas.
                # Recalcula custos das rotas que receberam novas viagens
                for other_r in rotas_ativas:
                    other_r.custo_brl = ONIBUS_GENERICO.custo_rota(other_r.dist_km)
                continue
            else:
                # Falha: restaura backup
                for other_r, paradas, cargas, carga_max, dist, tempo, viagens in copias_backup:
                    other_r.paradas = paradas
                    other_r.cargas_trecho = cargas
                    other_r.carga_maxima = carga_max
                    other_r.dist_km = dist
                    other_r.tempo_min = tempo
                    other_r.viagens_atendidas = viagens
                rotas_ativas.append(r)
        else:
            rotas_ativas.append(r)
            
    return sorted(rotas_ativas, key=lambda r: r.carga_maxima, reverse=True)


def clarke_wright_multi_ovrp(
    nos: list[str],
    matriz_dist: dict,
    matriz_tempo: dict,
    viagens: list[dict],
    deposito: str = "UNIVASF Campus Petrolina",
    capacidade: int = 48,
    modelo: ModeloOnibus = ONIBUS_GENERICO,
    lam: Optional[float] = None,
    conforto: Optional[int] = None,
    max_tempo: float = 70.0,
    verbose: bool = True,
) -> tuple[list[RotaMulti], float]:
    """
    Roda a heurística Clarke-Wright Multi-Objetivo para encontrar as rotas.
    Busca automaticamente o melhor lambda se não for fornecido.
    """
    if conforto is None:
        conforto = modelo.capacidade_conforto or 36

    lambdas = [lam] if lam is not None else [
        round(0.1 + i * 0.1, 1) for i in range(20)
    ]

    melhor_rotas = None
    melhor_custo = float("inf")
    melhor_lam = 1.0

    for l in lambdas:
        viagens_restantes = list(viagens)
        remaining_boardings = set(t["embarque"] for t in viagens if t["embarque"] != deposito)

        rotas_l = []
        while remaining_boardings or any(t["embarque"] in remaining_boardings for t in viagens_restantes):
            n_restantes_antes = len(viagens_restantes)
            
            r = construir_rota_multi_objetivo(
                remaining_boardings=remaining_boardings,
                viagens_restantes=viagens_restantes,
                matriz_dist=matriz_dist,
                matriz_tempo=matriz_tempo,
                deposito=deposito,
                capacidade=capacidade,
                conforto=conforto,
                modelo=modelo,
                max_tempo=max_tempo,
                lam=l
            )
            
            if len(r.paradas) <= 1:
                break
                
            rotas_l.append(r)

            if len(viagens_restantes) == n_restantes_antes:
                break

        # Consolidar rotas pequenas antes de avaliar custo total
        rotas_l = consolidar_rotas_pequenas(rotas_l, matriz_dist, matriz_tempo, capacidade, max_tempo, limiar=8)

        # Atualiza ids das rotas após consolidação
        for idx, r in enumerate(rotas_l):
            r.id = idx + 1

        custo_l = calcular_custo_total_multi(rotas_l)

        if verbose:
            print(f"  [Multi-CW] lam={l:.1f} -> {len(rotas_l)} veiculos | R${custo_l:.2f} | {sum(r.dist_km for r in rotas_l):.1f} km")

        if custo_l < melhor_custo:
            melhor_custo = custo_l
            melhor_rotas = rotas_l
            melhor_lam = l

    return melhor_rotas or [], melhor_lam
