"""Relatório textual e persistência da solução do Clarke-Wright."""

import json
from datetime import datetime

from utils.fleet import load_fleet

from .constants import INF
from .evaluation import avaliar_atendimento
from .metrics import _limite_texto
from .model import Atendimento, Contexto, Rota
from .objective import _obj_total
from .scenario import ROOT


def _situacao(rota: Rota, ctx: Contexto) -> str:
    """Marcadores do relatório. Referem-se à CARGA ALOCADA (a do algoritmo)."""
    marcas = []
    if rota.carga > ctx.capacidade:
        marcas.append("[ALOCADA ACIMA DA CAP.]")
    elif rota.carga >= ctx.capacidade:
        marcas.append("[ALOCADA CHEIA]")
    if rota.tempo_min > ctx.limite_tempo:
        marcas.append("[ACIMA DO TEMPO]")
    return " ".join(marcas)


def _pares_texto(pares: tuple, limite: int = 10) -> str:
    """Lista curta dos pares atendidos: "12->2=1, 22->2=1"."""
    itens = [f"{o}->{d}={q}" for o, d, q in pares[:limite]]
    if len(pares) > limite:
        itens.append(f"(+{len(pares) - limite})")
    return ", ".join(itens)


def imprimir_solucao(
    rotas: list[Rota],
    ctx: Contexto,
    rotulo: str,
    lam: float,
    atend: Atendimento | None = None,
) -> None:
    if atend is None:
        atend = avaliar_atendimento(rotas, ctx)

    custo_total = _obj_total(rotas)
    dist_total = sum(r.dist_km for r in rotas)
    alocada = sum(r.carga for r in rotas)
    atendida = sum(r.pax for r in rotas)
    ocup_aloc = (
        alocada / (len(rotas) * ctx.capacidade) * 100 if rotas else 0.0
    )
    ocup_real = (atend.pico / ctx.capacidade * 100) if ctx.capacidade else 0.0
    custo_pax = custo_total / atendida if atendida else 0.0
    n_cheias = sum(1 for r in rotas if r.carga >= ctx.capacidade)
    maior_tempo = max((r.tempo_min for r in rotas), default=0)
    fora_tempo = sum(1 for r in rotas if r.tempo_min > ctx.limite_tempo)

    print(f"\n{'=' * 65}")
    print(f"SOLUCAO CLARKE-WRIGHT OVRP  |  {rotulo}  |  lam = {lam}")
    print(f"Depósito  : {ctx.deposito}")
    print(f"Modelo    : {ctx.modelo.nome} | R${ctx.modelo.custo_por_km:.4f}/km")
    print(
        f"Restrições: {ctx.restricoes.chave} "
        f"(capacidade={'sim' if ctx.restricoes.capacidade else 'não'}, "
        f"tempo={'sim' if ctx.restricoes.tempo else 'não'})"
    )
    print(f"Capacidade: {ctx.capacidade} máx")
    print(
        f"Tempo     : limite {_limite_texto(ctx.limite_tempo)} | "
        f"maior rota {maior_tempo} min"
    )
    print(f"{'=' * 65}")
    print(f"  Veículos utilizados  : {len(rotas)}")
    print(f"  Demanda total        : {atend.demanda_total} pax")
    print(
        f"  Demanda alocada      : {alocada} "
        f"({atend.pct_alocada:.0f}%)  [projeção do CVRP]"
    )
    print(
        f"  Passageiros atendidos: {atendida} "
        f"({atend.pct_atendida:.0f}%)  [simulação]"
    )
    print(f"  Demanda não atendida : {atend.nao_atendida} pax")
    print(f"  Distância total      : {dist_total:.1f} km")
    print(f"  Custo total (comb.)  : R${custo_total:.2f}")
    print(
        f"  Custo médio/veículo  : "
        f"R${custo_total / max(1, len(rotas)):.2f}"
    )
    print(f"  Custo por pax atend. : R${custo_pax:.2f}")
    print(f"  Ocupação alocada     : {ocup_aloc:.0f}% da capacidade")
    print(
        f"  Ocupação real (pico) : "
        f"{atend.pico}/{ctx.capacidade} ({ocup_real:.0f}%)"
    )
    print(
        f"  Rotas com aloc. cheia: {n_cheias}/{len(rotas)} "
        "(carga alocada = capacidade)"
    )
    print(f"  Rotas acima do tempo : {fora_tempo}/{len(rotas)}")
    print()

    for i, rota in enumerate(sorted(rotas, key=lambda r: -r.carga), 1):
        pct = round(rota.carga / ctx.capacidade * 100)
        cheio = min(pct, 100)
        barra = "#" * (cheio // 5) + "." * (20 - cheio // 5)
        status = _situacao(rota, ctx)

        print(
            f"  Ônibus {i:02d}  [{barra}] {pct:3d}%  "
            f"aloc {rota.carga:3d}/{ctx.capacidade} | "
            f"pax {rota.pax:3d} | pico {rota.pico:3d}  "
            f"{rota.tempo_min}/{_limite_texto(ctx.limite_tempo)}  "
            f"{rota.dist_km:.1f} km  R${rota.custo_brl:.2f}  {status}"
        )

        rota_str = f"    {ctx.deposito} -> " + " -> ".join(
            str(p) for p in rota.paradas
        )
        if len(rota_str) > 130:
            rota_str = rota_str[:127] + "..."
        print(rota_str)
        if rota.pares:
            print(f"    atende: {_pares_texto(rota.pares)}")
        else:
            print("    atende: nenhum par origem->destino cabe na rota")
        print()


def salvar_resultado(
    rotas: list[Rota],
    ctx: Contexto,
    rotulo: str,
    lam: float,
    atend: Atendimento | None = None,
) -> None:
    if atend is None:
        atend = avaliar_atendimento(rotas, ctx)

    output_dir = ROOT / "algorithms" / "output"
    output_dir.mkdir(exist_ok=True)

    resultado = {
        "algoritmo": "Clarke-Wright OVRP (Pichpibul & Kawtummachai, 2013)",
        "rotulo": rotulo,
        "deposito": ctx.deposito,
        "sentido": ctx.sentido,
        "lambda": lam,
        "restricoes": ctx.restricoes.chave,
        "capacidade": ctx.capacidade,
        "limite_tempo": None if ctx.limite_tempo == INF else ctx.limite_tempo,
        "modelo_onibus": {
            "nome": ctx.modelo.nome,
            "capacidade": ctx.modelo.capacidade,
            "consumo_km_l": ctx.modelo.consumo_km_l,
            "custo_litro": ctx.modelo.custo_litro,
            "custo_por_km": ctx.modelo.custo_por_km,
        },
        "gerado_em": datetime.now().isoformat(),
        "num_veiculos": len(rotas),
        "dist_total_km": round(sum(r.dist_km for r in rotas), 2),
        "custo_total_brl": round(sum(r.custo_brl for r in rotas), 2),
        # Projeção do CVRP (uma demanda por nó) × atendimento medido pela
        # simulação de embarque/desembarque. Os dois números são diferentes
        # por construção; ver o docstring do módulo.
        "demanda_total": atend.demanda_total,
        "demanda_alocada": atend.alocada,
        "demanda_alocada_pct": round(atend.pct_alocada, 1),
        "pax_atendidos": atend.atendida,
        "pax_atendidos_pct": round(atend.pct_atendida, 1),
        "demanda_nao_atendida": atend.nao_atendida,
        "pico_max": atend.pico,
        "pares_atendidos": [
            {"origem": o, "destino": d, "pax": q}
            for o, d, q in atend.pares_atendidos
        ],
        "rotas": [
            {
                "id": i + 1,
                "paradas": r.paradas,
                "carga": r.carga,
                "pax_atendido": r.pax,
                "pico": r.pico,
                "pares": [
                    {"origem": o, "destino": d, "pax": q}
                    for o, d, q in r.pares
                ],
                "dist_km": r.dist_km,
                "tempo_min": r.tempo_min,
                "custo_brl": r.custo_brl,
            }
            for i, r in enumerate(rotas)
        ],
    }

    nome_arquivo = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in rotulo.lower()
    )
    arquivo = output_dir / f"cw_ovrp_{nome_arquivo}.json"
    with open(arquivo, "w", encoding="utf-8") as f:
        json.dump(resultado, f, ensure_ascii=False, indent=2)

    print(f"[clarke_wright] Resultado salvo em: {arquivo}")


def imprimir_frota() -> None:
    """Lista o fleet.csv (o que o algoritmo usa como referência)."""
    buses = load_fleet(ROOT / "fleet.csv")
    print(f"\n{'=' * 46}")
    print("FROTA  (fleet.csv)")
    print(f"{'=' * 46}")
    print(f"  {'id':>3} | {'lugares':>7} | {'tanque (L)':>10} | {'km/L':>5}")
    print(f"  {'-'*3} | {'-'*7} | {'-'*10} | {'-'*5}")
    for bus in buses:
        print(
            f"  {bus.id:>3} | {bus.passenger_capacity:>7} | "
            f"{bus.fuel_capacity:>10g} | {bus.km_autonomy_per_liter:>5g}"
        )
    print()
