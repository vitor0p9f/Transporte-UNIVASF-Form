from __future__ import annotations

import json
from pathlib import Path

from application.graph.graph_factory import demand_state_factory, graph_factory
from application.orienteering.fleet import run_balanced_fleet_top
from application.orienteering.report import fleet_result_rows, fleet_summary_row, render_markdown_table, render_routes_section
from domain.entities.bus import Bus
from domain.entities.shift import Shift
from infraestructure.graph.graph_loader import graph_loader


def load_buses(path: Path) -> list[Bus]:
    data = json.loads(path.read_text())
    return [
        Bus(
            id=b["id"],
            passenger_capacity=b["passenger_capacity"],
            fuel_capacity=b["fuel_capacity"],
            km_autonomy_per_liter=b["km_autonomy_per_liter"],
        )
        for b in data["buses"]
    ]


def main() -> None:
    graph_data = graph_loader(Path("graph.json"))
    graph = graph_factory(graph_data)
    buses = load_buses(Path("fleet.json"))

    origin_label = input("Origin: ").strip()
    destination_labels = input("Destinations (space-separated): ").strip().split()

    shift_names = [shift.name for shift in Shift]
    print("Available shifts:")
    for i, name in enumerate(shift_names, 1):
        print(f"  {i}) {name}")
    shift_index = int(input("Choose shift (number): ").strip()) - 1
    shift = Shift[shift_names[shift_index]]

    demand_state = demand_state_factory(graph_data, shift)

    time_limit = int(input("Time limit per bus (min) [90]: ").strip() or "90")
    seed = int(input("Random seed [0]: ").strip() or "0")
    driver_hourly_rate = float(input("Driver hourly rate (R$/h) [30.0]: ").strip() or "30.0")
    diesel_price = float(input("Diesel price (R$/L) [6.5]: ").strip() or "6.5")

    result = run_balanced_fleet_top(
        graph,
        demand_state,
        buses,
        origin_label,
        destination_labels,
        time_limit,
        seed=seed,
        diesel_price_per_liter=diesel_price,
        driver_hourly_rate=driver_hourly_rate,
    )

    rows = fleet_result_rows(result)
    rows.append(fleet_summary_row(result))
    print()
    print(render_markdown_table(rows))
    print()
    print(render_routes_section(result))


if __name__ == "__main__":
    main()
