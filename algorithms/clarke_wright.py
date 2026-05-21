"""
clarke_wright.py
----------------
Implementação do algoritmo Clarke-Wright para o problema
OVRP (Open Vehicle Routing Problem) do transporte universitário UNIVASF.

Os ônibus partem do depósito, percorrem as paradas e FICAM no campus
destino — não retornam ao depósito. Isso caracteriza o OVRP.

Baseado em:
  Pichpibul, T. & Kawtummachai, R. (2013). A Heuristic Approach Based
  on Clarke-Wright Algorithm for Open Vehicle Routing Problem.
  The Scientific World Journal, Article ID 874349.
  https://onlinelibrary.wiley.com/doi/10.1155/2013/874349

  Clarke, G. & Wright, J.W. (1964). Scheduling of vehicles from a
  central depot to a number of delivery points. Operations Research,
  12(4), 568–581.
  https://www.jstor.org/stable/167703
  
Procedimentos implementados (cf. artigo):
  CW-1 : Fórmula OVRP modificada com parâmetro λ
  CW-2 : Construção de rota aberta (sem retorno ao depósito)
  CW-3 : Post-improvement (2-opt, shift 1-0, swap 1-1)

Uso:
    python clarke_wright.py --turno manha_1 --capacidade 48 --csv data/viagens.csv
    python clarke_wright.py --turno tarde_1 --lambda-min 0.5 --lambda-max 1.5 --salvar
"""

import argparse
import random
import math
from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from utils.fleet import ModeloOnibus, ONIBUS_GENERICO, imprimir_frota
from utils.loader import carregar_tudo
from utils.distance_matrix import (
    carregar_stops_json,
    construir_matriz,
    construir_matriz_fallback,
    filtrar_paradas,
)

# ── Constantes ────────────────────────────────────────────────────────────────
DEPOSITO_PADRAO  = "UNIVASF Campus Petrolina"
LAMBDA_MIN       = 0.1    # range de λ conforme artigo (Tabela 1)
LAMBDA_MAX       = 2.0
LAMBDA_PASSO     = 0.1
ITER_TWO_PHASE   = 5000   # iterações da two-phase selection (artigo: 5000)
ITER_POSTIMPROVE = 500    # iterações sem melhora para parar post-improvement

INF = float("inf")


# ── Estruturas de dados ───────────────────────────────────────────────────────

@dataclass
class Saving:
    """Par (i, j) com o valor de economia calculado."""
    i:     str
    j:     str
    valor: float

    def __lt__(self, other):
        return self.valor > other.valor  # ordenação decrescente


@dataclass
class Rota:
    """
    Rota aberta: depot → p1 → p2 → ... → pn  (sem retorno ao depósito).
    """
    paradas:    list[str] = field(default_factory=list)
    carga:      int       = 0       # passageiros transportados
    dist_km:    float     = 0.0     # distância total da rota (km)
    custo_brl:  float     = 0.0     # custo de combustível (R$)

    def primeira(self) -> str:
        return self.paradas[0]

    def ultima(self) -> str:
        return self.paradas[-1]

    def __repr__(self) -> str:
        return (
            f"Rota({len(self.paradas)} paradas | "
            f"{self.carga} pass. | "
            f"{self.dist_km:.1f} km | "
            f"R${self.custo_brl:.2f})"
        )


# ── Fórmula de savings OVRP (CW-1) ───────────────────────────────────────────

