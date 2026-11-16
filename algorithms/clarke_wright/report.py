"""Text report and persistence of the Clarke-Wright solution.

The printed text and the JSON keys stay in pt-BR: they are the report output.
"""

import json
from datetime import datetime

from utils.fleet import load_fleet

from .constants import INF
from .evaluation import evaluate_attendance
from .metrics import route_path, _time_limit_text
from .model import Attendance, Context, Route
from .objective import _obj_total
from .scenario import ROOT


def _status(route: Route, ctx: Context) -> str:
    """Report markers. They refer to the ALLOCATED LOAD (the algorithm one)."""
    marks = []
    if route.load > ctx.capacity:
        marks.append("[ALOCADA ACIMA DA CAP.]")
    elif route.load >= ctx.capacity:
        marks.append("[ALOCADA CHEIA]")
    if route.time_minutes > ctx.max_time:
        marks.append("[ACIMA DO TEMPO]")
    return " ".join(marks)


def _pairs_text(pairs: tuple, limit: int = 10) -> str:
    """Short list of the served pairs: "12->2=1, 22->2=1"."""
    items = [f"{o}->{d}={q}" for o, d, q in pairs[:limit]]
    if len(pairs) > limit:
        items.append(f"(+{len(pairs) - limit})")
    return ", ".join(items)


