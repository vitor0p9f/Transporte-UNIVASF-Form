from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

from application.graph.graph_factory import demand_state_factory, graph_factory
from application.orienteering.fleet import run_parallel_fleet_top
from application.orienteering.fleet_legacy import run_balanced_fleet_top
from application.orienteering.report import fleet_result_rows, fleet_summary_row, render_markdown_table, render_routes_section
from domain.entities.bus import Bus
from domain.entities.shift import Shift
from infraestructure.graph.graph_loader import graph_loader


@dataclass
class RunConfig:
    origin_label: str = "1"
    destination_labels: list[str] = field(default_factory=list)
    shift: Shift = Shift.MORNING_1
    time_limit: int = 90
    diesel_price: float = 6.5
    driver_hourly_rate: float = 30.0
    mode: str = "parallel"
    two_opt: bool = True
    score: str = "density"
    seed: int = 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Otimização de frota (orienteering/TOP).")
    parser.add_argument("--origin", default=None, help="Origem (omitir p/ menu)")
    parser.add_argument("--destinations", default=None, help="Destinos separados por espaço; vazio = livre (omitir p/ menu)")
    parser.add_argument("--shift", default=None, help="Nome do turno ou índice 1-based (omitir p/ menu)")
    parser.add_argument("--time-limit", type=int, default=None, help="Limite de tempo por ônibus em min (omitir p/ menu)")
    parser.add_argument("--diesel-price", type=float, default=None, help="Preço do diesel R$/L (omitir p/ menu)")
    parser.add_argument("--driver-rate", type=float, default=None, help="Taxa do motorista R$/h (omitir p/ menu)")
    parser.add_argument("--mode", choices=["parallel", "sequential"], default=None, help="parallel ou sequential (omitir p/ menu)")
    parser.add_argument("--seed", type=int, default=0, help="Seed RNG (só no mode=sequential)")
    parser.add_argument("--score", choices=["density", "pax_minus_time"], default=None, help="Métrica de prize (omitir p/ menu)")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--two-opt", dest="two_opt", action="store_true", default=None, help="Habilita 2-opt (padrão)")
    group.add_argument("--no-two-opt", dest="two_opt", action="store_false", default=None, help="Desabilita 2-opt")
    return parser


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


def resolve_shift(value: str) -> Shift:
    shift_name = value.strip().upper()
    if shift_name in Shift.__members__:
        return Shift[shift_name]
    return list(Shift)[int(shift_name) - 1]


def _read_line(prompt: str) -> str:
    try:
        return input(prompt).strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)


def _read_int(prompt: str, current: int) -> int:
    raw = _read_line(prompt)
    return int(raw) if raw else current


def _read_float(prompt: str, current: float) -> float:
    raw = _read_line(prompt)
    return float(raw) if raw else current


def _pick_shift() -> Shift:
    names = [s.name for s in Shift]
    print("\n=== Turno ===")
    for i, name in enumerate(names, 1):
        print(f"  {i:>2}) {name}")
    while True:
        raw = _read_line("Escolha: ")
        if raw.isdigit() and 1 <= int(raw) <= len(names):
            return Shift[names[int(raw) - 1]]
        print("Opção inválida.")


