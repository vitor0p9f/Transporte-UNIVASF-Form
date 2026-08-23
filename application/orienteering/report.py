from __future__ import annotations

from application.orienteering.models import FleetResult


def fleet_result_rows(result: FleetResult) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for plan in result.plans:
        visited_stops = len(plan.route_stops)
        rows.append(
            {
                "id do ônibus": plan.bus.id,
                "destino": plan.destination_label,
                "pasageiros atendidos": plan.simulation.served_passengers,
                "passageiros sem desembarque": plan.simulation.leftover_onboard_passengers,
                "pico de passageiros": plan.simulation.peak_load,
                "custo operacional (R$)": round(plan.simulation.total_cost, 2),
                "tempo_min": plan.simulation.travel_time_minutes,
                "distancia_km": round(plan.simulation.total_distance_km, 2),
                "paradas": visited_stops,
                "capacidade": plan.bus.passenger_capacity,
                "viável": plan.simulation.route_valid,
            }
        )

    return rows


def fleet_summary_row(result: FleetResult) -> dict[str, object]:
    total_passengers = sum(plan.simulation.served_passengers for plan in result.plans)
    total_residual = sum(plan.simulation.leftover_onboard_passengers for plan in result.plans)
    total_peak = max((plan.simulation.peak_load for plan in result.plans), default=0)
    total_cost = sum(plan.simulation.total_cost for plan in result.plans)
    total_time = sum(plan.simulation.travel_time_minutes for plan in result.plans)
    total_distance = sum(plan.simulation.total_distance_km for plan in result.plans)
    total_stops = sum(len(plan.route_stops) for plan in result.plans)

    return {
        "id do ônibus": "Σ",
        "destino": "",
        "pasageiros atendidos": total_passengers,
        "passageiros sem desembarque": total_residual,
        "pico de passageiros": total_peak,
        "custo operacional (R$)": round(total_cost, 2),
        "tempo_min": total_time,
        "distancia_km": round(total_distance, 2),
        "paradas": total_stops,
        "capacidade": "",
        "viável": "",
    }


def render_markdown_table(rows: list[dict[str, object]]) -> str:
    if not rows:
        return ""

    headers = list(rows[0].keys())
    matrix = [[str(row.get(header, "")) for header in headers] for row in rows]
    widths = [len(header) for header in headers]

    for row in matrix:
        for index, cell in enumerate(row):
            widths[index] = max(widths[index], len(cell))

    def render_row(cells: list[str]) -> str:
        return "| " + " | ".join(cell.ljust(widths[index]) for index, cell in enumerate(cells)) + " |"

    lines = [render_row(headers), render_row(["-" * width for width in widths])]
    lines.extend(render_row(row) for row in matrix)
    return "\n".join(lines)


def render_routes_section(result: FleetResult) -> str:
    lines: list[str] = []
    for plan in result.plans:
        route_str = " → ".join(plan.route_stops)
        lines.append(f"**Ônibus {plan.bus.id} ({plan.destination_label}):** {route_str}")
    return "\n".join(lines)