def print_solution(
    routes: list[Route],
    ctx: Context,
    label: str,
    lam: float,
    attendance: Attendance | None = None,
) -> None:
    if attendance is None:
        attendance = evaluate_attendance(routes, ctx)

    total_cost = _obj_total(routes)
    total_distance = sum(r.distance_km for r in routes)
    allocated = sum(r.load for r in routes)
    served = sum(r.passengers for r in routes)
    allocated_occupancy = (
        allocated / (len(routes) * ctx.capacity) * 100 if routes else 0.0
    )
    real_occupancy = (attendance.peak_load / ctx.capacity * 100) if ctx.capacity else 0.0
    cost_per_passenger = total_cost / served if served else 0.0
    full_routes = sum(1 for r in routes if r.load >= ctx.capacity)
    longest_time = max((r.time_minutes for r in routes), default=0)
    over_time = sum(1 for r in routes if r.time_minutes > ctx.max_time)

    print(f"\n{'=' * 65}")
    print(f"SOLUCAO CLARKE-WRIGHT OVRP  |  {label}  |  lam = {lam}")
    print(f"Depósito de referência: {ctx.depot}")
    print(f"Origens permitidas: {ctx.origins or (ctx.depot,)}")
    print(f"Destinos permitidos: {ctx.destinations or 'livre'}")
    print(f"Modelo    : {ctx.bus_model.name} | R${ctx.bus_model.cost_per_km:.4f}/km")
    print(
        f"Restrições: {ctx.restrictions.key} "
        f"(capacidade={'sim' if ctx.restrictions.capacity else 'não'}, "
        f"tempo={'sim' if ctx.restrictions.time else 'não'})"
    )
    print(f"Capacidade: {ctx.capacity} máx")
    print(
        f"Tempo     : limite {_time_limit_text(ctx.max_time)} | "
        f"maior rota {longest_time} min"
    )
    print(f"{'=' * 65}")
    print(f"  Veículos utilizados  : {len(routes)}")
    print(f"  Demanda total        : {attendance.total_demand} pax")
    print(
        f"  Demanda alocada      : {allocated} "
        f"({attendance.allocated_pct:.0f}%)  [carga estática; não é atendimento]"
    )
    print(
        f"  Passageiros atendidos: {served} "
        f"({attendance.served_pct:.0f}%)  [simulação]"
    )
    print(f"  Demanda não atendida : {attendance.unserved} pax")
    print(f"  Distância total      : {total_distance:.1f} km")
    print(f"  Custo total (diesel + motorista): R${total_cost:.2f}")
    print(
        f"  Custo médio/veículo  : "
        f"R${total_cost / max(1, len(routes)):.2f}"
    )
    print(f"  Custo por pax atend. : R${cost_per_passenger:.2f}")
    print(f"  Ocupação alocada     : {allocated_occupancy:.0f}% da capacidade")
    print(
        f"  Ocupação real (pico) : "
        f"{attendance.peak_load}/{ctx.capacity} ({real_occupancy:.0f}%)"
    )
    print(
        f"  Rotas com aloc. cheia: {full_routes}/{len(routes)} "
        "(carga alocada = capacidade)"
    )
    print(f"  Rotas acima do tempo : {over_time}/{len(routes)}")
    print()

    for i, route in enumerate(sorted(routes, key=lambda r: -r.load), 1):
        pct = round(route.load / ctx.capacity * 100)
        filled = min(pct, 100)
        bar = "#" * (filled // 5) + "." * (20 - filled // 5)
        status = _status(route, ctx)

        print(
            f"  Ônibus {i:02d}  [{bar}] {pct:3d}%  "
            f"aloc {route.load:3d}/{ctx.capacity} | "
            f"pax {route.passengers:3d} | pico {route.peak_load:3d}  "
            f"{route.time_minutes}/{_time_limit_text(ctx.max_time)}  "
            f"{route.distance_km:.1f} km  R${route.cost_brl:.2f}  {status}"
        )

        route_text = "    " + " -> ".join(
            str(p) for p in route_path(route, ctx)
        )
        if len(route_text) > 130:
            route_text = route_text[:127] + "..."
        print(route_text)
        if route.pairs:
            print(f"    atende: {_pairs_text(route.pairs)}")
        else:
            print("    atende: nenhum par origem->destino cabe na rota")
        print()


def save_result(
    routes: list[Route],
    ctx: Context,
    label: str,
    lam: float,
    attendance: Attendance | None = None,
) -> None:
    if attendance is None:
        attendance = evaluate_attendance(routes, ctx)

    output_dir = ROOT / "algorithms" / "output"
    output_dir.mkdir(exist_ok=True)

    outcome = {
        "algoritmo": "Clarke-Wright OVRP (Pichpibul & Kawtummachai, 2013)",
        "rotulo": label,
        "deposito": ctx.depot,
        "origens_permitidas": list(ctx.origins or (ctx.depot,)),
        "destinos_permitidos": list(ctx.destinations) if ctx.destinations else None,
        "sentido": ctx.sense,
        "lambda": lam,
        "restricoes": ctx.restrictions.key,
        "capacidade": ctx.capacity,
        "limite_tempo": None if ctx.max_time == INF else ctx.max_time,
        "modelo_onibus": {
            "nome": ctx.bus_model.name,
            "capacidade": ctx.bus_model.capacity,
            "consumo_km_l": ctx.bus_model.km_per_liter,
            "custo_litro": ctx.bus_model.diesel_price,
            "custo_por_km": ctx.bus_model.cost_per_km,
        },
        "gerado_em": datetime.now().isoformat(),
        "num_veiculos": len(routes),
        "dist_total_km": round(sum(r.distance_km for r in routes), 2),
        "custo_total_brl": round(sum(r.cost_brl for r in routes), 2),
        # CVRP projection (one demand per node) vs. the attendance measured by
        # the boarding/alighting simulation. The two numbers differ by
        # construction; see the module docstring.
        "demanda_total": attendance.total_demand,
        "demanda_alocada": attendance.allocated,
        "demanda_alocada_pct": round(attendance.allocated_pct, 1),
        "pax_atendidos": attendance.served,
        "pax_atendidos_pct": round(attendance.served_pct, 1),
        "demanda_nao_atendida": attendance.unserved,
        "pico_max": attendance.peak_load,
        "pares_atendidos": [
            {"origem": o, "destino": d, "pax": q}
            for o, d, q in attendance.served_pairs
        ],
        "rotas": [
            {
                "id": i + 1,
                "paradas": r.stops,
                "origem": route_path(r, ctx)[0],
                "destino": route_path(r, ctx)[-1],
                "percurso": list(route_path(r, ctx)),
                "carga": r.load,
                "pax_atendido": r.passengers,
                "pico": r.peak_load,
                "pares": [
                    {"origem": o, "destino": d, "pax": q}
                    for o, d, q in r.pairs
                ],
                "dist_km": r.distance_km,
                "tempo_min": r.time_minutes,
                "custo_brl": r.cost_brl,
            }
            for i, r in enumerate(routes)
        ],
    }

    file_name = "".join(
        c if c.isalnum() or c in "-_" else "_" for c in label.lower()
    )
    output_path = output_dir / f"cw_ovrp_{file_name}.json"
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(outcome, f, ensure_ascii=False, indent=2)

    print(f"[clarke_wright] Resultado salvo em: {output_path}")


def print_fleet() -> None:
    """List fleet.csv (what the algorithm uses as reference)."""
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
