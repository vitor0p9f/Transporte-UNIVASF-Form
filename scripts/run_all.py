"""Roda todos os cenários e grava os resultados num .md."""

import sys
import time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "results.md"

from algorithms.top_univasf import solve_scenario
from utils.fleet import load_fleet, parse_fleet_ids
from utils.scenarios import load_scenarios
from utils.seed import DEFAULT_SEED


def main() -> None:
    scenarios = load_scenarios(ROOT)
    lines: list[str] = []
    now = datetime.now(timezone.utc).astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lines.append("# Resultados — todos os cenários (TOP UNIVASF)")
    lines.append("")
    fixed = sum(1 for s in scenarios if s["instance_id"] == "base")
    lines.append(
        f"Gerado em {now} · {len(scenarios)} cenários ({fixed} fixos de base) · "
        f"seed de geração {DEFAULT_SEED} (utils/seed.py)."
    )
    lines.append("")
    lines.append("| cenário | instância | período | frota | limite | usados | pax | % | rounds | exec (s) |")
    lines.append("|---|---|---|---|---|---|---|---|---|---|")

    for s in scenarios:
        buses = load_fleet(ROOT / "fleet.csv", parse_fleet_ids(s["fleet_bus_ids"]))
        start = time.monotonic()
        try:
            data, plans, summary = solve_scenario(s, buses, ROOT)
            error = ""
        except Exception as exc:  # noqa: BLE001 — registra e segue
            data, plans, summary, error = None, [], None, f"{type(exc).__name__}: {exc}"
        elapsed = time.monotonic() - start
        if error:
            lines.append(f"| {s['scenario_id']} | {s['instance_id']} | {s['period']} | "
                         f"[{s['fleet_bus_ids']}] | {s['max_time_limit']} | ERRO | — | — | — | {elapsed:.1f} |")
        else:
            total = int(data.demand.sum())
            served = sum(p.served_passengers for p in plans)
            pct = 100.0 * served / total if total else 0.0
            lines.append(f"| {s['scenario_id']} | {s['instance_id']} | {s['period']} | "
                         f"[{s['fleet_bus_ids']}] | {s['max_time_limit']} | {len(plans)}/{len(buses)} | "
                         f"{served}/{total} | {pct:.0f}% | {summary.rounds} | {elapsed:.1f} |")

    lines.append("")
    for s in scenarios:
        buses = load_fleet(ROOT / "fleet.csv", parse_fleet_ids(s["fleet_bus_ids"]))
        cap = {b.id: b.passenger_capacity for b in buses}
        start = time.monotonic()
        try:
            data, plans, summary = solve_scenario(s, buses, ROOT)
            error = ""
        except Exception as exc:  # noqa: BLE001
            data, plans, summary, error = None, [], None, f"{type(exc).__name__}: {exc}"
        elapsed = time.monotonic() - start
        origin_txt = f" | origem {s['origin']}" if s.get("origin") else ""
        dest_txt = f" -> [{s['destination_labels']}]" if s.get("destination_labels") else ""
        lines.append(f"## Cenário {s['scenario_id']} — {s['instance_id']} / {s['period']} "
                     f"(frota [{s['fleet_bus_ids']}], limite {s['max_time_limit']} min{origin_txt}{dest_txt})")
        lines.append("")
        if error:
            lines.append(f"ERRO após {elapsed:.1f}s: `{error}`")
            lines.append("")
            continue
        total = int(data.demand.sum())
        served = sum(p.served_passengers for p in plans)
        pct = 100.0 * served / total if total else 0.0
        lines.append(f"{len(plans)} de {len(buses)} ônibus · {served}/{total} pax ({pct:.0f}%) · "
                     f"{summary.rounds} rodadas · {elapsed:.1f}s")
        lines.append("")
        lines.append("| bus | paradas | pax | tempo | pico | pax/min | origem | destino |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for p in plans:
            org = str(p.stops[0])
            dst = str(p.destination) if p.destination is not None else "livre"
            lines.append(f"| {p.bus_id} | {len(p.stops)} | {p.served_passengers} | "
                         f"{p.travel_time_minutes}/{s['max_time_limit']} | {p.peak_load}/{cap.get(p.bus_id, '?')} | "
                         f"{p.score:.2f} | {org} | {dst} |")
        lines.append("")
        agg: Counter = Counter()
        for p in plans:
            for o, d, q in p.served_pairs:
                agg[(o, d)] += q
        if agg:
            lines.append("Pares mais atendidos: " + ", ".join(
                f"{o}→{d}={q}" for (o, d), q in agg.most_common(5)))
            lines.append("")
        idle = [b.id for b in buses if b.id not in {p.bus_id for p in plans}]
        if idle:
            lines.append(f"Ociosos ({len(idle)}): {idle}")
            lines.append("")
        if summary.unserved_pairs:
            lines.append(f"Não atendidos ({summary.unserved_passengers} pax): " + ", ".join(
                f"{o}→{d}={q}" for o, d, q in summary.unserved_pairs[:8]))
            lines.append("")
        lines.append("Rotas:")
        lines.append("")
        lines.append("```")
        for p in plans:
            lines.append(f"bus {p.bus_id} ({p.stops[0]} → {p.destination}): "
                         + " -> ".join(map(str, p.stops)))
        lines.append("```")
        lines.append("")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK: {OUT} ({len(scenarios)} cenários)")


if __name__ == "__main__":
    main()