def calcular_savings_ovrp(
    paradas: list[str],
    matriz:  dict,
    deposito: str,
    lam:     float,
) -> list[Saving]:
    """
    Fórmula OVRP modificada (equação 5 do artigo):

        s(i,j) = c(depot, j) - λ · c(i, j)

    Diferença em relação ao CVRP: remove o termo c(i, depot)
    pois o veículo não retorna ao depósito após visitar i.

    Args:
        paradas  : lista de paradas (sem o depósito)
        matriz   : matriz de distâncias
        deposito : nó de partida da frota
        lam      : parâmetro de forma λ ∈ [0.1, 2.0]
    """
    savings = []
    for idx_i in range(len(paradas)):
        for idx_j in range(idx_i + 1, len(paradas)):
            pi, pj = paradas[idx_i], paradas[idx_j]

            c_depot_j = matriz.get(deposito, {}).get(pj, INF)
            c_i_j     = matriz.get(pi, {}).get(pj, INF)

            if c_depot_j == INF or c_i_j == INF:
                continue

            # Equação 5 do artigo (OVRP com λ)
            s = c_depot_j - lam * c_i_j
            savings.append(Saving(i=pi, j=pj, valor=round(s, 6)))

    savings.sort()  # decrescente via __lt__
    return savings


# ── Custo de rota (OVRP: sem retorno ao depósito) ────────────────────────────

def _custo_dist(paradas: list[str], matriz: dict, deposito: str) -> float:
    """
    Distância total da rota aberta: depot → p1 → p2 → ... → pn.
    Não inclui retorno ao depósito (OVRP).
    """
    if not paradas:
        return 0.0
    dist = matriz.get(deposito, {}).get(paradas[0], 0.0)
    for k in range(len(paradas) - 1):
        dist += matriz.get(paradas[k], {}).get(paradas[k + 1], 0.0)
    return round(dist, 4)


def _atualizar_custo(rota: Rota, matriz: dict, deposito: str,
                     modelo: ModeloOnibus) -> Rota:
    """Recalcula dist_km e custo_brl da rota."""
    rota.dist_km  = _custo_dist(rota.paradas, matriz, deposito)
    rota.custo_brl = modelo.custo_rota(rota.dist_km)
    return rota


# ── Construção OVRP (CW-2): rota aberta em dois sentidos ─────────────────────

def _melhor_direcao(
    paradas: list[str],
    matriz:  dict,
    deposito: str,
) -> list[str]:
    """
    Procedimento CW-2 do artigo: testa as duas direções possíveis da rota
    aberta (forward e reverse) e retorna a de menor distância.

    Em OVRP:
      forward : depot → p1 → p2 → ... → pn   (distância D_f)
      reverse : depot → pn → p(n-1) → ... → p1 (distância D_r)
    """
    dist_f = _custo_dist(paradas,              matriz, deposito)
    dist_r = _custo_dist(list(reversed(paradas)), matriz, deposito)
    return paradas if dist_f <= dist_r else list(reversed(paradas))


# ── Fusão de rotas ─────────────────────────────────────────────────────────────

def _fundir(
    savings:    list[Saving],
    paradas_ativas: set[str],
    matriz:     dict,
    demanda:    dict,
    deposito:   str,
    capacidade: int,
    modelo:     ModeloOnibus,
) -> list[Rota]:
    """
    Procedimento de fusão (route merging) do Clarke-Wright paralelo.

    Para cada saving s(i,j) em ordem decrescente:
      - Se i e j estão em rotas diferentes
      - Se a fusão não viola a capacidade
      - Se i é extremo (início ou fim) da sua rota
      - Se j é extremo da sua rota
      → funde as rotas
    """
    # Solução inicial: uma rota por parada
    rotas: dict[str, Rota] = {}
    extremo: dict[str, Rota] = {}   # extremo → rota que o contém

    for p in paradas_ativas:
        carga = demanda.get(p, {}).get("boarding", 0)
        r = Rota(paradas=[p], carga=carga)
        _atualizar_custo(r, matriz, deposito, modelo)
        rotas[id(r)] = r
        extremo[p] = r

    for s in savings:
        ri = extremo.get(s.i)
        rj = extremo.get(s.j)

        if ri is None or rj is None or ri is rj:
            continue
        if ri.carga + rj.carga > capacidade:
            continue

        nova_ordem = None

        if ri.ultima() == s.i and rj.primeira() == s.j:
            nova_ordem = ri.paradas + rj.paradas
        elif rj.ultima() == s.j and ri.primeira() == s.i:
            nova_ordem = rj.paradas + ri.paradas
        elif ri.ultima() == s.i and rj.ultima() == s.j:
            nova_ordem = ri.paradas + list(reversed(rj.paradas))
        elif ri.primeira() == s.i and rj.primeira() == s.j:
            nova_ordem = list(reversed(ri.paradas)) + rj.paradas

        if nova_ordem is None:
            continue

        # Aplica CW-2: escolhe a melhor direção da rota aberta
        nova_ordem = _melhor_direcao(nova_ordem, matriz, deposito)

        nova_rota = Rota(
            paradas = nova_ordem,
            carga   = ri.carga + rj.carga,
        )
        _atualizar_custo(nova_rota, matriz, deposito, modelo)

        # Remove rotas antigas
        rotas.pop(id(ri), None)
        rotas.pop(id(rj), None)
        for p in ri.paradas + rj.paradas:
            extremo.pop(p, None)

        # Registra nova rota
        rotas[id(nova_rota)] = nova_rota
        extremo[nova_rota.primeira()] = nova_rota
        extremo[nova_rota.ultima()]   = nova_rota

    return list(rotas.values())


