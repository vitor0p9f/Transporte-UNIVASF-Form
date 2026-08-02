"""
convert_vrp_stops.py
--------------------
Sobrepõe as distâncias reais (Google Maps) da branch python/VRP sobre
os arquivos sintéticos de stops/ (que usam os nomes canônicos do banco).

Como funciona:
  1. Carrega os stops VRP de scratch_vrp_stops/all_stops.json (extraídos
     da branch remota por scripts/extract_vrp_stops.py ou manualmente).
  2. Traduz os rótulos VRP → nomes canônicos via vrp_adapter.VRP_TO_CANONICAL.
  3. Para cada stop sintético em stops/, substitui a distância/tempo nas
     arestas que existem na matriz real; mantém os valores sintéticos para
     pares não cobertos pelo VRP.
  4. Remove a flag "_sintetico" do JSON de saída onde a aresta foi atualizada.

Uso:
    cd algorithms
    python convert_vrp_stops.py
    python convert_vrp_stops.py --dry-run   # só mostra estatísticas
"""

import argparse
import json
import sys
from pathlib import Path

# Adiciona o diretório pai ao path para importar utils
sys.path.insert(0, str(Path(__file__).parent))
from utils.vrp_adapter import construir_matriz_real, canonical

STOPS_DIR   = Path(__file__).parent.parent / "stops"
VRP_DUMP    = Path(__file__).parent.parent / "scratch_vrp_stops" / "all_stops.json"
VRP_DUMP_ALT = Path(__file__).parent / "data" / "vrp_stops.json"


def carregar_vrp(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def main() -> None:
    ap = argparse.ArgumentParser(description="Sobrepõe distâncias reais VRP nos stops sintéticos")
    ap.add_argument("--dry-run", action="store_true",
                    help="Mostra estatísticas sem salvar arquivos")
    ap.add_argument("--metrica", default="distance",
                    choices=["distance", "estimated_travel_time"],
                    help="Métrica primária a atualizar (default: distance)")
    args = ap.parse_args()

    # 1 — Carrega dados VRP
    vrp_stops = carregar_vrp(VRP_DUMP) or carregar_vrp(VRP_DUMP_ALT)
    if not vrp_stops:
        print(f"[ERRO] Arquivo VRP não encontrado.\n"
              f"  Esperado em: {VRP_DUMP}\n"
              f"  ou         : {VRP_DUMP_ALT}")
        sys.exit(1)

    print(f"[convert] {len(vrp_stops)} stops VRP carregados.")

    # 2 — Constrói matrizes reais (distância e tempo)
    real_dist = construir_matriz_real(vrp_stops, metrica="distance")
    real_time = construir_matriz_real(vrp_stops, metrica="estimated_travel_time")

    pares_reais = sum(len(v) for v in real_dist.values())
    print(f"[convert] {pares_reais} pares com distância real disponível.")

    # 3 — Atualiza stops sintéticos
    arquivos = sorted(STOPS_DIR.glob("*.json"))
    if not arquivos:
        print(f"[ERRO] Nenhum stop encontrado em {STOPS_DIR}")
        sys.exit(1)

    total_arestas = 0
    total_atualizadas = 0

    for arq in arquivos:
        with open(arq, encoding="utf-8") as f:
            stop = json.load(f)

        label    = stop.get("label", arq.stem)
        origem_c = canonical(label)
        atualizado = False

        for edge in stop.get("edges", []):
            dest_raw = edge.get("destination", "")
            dest_c   = canonical(dest_raw)
            total_arestas += 1

            d_real = real_dist.get(origem_c, {}).get(dest_c)
            t_real = real_time.get(origem_c, {}).get(dest_c)

            if d_real is not None:
                edge["distance"] = round(d_real, 2)
                atualizado = True
                total_atualizadas += 1

            if t_real is not None:
                edge["estimated_travel_time"] = round(t_real, 1)

        if atualizado:
            stop.pop("_sintetico", None)   # remove flag sintético

        if not args.dry_run:
            with open(arq, "w", encoding="utf-8") as f:
                json.dump(stop, f, ensure_ascii=False, indent=2)

    pct = total_atualizadas / total_arestas * 100 if total_arestas else 0
    modo = "[DRY-RUN] " if args.dry_run else ""
    print(f"{modo}Arestas atualizadas com distância real: "
          f"{total_atualizadas}/{total_arestas} ({pct:.1f}%)")

    if not args.dry_run:
        print(f"[convert] Stops salvos em {STOPS_DIR}")


if __name__ == "__main__":
    main()