def _configure() -> RunConfig:
    cfg = RunConfig()
    score_options = ["density", "pax_minus_time"]
    while True:
        dest = " ".join(cfg.destination_labels) or "livre"
        print("\n=== OTIMIZAÇÃO DE FROTA ===")
        print(f"  1) Origem ............: {cfg.origin_label}")
        print(f"  2) Destinos ..........: {dest}")
        print(f"  3) Turno .............: {cfg.shift.name}")
        print(f"  4) Tempo/ônibus (min).: {cfg.time_limit}")
        print(f"  5) Diesel (R$/L) .....: {cfg.diesel_price}")
        print(f"  6) Motorista (R$/h) ..: {cfg.driver_hourly_rate}")
        print(f"  7) Modo ..............: {cfg.mode}")
        print(f"  8) 2-opt no commit ...: {'on' if cfg.two_opt else 'off'}")
        print(f"  9) Score .............: {cfg.score}")
        print(f" 10) Executar")
        print(f" 11) Sair")
        raw = _read_line("Escolha [1-11]: ")
        if not raw.isdigit() or not 1 <= int(raw) <= 11:
            print("Opção inválida.")
            continue
        choice = int(raw)
        if choice == 1:
            raw = _read_line(f"Origem [{cfg.origin_label}]: ")
            if raw:
                cfg.origin_label = raw
        elif choice == 2:
            raw = _read_line("Destinos (espaçados; vazio = modo livre): ")
            cfg.destination_labels = raw.split()
        elif choice == 3:
            cfg.shift = _pick_shift()
        elif choice == 4:
            cfg.time_limit = _read_int("Tempo/ônibus (min): ", cfg.time_limit)
        elif choice == 5:
            cfg.diesel_price = _read_float("Diesel (R$/L): ", cfg.diesel_price)
        elif choice == 6:
            cfg.driver_hourly_rate = _read_float("Motorista (R$/h): ", cfg.driver_hourly_rate)
        elif choice == 7:
            cfg.mode = "sequential" if cfg.mode == "parallel" else "parallel"
            print(f"Modo -> {cfg.mode}")
        elif choice == 8:
            cfg.two_opt = not cfg.two_opt
            print(f"2-opt -> {'on' if cfg.two_opt else 'off'}")
        elif choice == 9:
            cfg.score = score_options[(score_options.index(cfg.score) + 1) % len(score_options)]
            print(f"Score -> {cfg.score}")
        elif choice == 10:
            return cfg
        elif choice == 11:
            print("Saindo.")
            sys.exit(0)


def _run(cfg: RunConfig) -> None:
    graph_data = graph_loader(Path("graph.json"))
    graph = graph_factory(graph_data)
    buses = load_buses(Path("fleet.json"))
    demand_state = demand_state_factory(graph_data, cfg.shift)

    cost_kwargs = {
        "diesel_price_per_liter": cfg.diesel_price,
        "driver_hourly_rate": cfg.driver_hourly_rate,
    }
    if cfg.mode == "sequential":
        result = run_balanced_fleet_top(
            graph,
            demand_state,
            buses,
            cfg.origin_label,
            cfg.destination_labels,
            cfg.time_limit,
            use_two_opt=cfg.two_opt,
            score_metric=cfg.score,
            seed=cfg.seed,
            **cost_kwargs,
        )
    else:
        result = run_parallel_fleet_top(
            graph,
            demand_state,
            buses,
            cfg.origin_label,
            cfg.destination_labels,
            cfg.time_limit,
            use_two_opt=cfg.two_opt,
            score_metric=cfg.score,
            **cost_kwargs,
        )

    destination_note = " ".join(cfg.destination_labels) if cfg.destination_labels else "livre"
    print(
        f"\nmode={cfg.mode} two_opt={'on' if cfg.two_opt else 'off'} score={cfg.score} "
        f"destination={destination_note} shift={cfg.shift.name} time_limit={cfg.time_limit} min"
    )
    rows = fleet_result_rows(result)
    rows.append(fleet_summary_row(result))
    print()
    print(render_markdown_table(rows))
    print()
    print(render_routes_section(result))


def main() -> None:
    args = build_parser().parse_args()
    flag_names = ["origin", "destinations", "shift", "time_limit", "diesel_price", "driver_rate", "mode", "score", "two_opt"]
    interactive = all(getattr(args, name) is None for name in flag_names)

    if interactive:
        cfg = _configure()
    else:
        cfg = RunConfig(seed=args.seed)
        if args.origin is not None:
            cfg.origin_label = args.origin
        if args.destinations is not None:
            cfg.destination_labels = args.destinations.split()
        if args.shift is not None:
            cfg.shift = resolve_shift(args.shift)
        if args.time_limit is not None:
            cfg.time_limit = args.time_limit
        if args.diesel_price is not None:
            cfg.diesel_price = args.diesel_price
        if args.driver_rate is not None:
            cfg.driver_hourly_rate = args.driver_rate
        if args.mode is not None:
            cfg.mode = args.mode
        if args.two_opt is not None:
            cfg.two_opt = args.two_opt
        if args.score is not None:
            cfg.score = args.score

    _run(cfg)


if __name__ == "__main__":
    main()