# ── Two-Phase Selection (CW-2 do artigo) ─────────────────────────────────────

def _roulette_wheel(savings: list[Saving], T: int) -> list[Saving]:
    """
    Seleção por roleta sobre os T melhores savings (seção 2.3 do artigo).

    Reconstrói a lista de savings embaralhando probabilisticamente
    os T melhores a cada iteração — explora ordens de fusão diferentes.
    """
    if len(savings) <= 1:
        return savings

    nova_lista = []
    restantes = list(savings)

    while restantes:
        t = min(T, len(restantes))
        candidatos = restantes[:t]

        soma = sum(abs(s.valor) for s in candidatos)
        if soma == 0:
            escolhido = random.choice(candidatos)
        else:
            r = random.random()
            acumulado = 0.0
            escolhido = candidatos[-1]
            for s in candidatos:
                acumulado += abs(s.valor) / soma
                if r <= acumulado:
                    escolhido = s
                    break

        nova_lista.append(escolhido)
        restantes.remove(escolhido)

    return nova_lista


def two_phase_selection(
    savings:    list[Saving],
    paradas_ativas: set[str],
    matriz:     dict,
    demanda:    dict,
    deposito:   str,
    capacidade: int,
    modelo:     ModeloOnibus,
    iteracoes:  int = ITER_TWO_PHASE,
) -> list[Rota]:
    """
    Procedimento CW-2 do artigo: iterativamente reordena a lista de savings
    via roleta e verifica se a nova solução melhora a atual.
    """
    melhor_rotas = _fundir(savings, paradas_ativas, matriz, demanda,
                           deposito, capacidade, modelo)
    melhor_custo = sum(r.custo_brl for r in melhor_rotas)

    savings_atual = list(savings)

    for _ in range(iteracoes):
        T = random.randint(3, min(20, len(savings_atual)))
        nova_ordem = _roulette_wheel(savings_atual, T)
        novas_rotas = _fundir(nova_ordem, paradas_ativas, matriz, demanda,
                              deposito, capacidade, modelo)
        novo_custo = sum(r.custo_brl for r in novas_rotas)

        if novo_custo < melhor_custo:
            melhor_custo  = novo_custo
            melhor_rotas  = novas_rotas
            savings_atual = nova_ordem

    return melhor_rotas


# ── Post-improvement (CW-3 do artigo) ────────────────────────────────────────

def _custo_total(rotas: list[Rota]) -> float:
    return sum(r.custo_brl for r in rotas)


def _2opt_rota(rota: Rota, matriz: dict, deposito: str,
               modelo: ModeloOnibus) -> Rota:
    """
    2-opt intra-rota: inverte segmentos internos e mantém o melhor.
    Aplica CW-2 (melhor direção) após cada melhoria.
    """
    melhorou = True
    paradas  = list(rota.paradas)

    while melhorou:
        melhorou = False
        for i in range(len(paradas) - 1):
            for j in range(i + 2, len(paradas)):
                nova = paradas[:i+1] + list(reversed(paradas[i+1:j+1])) + paradas[j+1:]
                nova = _melhor_direcao(nova, matriz, deposito)
                d_nova = _custo_dist(nova, matriz, deposito)
                if d_nova < _custo_dist(paradas, matriz, deposito) - 1e-6:
                    paradas  = nova
                    melhorou = True

    rota.paradas = paradas
    return _atualizar_custo(rota, matriz, deposito, modelo)


def _shift_10(
    rotas: list[Rota], matriz: dict, deposito: str,
    capacidade: int, modelo: ModeloOnibus,
) -> list[Rota]:
    """
    Shift 1-0: move uma parada de uma rota para outra.
    Aceita somente se reduzir o custo total.
    """
    melhorou = True
    while melhorou:
        melhorou = False
        for a in range(len(rotas)):
            for pos_i in range(len(rotas[a].paradas)):
                parada = rotas[a].paradas[pos_i]

                for b in range(len(rotas)):
                    if a == b:
                        continue
                    if rotas[b].carga + 1 > capacidade:
                        continue

                    custo_antes = rotas[a].custo_brl + rotas[b].custo_brl

                    # Testa inserção no início e fim da rota b
                    for pos_j in [0, len(rotas[b].paradas)]:
                        novas_a = list(rotas[a].paradas)
                        novas_a.pop(pos_i)
                        novas_b = list(rotas[b].paradas)
                        novas_b.insert(pos_j, parada)

                        if not novas_a:
                            continue  # não cria rota vazia

                        novas_a = _melhor_direcao(novas_a, matriz, deposito)
                        novas_b = _melhor_direcao(novas_b, matriz, deposito)

                        dist_a = _custo_dist(novas_a, matriz, deposito)
                        dist_b = _custo_dist(novas_b, matriz, deposito)
                        custo_depois = modelo.custo_rota(dist_a) + modelo.custo_rota(dist_b)

                        if custo_depois < custo_antes - 1e-6:
                            rotas[a].paradas   = novas_a
                            rotas[a].dist_km   = dist_a
                            rotas[a].custo_brl = modelo.custo_rota(dist_a)

                            rotas[b].paradas   = novas_b
                            rotas[b].dist_km   = dist_b
                            rotas[b].custo_brl = modelo.custo_rota(dist_b)

                            melhorou = True
                            break
                    if melhorou:
                        break
                if melhorou:
                    break
            if melhorou:
                break

    return rotas


def _swap_11(
    rotas: list[Rota], matriz: dict, deposito: str,
    capacidade: int, modelo: ModeloOnibus,
) -> list[Rota]:
    """
    Swap 1-1: troca uma parada entre duas rotas.
    Aceita somente se não violar capacidade e reduzir custo.
    """
    melhorou = True
    while melhorou:
        melhorou = False
        for a in range(len(rotas)):
            for b in range(a + 1, len(rotas)):
                for pos_i in range(len(rotas[a].paradas)):
                    for pos_j in range(len(rotas[b].paradas)):
                        pi = rotas[a].paradas[pos_i]
                        pj = rotas[b].paradas[pos_j]

                        custo_antes = rotas[a].custo_brl + rotas[b].custo_brl

                        novas_a = list(rotas[a].paradas)
                        novas_b = list(rotas[b].paradas)
                        novas_a[pos_i] = pj
                        novas_b[pos_j] = pi

                        novas_a = _melhor_direcao(novas_a, matriz, deposito)
                        novas_b = _melhor_direcao(novas_b, matriz, deposito)

                        dist_a = _custo_dist(novas_a, matriz, deposito)
                        dist_b = _custo_dist(novas_b, matriz, deposito)
                        custo_depois = modelo.custo_rota(dist_a) + modelo.custo_rota(dist_b)

                        if custo_depois < custo_antes - 1e-6:
                            rotas[a].paradas   = novas_a
                            rotas[a].dist_km   = dist_a
                            rotas[a].custo_brl = modelo.custo_rota(dist_a)

                            rotas[b].paradas   = novas_b
                            rotas[b].dist_km   = dist_b
                            rotas[b].custo_brl = modelo.custo_rota(dist_b)

                            melhorou = True
                            break
                    if melhorou:
                        break
                if melhorou:
                    break
            if melhorou:
                break

    return rotas


def post_improvement(
    rotas:      list[Rota],
    matriz:     dict,
    deposito:   str,
    capacidade: int,
    modelo:     ModeloOnibus,
    max_iter_sem_melhora: int = ITER_POSTIMPROVE,
) -> list[Rota]:
    """
    Procedimento CW-3 do artigo: aplica operadores de busca local
    até não haver mais melhorias.

    Operadores (com igual probabilidade, conforme Tabela 1 do artigo):
      - 2-opt intra-rota
      - shift 1-0 inter-rotas
      - swap 1-1 inter-rotas
    """
    rotas = deepcopy(rotas)
    melhor_custo = _custo_total(rotas)
    iter_sem_melhora = 0

    operadores = [
        lambda r: [_2opt_rota(x, matriz, deposito, modelo) for x in r],
        lambda r: _shift_10(r, matriz, deposito, capacidade, modelo),
        lambda r: _swap_11(r, matriz, deposito, capacidade, modelo),
    ]

    while iter_sem_melhora < max_iter_sem_melhora:
        op = random.choice(operadores)
        rotas_novas = op(rotas)
        novo_custo  = _custo_total(rotas_novas)

        if novo_custo < melhor_custo - 1e-6:
            melhor_custo     = novo_custo
            rotas            = rotas_novas
            iter_sem_melhora = 0
        else:
            iter_sem_melhora += 1

    return rotas


# ── Algoritmo principal ───────────────────────────────────────────────────────

def clarke_wright_ovrp(
    nos:        list[str],
    matriz:     dict,
    demanda:    dict,
    deposito:   str          = DEPOSITO_PADRAO,
    capacidade: int          = 48,
    modelo:     ModeloOnibus = ONIBUS_GENERICO,
    lam:        Optional[float] = None,
    usar_two_phase: bool     = True,
    usar_postimprove: bool   = True,
    verbose:    bool         = True,
) -> tuple[list[Rota], float]:
    """
    Executa o Clarke-Wright OVRP completo (CW-1 + CW-2 + CW-3).

    Se λ não for fornecido, testa todos os valores de 0.1 a 2.0
    (incremento 0.1) e usa o que gerar menor custo total — conforme
    procedimento CW-1 do artigo (Tabela 1).

    Retorna:
        (rotas, lambda_usado)
    """
    paradas_ativas = {
        p for p in nos
        if p != deposito and demanda.get(p, {}).get("boarding", 0) > 0
    }

    if not paradas_ativas:
        if verbose:
            print("[clarke_wright] Nenhuma parada com demanda para este turno.")
        return [], 0.0

    if verbose:
        print(f"\n[CW-OVRP] {len(paradas_ativas)} paradas | "
              f"depósito: {deposito} | cap: {capacidade} | modelo: {modelo.nome}")

    # ── CW-1: testa múltiplos λ e guarda o melhor ────────────────────────────
    lambdas = [lam] if lam is not None else [
        round(LAMBDA_MIN + i * LAMBDA_PASSO, 1)
        for i in range(round((LAMBDA_MAX - LAMBDA_MIN) / LAMBDA_PASSO) + 1)
    ]

    melhor_rotas = None
    melhor_custo = INF
    melhor_lam   = lambdas[0]

    for l in lambdas:
        savings = calcular_savings_ovrp(list(paradas_ativas), matriz, deposito, l)

        if usar_two_phase:
            rotas_l = two_phase_selection(
                savings, paradas_ativas, matriz, demanda,
                deposito, capacidade, modelo,
                iteracoes=ITER_TWO_PHASE,
            )
        else:
            rotas_l = _fundir(savings, paradas_ativas, matriz, demanda,
                              deposito, capacidade, modelo)

        custo_l = _custo_total(rotas_l)
        if verbose:
            print(f"  lam={l:.1f} -> {len(rotas_l)} veiculos | "
                  f"R${custo_l:.2f} | {sum(r.dist_km for r in rotas_l):.1f} km")

        if custo_l < melhor_custo:
            melhor_custo = custo_l
            melhor_rotas = rotas_l
            melhor_lam   = l

    if verbose:
        print(f"\n  [OK] Melhor lam = {melhor_lam} | custo R${melhor_custo:.2f}")

    # ── CW-3: post-improvement sobre a melhor solução ───────────────────────
    if usar_postimprove and melhor_rotas:
        if verbose:
            print("  Aplicando post-improvement (2-opt / shift / swap)...")
        melhor_rotas = post_improvement(
            melhor_rotas, matriz, deposito, capacidade, modelo
        )
        custo_pos = _custo_total(melhor_rotas)
        if verbose:
            reducao = round((melhor_custo - custo_pos) / melhor_custo * 100, 2)
            print(f"  [OK] Apos post-improvement: R${custo_pos:.2f} "
                  f"(-{reducao}%)")

    return melhor_rotas or [], melhor_lam


# ── Relatório ─────────────────────────────────────────────────────────────────

def imprimir_solucao(
    rotas:      list[Rota],
    deposito:   str,
    capacidade: int,
    modelo:     ModeloOnibus,
    turno:      str,
    lam:        float,
) -> None:
    custo_total = _custo_total(rotas)
    dist_total  = sum(r.dist_km for r in rotas)

    print(f"\n{'=' * 65}")
    print(f"SOLUCAO CLARKE-WRIGHT OVRP  |  Turno: {turno}  |  lam = {lam}")
    print(f"Depósito  : {deposito}")
    print(f"Modelo    : {modelo.nome}")
    print(f"Capacidade: {capacidade} pass. | R${modelo.custo_por_km:.4f}/km")
    print(f"{'=' * 65}")
    print(f"  Veículos utilizados  : {len(rotas)}")
    print(f"  Distância total      : {dist_total:.1f} km")
    print(f"  Custo total (comb.)  : R${custo_total:.2f}")
    print(f"  Custo médio/veículo  : R${custo_total / max(1, len(rotas)):.2f}")
    print()

    for i, rota in enumerate(sorted(rotas, key=lambda r: -r.carga), 1):
        pct    = round(rota.carga / capacidade * 100)
        barra  = "#" * (pct // 5) + "." * (20 - pct // 5)
        status = "[LOTADO]" if pct >= 100 else ("[alto]" if pct >= 80 else "")

        print(f"  Ônibus {i:02d}  [{barra}] {pct:3d}%  "
              f"({rota.carga}/{capacidade} pass.)  "
              f"{rota.dist_km:.1f} km  R${rota.custo_brl:.2f}  {status}")

        rota_str = f"    {deposito} -> " + " -> ".join(rota.paradas)
        if len(rota_str) > 130:
            rota_str = rota_str[:127] + "..."
        print(rota_str)
        print()


def salvar_resultado(
    rotas:    list[Rota],
    turno:    str,
    deposito: str,
    modelo:   ModeloOnibus,
    lam:      float,
) -> None:
    import json
    from datetime import datetime

    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)

    resultado = {
        "algoritmo":    "Clarke-Wright OVRP (Pichpibul & Kawtummachai, 2013)",
        "turno":        turno,
        "deposito":     deposito,
        "lambda":       lam,
        "modelo_onibus": {
            "nome":         modelo.nome,
            "capacidade":   modelo.capacidade,
            "consumo_km_l": modelo.consumo_km_l,
            "custo_litro":  modelo.custo_litro,
            "custo_por_km": modelo.custo_por_km,
        },
        "gerado_em":      datetime.now().isoformat(),
        "num_veiculos":   len(rotas),
        "dist_total_km":  round(sum(r.dist_km  for r in rotas), 2),
        "custo_total_brl": round(sum(r.custo_brl for r in rotas), 2),
        "rotas": [
            {
                "id":        i + 1,
                "paradas":   r.paradas,
                "carga":     r.carga,
                "dist_km":   r.dist_km,
                "custo_brl": r.custo_brl,
            }
            for i, r in enumerate(rotas)
        ],
    }

    arquivo = output_dir / f"cw_ovrp_{turno}.json"
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"[clarke_wright] Resultado salvo em: {arquivo}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Clarke-Wright OVRP — Transporte UNIVASF"
    )
    parser.add_argument("--turno",       default="manha_1",
                        help="Slug do turno (ex: manha_1)")
    parser.add_argument("--capacidade",  type=int, default=48,
                        help="Capacidade máxima do veículo (passageiros)")
    parser.add_argument("--deposito",    default=DEPOSITO_PADRAO,
                        help="Parada de origem (depósito)")
    parser.add_argument("--csv",         default=None,
                        help="Caminho do CSV exportado do Supabase")
    parser.add_argument("--metrica",     default="distance",
                        choices=["distance", "estimated_travel_time"],
                        help="Métrica da matriz (distance ou tempo)")
    parser.add_argument("--lambda-val",  type=float, default=None,
                        help="Valor fixo de λ (padrão: testa 0.1–2.0)")
    parser.add_argument("--sem-two-phase",  action="store_true",
                        help="Desativa two-phase selection (CW-1 apenas)")
    parser.add_argument("--sem-postimprove", action="store_true",
                        help="Desativa post-improvement (CW-1+CW-2 apenas)")
    parser.add_argument("--salvar",      action="store_true",
                        help="Salva resultado em output/")
    parser.add_argument("--frota",       action="store_true",
                        help="Exibe modelos de ônibus cadastrados")
    args = parser.parse_args()

    if args.frota:
        imprimir_frota()
        return

    # 1. Dados do formulário
    csv_path = Path(args.csv) if args.csv else None
    _, demand_total = carregar_tudo(csv_path) if csv_path else carregar_tudo()

    demanda_turno = demand_total.get(args.turno, {})
    if not demanda_turno:
        print(f"[erro] Nenhum dado para o turno '{args.turno}'. "
              f"Verifique o CSV.")
        return

    # 2. Matriz de distâncias
    stops = carregar_stops_json()
    if stops:
        nos, matriz = construir_matriz(stops, metrica=args.metrica)
        paradas_ativas = set(demanda_turno.keys()) | {args.deposito}
        nos, matriz = filtrar_paradas(nos, matriz, paradas_ativas)
    else:
        print("[aviso] Stops JSON não encontrados — usando fallback euclidiano.")
        paradas_ativas = set(demanda_turno.keys()) | {args.deposito}
        nos, matriz = construir_matriz_fallback(list(paradas_ativas))

    # 3. Executa CW-OVRP
    rotas, lam_usado = clarke_wright_ovrp(
        nos             = nos,
        matriz          = matriz,
        demanda         = demanda_turno,
        deposito        = args.deposito,
        capacidade      = args.capacidade,
        modelo          = ONIBUS_GENERICO,
        lam             = args.lambda_val,
        usar_two_phase  = not args.sem_two_phase,
        usar_postimprove= not args.sem_postimprove,
        verbose         = True,
    )

    # 4. Exibe resultado
    imprimir_solucao(
        rotas      = rotas,
        deposito   = args.deposito,
        capacidade = args.capacidade,
        modelo     = ONIBUS_GENERICO,
        turno      = args.turno,
        lam        = lam_usado,
    )

    if args.salvar:
        salvar_resultado(rotas, args.turno, args.deposito,
                         ONIBUS_GENERICO, lam_usado)


if __name__ == "__main__":
    main()
