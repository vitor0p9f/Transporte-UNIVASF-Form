"""
plotar_rotas.py
---------------
Roda os algoritmos de Clarke-Wright Clássico e Multi-Objetivo,
compara os resultados no terminal e gera uma visualização interativa
e elegante no formato HTML usando Leaflet.js, mostrando detalhes de ocupação por trecho.
Opera EXCLUSIVAMENTE sobre os arquivos da pasta /stops.
"""

import argparse
import json
import webbrowser
import math
from pathlib import Path

from clarke_wright import clarke_wright_ovrp
from clarke_wright_multi import clarke_wright_multi_ovrp, RotaMulti
from utils.fleet import ONIBUS_GENERICO
from utils.distance_matrix import carregar_stops_json, construir_matriz, filtrar_paradas

TURNO_INDICES = {
    "manha_1": 0,
    "manha_2": 1,
    "tarde_1": 2,
    "tarde_2": 3,
    "noite_1": 4,
    "noite_2": 5
}

DEPOT_IDS = {
    "manha_1": "9",
    "manha_2": "9",
    "tarde_1": "9",
    "tarde_2": "9",
    "noite_1": "37",
    "noite_2": "9",
}

def converter_rota_classica_para_multi(
    rota_classica,
    viagens: list[dict],
    matriz_dist: dict,
    matriz_tempo: dict,
    deposito: str,
    modelo
) -> RotaMulti:
    boarding_stops = list(rota_classica.paradas)
    full_paradas = [deposito] + boarding_stops
    
    viagens_atendidas = [t for t in viagens if t["embarque"] in boarding_stops]
    desemb_pendentes = set(t["desembarque"] for t in viagens_atendidas)
    
    curr = boarding_stops[-1] if boarding_stops else deposito
    while desemb_pendentes:
        melhor = None
        menor_d = float("inf")
        for d in desemb_pendentes:
            dist = matriz_dist.get(curr, {}).get(d, float("inf"))
            if dist < menor_d:
                menor_d = dist
                melhor = d
        if melhor:
            full_paradas.append(melhor)
            desemb_pendentes.remove(melhor)
            curr = melhor
        else:
            break
            
    on_board = []
    cargas_trecho = []
    total_dist = 0.0
    total_time = 0.0
    
    for idx in range(len(full_paradas) - 1):
        origem = full_paradas[idx]
        destino = full_paradas[idx + 1]
        
        boarding_here = [t for t in viagens_atendidas if t["embarque"] == origem]
        on_board.extend(boarding_here)
        
        alighting_here = [t for t in on_board if t["desembarque"] == origem]
        for t in alighting_here:
            on_board.remove(t)
            
        cargas_trecho.append(len(on_board))
        total_dist += matriz_dist.get(origem, {}).get(destino, 0.0)
        total_time += matriz_tempo.get(origem, {}).get(destino, 0.0)
        
    alighting_last = [t for t in on_board if t["desembarque"] == full_paradas[-1]]
    for t in alighting_last:
        on_board.remove(t)
    cargas_trecho.append(0)
    
    return RotaMulti(
        paradas=full_paradas,
        cargas_trecho=cargas_trecho,
        carga_maxima=max(cargas_trecho) if cargas_trecho else 0,
        dist_km=round(total_dist, 2),
        tempo_min=round(total_time, 2),
        custo_brl=modelo.custo_rota(total_dist),
        viagens_atendidas=viagens_atendidas
    )

def computar_layout_distancias(nos: list[str], matriz_dist: dict, width: float = 900.0, height: float = 900.0) -> dict[str, tuple[float, float]]:
    # Fruchterman-Reingold Pure Force-Directed Layout
    import random
    random.seed(42)
    
    coords = {}
    for no in nos:
        coords[no] = [width/2 + random.uniform(-150, 150), height/2 + random.uniform(-150, 150)]
        
    conexoes = []
    for u in nos:
        for v in nos:
            if u != v:
                d = matriz_dist.get(u, {}).get(v, float("inf"))
                if d != float("inf") and d < 15.0:
                    conexoes.append((u, v, d))
                    
    iterations = 350
    learning_rate = 0.1
    
    for _ in range(iterations):
        forces = {no: [0.0, 0.0] for no in nos}
        
        # 1. Repulsão mútua geral (evita sobreposição)
        for i in range(len(nos)):
            u = nos[i]
            for j in range(i + 1, len(nos)):
                v = nos[j]
                dx = coords[v][0] - coords[u][0]
                dy = coords[v][1] - coords[u][1]
                d2 = dx*dx + dy*dy
                d = math.sqrt(d2)
                if d < 0.1:
                    dx = random.uniform(-2, 2)
                    dy = random.uniform(-2, 2)
                    d = 2.0
                    d2 = 4.0
                
                # Força repulsiva inverse square moderada
                f_rep = 15000.0 / d2
                fx = (dx / d) * f_rep
                fy = (dy / d) * f_rep
                
                forces[u][0] -= fx
                forces[u][1] -= fy
                forces[v][0] += fx
                forces[v][1] += fy
                
        # 2. Força de mola baseada nas distâncias reais (d_real)
        # Mapeia 1 km real -> 45 pixels no canvas
        for u, v, d_real in conexoes:
            dx = coords[v][0] - coords[u][0]
            dy = coords[v][1] - coords[u][1]
            d = math.sqrt(dx*dx + dy*dy)
            if d < 0.1:
                continue
            
            target_d = d_real * 45.0
            diff = d - target_d
            
            # Constante de rigidez da mola
            k_spring = 0.06
            f_spring = k_spring * diff
            
            fx = (dx / d) * f_spring
            fy = (dy / d) * f_spring
            
            forces[u][0] += fx
            forces[u][1] += fy
            forces[v][0] -= fx
            forces[v][1] -= fy
            
        # 3. Gravidade central moderada para evitar dispersão extrema
        k_gravity = 0.005
        for no in nos:
            dx = width/2 - coords[no][0]
            dy = height/2 - coords[no][1]
            forces[no][0] += k_gravity * dx
            forces[no][1] += k_gravity * dy
            
        # Atualização com margem folgada
        margin = 45.0
        for no in nos:
            coords[no][0] += learning_rate * forces[no][0]
            coords[no][1] += learning_rate * forces[no][1]
            coords[no][0] = max(margin, min(width - margin, coords[no][0]))
            coords[no][1] = max(margin, min(height - margin, coords[no][1]))
            
    return {no: (coords[no][0], coords[no][1]) for no in nos}

def main():
    parser = argparse.ArgumentParser(description="Compara Clarke-Wright Clássico e Multi-Objetivo operando estritamente sobre /stops.")
    parser.add_argument("--turno", default="manha_1", choices=["manha_1", "manha_2", "tarde_1", "tarde_2", "noite_1", "noite_2"])
    parser.add_argument("--capacidade", type=int, default=48)
    parser.add_argument("--conforto", type=int, default=36)
    parser.add_argument("--max-tempo", type=float, default=90.0)
    args = parser.parse_args()

    # 1. Carregar paradas reais de /stops
    stops_dir = Path(__file__).parent.parent / "stops"
    stops = carregar_stops_json(stops_dir)

    if not stops:
        print("[Erro] Arquivos de paradas não encontrados em /stops.")
        return

    # 2. Construir Matriz de distância e tempo
    nos, matriz_dist = construir_matriz(stops, metrica="distance")
    _, matriz_tempo = construir_matriz(stops, metrica="estimated_travel_time")

    turno_idx = TURNO_INDICES[args.turno]
    deposito_id = DEPOT_IDS.get(args.turno, "9")

    # 3. Extrair viagens diretamente dos arquivos stops (demandas das arestas)
    viagens = []
    trip_id = 1
    for stop_id in nos:
        stop_file = stops_dir / f"{stop_id}.json"
        if not stop_file.exists():
            continue
        with open(stop_file, "r", encoding="utf-8") as f:
            dados = json.load(f)
        for edge in dados.get("edges", []):
            demand_list = edge.get("demand", [])
            if len(demand_list) > turno_idx:
                qty = int(demand_list[turno_idx])
                dest_id = str(edge["destination"])
                for _ in range(qty):
                    viagens.append({
                        "id": trip_id,
                        "embarque": stop_id,
                        "desembarque": dest_id
                    })
                    trip_id += 1

    print(f"[plotar_rotas] Carregadas {len(viagens)} viagens das arestas do turno {args.turno}.")

    if not viagens:
        print("[Erro] Nenhuma viagem com demanda encontrada para este turno nos arquivos de paradas.")
        return

    # Filtra as paradas ativas para o Clarke-Wright
    paradas_ativas = set(t["embarque"] for t in viagens) | set(t["desembarque"] for t in viagens) | {deposito_id}
    nos_filtrados, matriz_dist_filtrada = filtrar_paradas(nos, matriz_dist, paradas_ativas)
    _, matriz_tempo_filtrada = filtrar_paradas(nos, matriz_tempo, paradas_ativas)

    # 4. Rodar Clarke-Wright Clássico (Baseline)
    print("\nExecutando Clarke-Wright Clássico...")
    demanda_cvrp = {}
    for t in viagens:
        p = t["embarque"]
        if p != deposito_id:
            if p not in demanda_cvrp:
                demanda_cvrp[p] = {"boarding": 0, "alighting": 0}
            demanda_cvrp[p]["boarding"] += 1
            
    rotas_classicas_raw, lam_classico = clarke_wright_ovrp(
        nos=nos_filtrados,
        matriz=matriz_dist_filtrada,
        demanda=demanda_cvrp,
        deposito=deposito_id,
        capacidade=args.capacidade,
        modelo=ONIBUS_GENERICO,
        usar_two_phase=False,
        usar_postimprove=False,
        verbose=False
    )
    
    rotas_classicas = []
    for r in rotas_classicas_raw:
        if r.paradas:
            rotas_classicas.append(converter_rota_classica_para_multi(
                r, viagens, matriz_dist_filtrada, matriz_tempo_filtrada, deposito_id, ONIBUS_GENERICO
            ))
            
    # Atribui ID para as rotas clássicas
    for idx, r in enumerate(rotas_classicas):
        r.id = idx + 1

    # 5. Rodar Clarke-Wright Multi-Objetivo (Proposto)
    print("\nExecutando Clarke-Wright Multi-Objetivo...")
    rotas_multi, lam_multi = clarke_wright_multi_ovrp(
        nos=nos_filtrados,
        matriz_dist=matriz_dist_filtrada,
        matriz_tempo=matriz_tempo_filtrada,
        viagens=viagens,
        deposito=deposito_id,
        capacidade=args.capacidade,
        modelo=ONIBUS_GENERICO,
        conforto=args.conforto,
        max_tempo=args.max_tempo,
        verbose=True
    )
    
    # Atribui ID para as rotas multi-objetivo
    for idx, r in enumerate(rotas_multi):
        r.id = idx + 1

    # 6. Calcular pontos não atendidos e métricas adicionais
    pontos_com_demanda = (set(t["embarque"] for t in viagens) | set(t["desembarque"] for t in viagens)) - {deposito_id}
    pontos_visitados_classico = set(p for r in rotas_classicas for p in r.paradas) - {deposito_id}
    pontos_visitados_multi = set(p for r in rotas_multi for p in r.paradas) - {deposito_id}
    
    pontos_nao_atendidos_classico = sorted(list(pontos_com_demanda - pontos_visitados_classico))
    pontos_nao_atendidos_multi = sorted(list(pontos_com_demanda - pontos_visitados_multi))

    # 6. Imprimir comparativo no terminal
    print("\n" + "="*80)
    print("COMPARATIVO DE MODELOS")
    print("="*80)
    
    metrics = {
        "classico": {
            "veiculos": len(rotas_classicas),
            "distancia": sum(r.dist_km for r in rotas_classicas),
            "tempo": sum(r.tempo_min for r in rotas_classicas),
            "custo": sum(r.custo_brl for r in rotas_classicas),
            "max_lota": max((r.carga_maxima for r in rotas_classicas), default=0),
            "superlotados": sum(1 for r in rotas_classicas if r.carga_maxima > args.capacidade),
            "desconforto": sum(max(0, r.carga_maxima - args.conforto) for r in rotas_classicas),
            "excedeu_tempo": sum(1 for r in rotas_classicas if r.tempo_min > args.max_tempo)
        },
        "multi": {
            "veiculos": len(rotas_multi),
            "distancia": sum(r.dist_km for r in rotas_multi),
            "tempo": sum(r.tempo_min for r in rotas_multi),
            "custo": sum(r.custo_brl for r in rotas_multi),
            "max_lota": max((r.carga_maxima for r in rotas_multi), default=0),
            "superlotados": sum(1 for r in rotas_multi if r.carga_maxima > args.capacidade),
            "desconforto": sum(max(0, r.carga_maxima - args.conforto) for r in rotas_multi),
            "excedeu_tempo": sum(1 for r in rotas_multi if r.tempo_min > args.max_tempo)
        }
    }

    print(f"Métrica                 | Clarke-Wright Clássico  | Clarke-Wright Multi-Objetivo")
    print(f"------------------------|-------------------------|------------------------------")
    print(f"Veículos Utilizados     | {metrics['classico']['veiculos']:23d} | {metrics['multi']['veiculos']:28d}")
    print(f"Distância Total (km)    | {metrics['classico']['distancia']:20.2f} km | {metrics['multi']['distancia']:25.2f} km")
    print(f"Tempo de Viagem (min)   | {metrics['classico']['tempo']:21.1f}m | {metrics['multi']['tempo']:26.1f}m")
    print(f"Custo Combustível (R$)  | R$ {metrics['classico']['custo']:18.2f} | R$ {metrics['multi']['custo']:23.2f}")
    print(f"Lotação Máxima (pass)   | {metrics['classico']['max_lota']:23d} | {metrics['multi']['max_lota']:28d}")
    print(f"Veículos Superlotados   | {metrics['classico']['superlotados']:23d} | {metrics['multi']['superlotados']:28d}")
    print(f"Pass. em Desconforto    | {metrics['classico']['desconforto']:23d} | {metrics['multi']['desconforto']:28d}")
    print(f"Veículos Estourados Tmax| {metrics['classico']['excedeu_tempo']:23d} | {metrics['multi']['excedeu_tempo']:28d}")
    
    nao_atendidos_c_str = ", ".join(pontos_nao_atendidos_classico) if pontos_nao_atendidos_classico else "Nenhum"
    nao_atendidos_m_str = ", ".join(pontos_nao_atendidos_multi) if pontos_nao_atendidos_multi else "Nenhum"
    print(f"Pontos Não Atendidos    | {nao_atendidos_c_str:23s} | {nao_atendidos_m_str:28s}")
    print("="*80)

    # 7. Computar layout de distâncias (Spring Embedder / MDS) para refletir distâncias reais no grafo
    coords_layout = computar_layout_distancias(nos, matriz_dist)

    # Serializar rotas e coordenadas para o JS
    def serializar_rotas(rotas_list):
        serializadas = []
        for idx, r in enumerate(rotas_list):
            serializadas.append({
                "id": idx + 1,
                "paradas": r.paradas,
                "cargas_trecho": r.cargas_trecho,
                "carga_maxima": r.carga_maxima,
                "dist_km": r.dist_km,
                "tempo_min": r.tempo_min,
                "custo_brl": r.custo_brl
            })
        return serializadas

    json_classico = json.dumps(serializar_rotas(rotas_classicas))
    json_multi = json.dumps(serializar_rotas(rotas_multi))
    json_coords_layout = json.dumps(coords_layout)

    # 8. Gravar HTML com SVG side-by-side
    output_dir = Path(__file__).parent / "output"
    output_dir.mkdir(exist_ok=True)
    html_file = output_dir / f"comparacao_{args.turno}.html"

    # Preparar as métricas para renderização no HTML
    classico_metrics_html = f"""
        <div class="metric-card"><div class="metric-label">Veículos</div><div class="metric-value">{metrics['classico']['veiculos']}</div></div>
        <div class="metric-card"><div class="metric-label">Distância</div><div class="metric-value">{metrics['classico']['distancia']:.1f} km</div></div>
        <div class="metric-card"><div class="metric-label">Tempo</div><div class="metric-value">{metrics['classico']['tempo']:.0f} min</div></div>
        <div class="metric-card"><div class="metric-label">Combustível</div><div class="metric-value">R$ {metrics['classico']['custo']:.2f}</div></div>
    """

    multi_metrics_html = f"""
        <div class="metric-card"><div class="metric-label">Veículos</div><div class="metric-value">{metrics['multi']['veiculos']}</div></div>
        <div class="metric-card"><div class="metric-label">Distância</div><div class="metric-value">{metrics['multi']['distancia']:.1f} km</div></div>
        <div class="metric-card"><div class="metric-label">Tempo</div><div class="metric-value">{metrics['multi']['tempo']:.0f} min</div></div>
        <div class="metric-card"><div class="metric-label">Combustível</div><div class="metric-value">R$ {metrics['multi']['custo']:.2f}</div></div>
    """
    
    # Preparar opções dos seletores de rotas
    options_classico_html = "\n".join(
        f'<option value="{r.id}">Rota {r.id} ({r.carga_maxima} pass., {r.dist_km} km)</option>'
        for r in rotas_classicas
    )
    options_multi_html = "\n".join(
        f'<option value="{r.id}">Rota {r.id} ({r.carga_maxima} pass., {r.dist_km} km)</option>'
        for r in rotas_multi
    )
    
    # Preparar html dos pontos não atendidos
    if pontos_nao_atendidos_classico:
        unserved_classico_html = f'<span class="unserved-list">{", ".join(pontos_nao_atendidos_classico)}</span>'
    else:
        unserved_classico_html = '<span class="unserved-none">Todos os pontos atendidos</span>'
        
    if pontos_nao_atendidos_multi:
        unserved_multi_html = f'<span class="unserved-list">{", ".join(pontos_nao_atendidos_multi)}</span>'
    else:
        unserved_multi_html = '<span class="unserved-none">Todos os pontos atendidos</span>'

    html_content = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Comparativo de Rotas UNIVASF - {args.turno.upper()}</title>
    
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap" rel="stylesheet">
    
    <style>
        :root {{
            --bg: #0b0f19;
            --surface: #151d30;
            --border: #222f4c;
            --text: #f3f4f6;
            --text-muted: #9ca3af;
            --accent: #3b82f6;
            --success: #10b981;
            --danger: #ef4444;
            --warning: #f59e0b;
            --radius: 12px;
        }}

        * {{
            box-sizing: border-box;
            margin: 0;
            padding: 0;
            font-family: 'Outfit', sans-serif;
        }}

        body {{
            background: var(--bg);
            color: var(--text);
            display: flex;
            flex-direction: column;
            height: 100vh;
            overflow: hidden;
            padding: 20px;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
            flex-shrink: 0;
        }}

        h1 {{
            font-size: 22px;
            font-weight: 700;
            color: #fff;
        }}

        .subtitle {{
            font-size: 14px;
            color: var(--text-muted);
        }}

        .container {{
            display: flex;
            gap: 20px;
            flex: 1;
            overflow: hidden;
        }}

        .panel {{
            flex: 1;
            background: var(--surface);
            border: 1px solid var(--border);
            border-radius: var(--radius);
            padding: 18px;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }}

        h2 {{
            font-size: 17px;
            font-weight: 600;
            margin-bottom: 12px;
            color: #fff;
            border-bottom: 2px solid var(--border);
            padding-bottom: 6px;
        }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 8px;
            margin-bottom: 12px;
            flex-shrink: 0;
        }}

        .metric-card {{
            background: var(--bg);
            border: 1px solid var(--border);
            padding: 8px;
            border-radius: 8px;
            text-align: center;
        }}

        .metric-label {{
            font-size: 9px;
            color: var(--text-muted);
            text-transform: uppercase;
            margin-bottom: 2px;
        }}

        .metric-value {{
            font-size: 14px;
            font-weight: 600;
        }}

        .selector-container {{
            display: flex;
            align-items: center;
            gap: 8px;
            margin-bottom: 10px;
            flex-shrink: 0;
        }}

        .selector-container label {{
            font-size: 12px;
            color: var(--text-muted);
            font-weight: 500;
        }}

        .route-select {{
            background: var(--bg);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 5px 10px;
            border-radius: 6px;
            font-size: 12px;
            outline: none;
            cursor: pointer;
            transition: border-color 0.2s;
        }}

        .route-select:focus {{
            border-color: var(--accent);
        }}

        .unserved-badge {{
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            padding: 6px 10px;
            margin-bottom: 10px;
            font-size: 11px;
            display: flex;
            align-items: center;
            gap: 6px;
            flex-shrink: 0;
        }}

        .unserved-label {{
            color: var(--text-muted);
            font-weight: 500;
        }}

        .unserved-list {{
            color: var(--danger);
            font-weight: 600;
            word-break: break-all;
        }}

        .unserved-none {{
            color: var(--success);
            font-weight: 600;
        }}

        .graph-area {{
            flex: 1;
            background: var(--bg);
            border: 1px solid var(--border);
            border-radius: 8px;
            position: relative;
            overflow: hidden;
            display: flex;
            align-items: center;
            justify-content: center;
        }}

        svg {{
            width: 100%;
            height: 100%;
        }}

        .node {{
            cursor: pointer;
            transition: r 0.2s, fill 0.2s;
        }}

        .node-depot {{
            fill: var(--warning) !important;
            stroke: #fff !important;
            stroke-width: 2px;
        }}

        .link {{
            transition: stroke-width 0.2s, opacity 0.2s;
            cursor: pointer;
        }}

        .tooltip {{
            position: absolute;
            background: var(--surface);
            border: 1px solid var(--border);
            color: var(--text);
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 12px;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.15s;
            box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            z-index: 10;
        }}

        .zoom-controls {{
            position: absolute;
            top: 12px;
            right: 12px;
            display: flex;
            flex-direction: column;
            gap: 6px;
            z-index: 5;
        }}

        .zoom-btn {{
            width: 36px;
            height: 36px;
            background: rgba(21, 29, 48, 0.85);
            border: 1px solid var(--border);
            color: #fff;
            border-radius: 8px;
            font-size: 16px;
            font-weight: bold;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            transition: background 0.2s, border-color 0.2s;
            backdrop-filter: blur(4px);
        }}

        .zoom-btn:hover {{
            background: var(--accent);
            border-color: var(--accent);
        }}

        .panel:fullscreen {{
            padding: 24px;
            background: var(--bg);
            width: 100vw;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }}
        
        .panel:fullscreen .graph-area {{
            flex: 1;
        }}
    </style>
</head>
<body>

    <header>
        <div>
            <h1>UNIVASF - Comparativo de Roteamento</h1>
            <div class="subtitle">Turno: {args.turno.upper()} | Capacidade Ônibus: {args.capacidade} pass.</div>
        </div>
    </header>

    <div class="container">
        <div class="panel">
            <h2>Clarke-Wright Clássico</h2>
            <div class="metrics-grid">
                {classico_metrics_html}
            </div>
            
            <div class="unserved-badge">
                <span class="unserved-label">Não Atendidos:</span>
                {unserved_classico_html}
            </div>
            
            <div class="selector-container">
                <label for="select-classico">Filtrar Rota:</label>
                <select id="select-classico" class="route-select" onchange="filterRoute('classico', this.value)">
                    <option value="all">Todas as Rotas</option>
                    {options_classico_html}
                </select>
            </div>
            
            <div class="graph-area">
                <svg id="svg-classico" viewBox="0 0 900 900"></svg>
                <div class="zoom-controls">
                    <button class="zoom-btn" onclick="zoomController['classico'].zoomIn()" title="Aumentar Zoom">＋</button>
                    <button class="zoom-btn" onclick="zoomController['classico'].zoomOut()" title="Diminuir Zoom">－</button>
                    <button class="zoom-btn" onclick="zoomController['classico'].reset()" title="Resetar Visualização">↺</button>
                    <button class="zoom-btn fullscreen-btn" onclick="toggleFullscreen(this.closest('.panel'))" title="Tela Cheia">⛶</button>
                </div>
            </div>
        </div>

        <div class="panel">
            <h2>Clarke-Wright Multi-Objetivo</h2>
            <div class="metrics-grid">
                {multi_metrics_html}
            </div>
            
            <div class="unserved-badge">
                <span class="unserved-label">Não Atendidos:</span>
                {unserved_multi_html}
            </div>
            
            <div class="selector-container">
                <label for="select-multi">Filtrar Rota:</label>
                <select id="select-multi" class="route-select" onchange="filterRoute('multi', this.value)">
                    <option value="all">Todas as Rotas</option>
                    {options_multi_html}
                </select>
            </div>
            
            <div class="graph-area">
                <svg id="svg-multi" viewBox="0 0 900 900"></svg>
                <div class="zoom-controls">
                    <button class="zoom-btn" onclick="zoomController['multi'].zoomIn()" title="Aumentar Zoom">＋</button>
                    <button class="zoom-btn" onclick="zoomController['multi'].zoomOut()" title="Diminuir Zoom">－</button>
                    <button class="zoom-btn" onclick="zoomController['multi'].reset()" title="Resetar Visualização">↺</button>
                    <button class="zoom-btn fullscreen-btn" onclick="toggleFullscreen(this.closest('.panel'))" title="Tela Cheia">⛶</button>
                </div>
            </div>
        </div>
    </div>

    <div id="tooltip" class="tooltip"></div>

    <script>
        const dataClassico = {json_classico};
        const dataMulti = {json_multi};
        const depotId = "{deposito_id}";
        const coordsLayout = {json_coords_layout};

        // Mapear coordenadas calculadas por MDS para o D3/SVG, normalizando para preencher o viewBox (900x900) com margem
        const pts = Object.values(coordsLayout);
        const xs = pts.map(pt => pt[0]);
        const ys = pts.map(pt => pt[1]);
        
        const minX = Math.min(...xs);
        const maxX = Math.max(...xs);
        const minY = Math.min(...ys);
        const maxY = Math.max(...ys);
        
        const padding = 60; // Margem nas bordas
        const svgW = 900;
        const svgH = 900;
        
        const nodeCoords = {{}};
        Object.entries(coordsLayout).forEach(([no, pt]) => {{
            const xNorm = minX === maxX ? svgW / 2 : padding + ((pt[0] - minX) / (maxX - minX)) * (svgW - 2 * padding);
            const yNorm = minY === maxY ? svgH / 2 : padding + ((pt[1] - minY) / (maxY - minY)) * (svgH - 2 * padding);
            nodeCoords[no] = {{
                x: xNorm,
                y: yNorm
            }};
        }});

        function drawSvgGraph(svgId, routes) {{
            const svg = document.getElementById("svg-" + svgId);
            
            // Cores das rotas
            const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#14b8a6', '#f43f5e'];
            
            // Defs com marcadores de seta coloridos
            let defsHtml = `<defs>`;
            routes.forEach((route, idx) => {{
                const color = colors[idx % colors.length];
                defsHtml += `
                    <marker id="arrow-${{svgId}}-${{route.id}}" viewBox="0 0 10 10" refX="27" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                        <path d="M 0 0 L 10 5 L 0 10 z" fill="${{color}}" />
                    </marker>
                `;
            }});
            defsHtml += `</defs>`;
            
            let linksHtml = '';
            routes.forEach((route, idx) => {{
                const color = colors[idx % colors.length];
                for (let k = 0; k < route.paradas.length - 1; k++) {{
                    const orig = route.paradas[k];
                    const dest = route.paradas[k+1];
                    const cOrig = nodeCoords[orig];
                    const cDest = nodeCoords[dest];
                    if (!cOrig || !cDest) continue;
                    
                    const carga = route.cargas_trecho[k] || 0;
                    
                    // Curva quadrática Bézier para evitar sobreposição total
                    const dx = cDest.x - cOrig.x;
                    const dy = cDest.y - cOrig.y;
                    const len = Math.sqrt(dx*dx + dy*dy);
                    const mx = (cOrig.x + cDest.x) / 2;
                    const my = (cOrig.y + cDest.y) / 2;
                    
                    const offset = 14 * (idx - (routes.length - 1)/2);
                    const px = mx - (dy / (len || 1)) * offset;
                    const py = my + (dx / (len || 1)) * offset;
                    
                    linksHtml += `
                        <path d="M ${{cOrig.x}} ${{cOrig.y}} Q ${{px}} ${{py}} ${{cDest.x}} ${{cDest.y}}"
                              fill="none"
                              stroke="${{color}}"
                              stroke-width="3"
                              opacity="0.65"
                              class="link link-${{svgId}}-${{route.id}}"
                              marker-end="url(#arrow-${{svgId}}-${{route.id}})"
                              onmouseover="highlightRoute('${{svgId}}', ${{route.id}}, '${{orig}}', '${{dest}}', ${{carga}}, event)"
                              onmousemove="moveTooltip(event)"
                              onmouseout="clearHighlight('${{svgId}}', ${{route.id}})"
                              onclick="selectRoute('${{svgId}}', ${{route.id}})" />
                    `;
                }}
            }});
            
            let nodesHtml = '';
            Object.entries(nodeCoords).forEach(([id, c]) => {{
                const isDepot = id === depotId;
                const isVisited = routes.some(r => r.paradas.includes(id));
                
                let fillColor = '#1e293b';
                let strokeColor = '#475569';
                let radius = 16;
                let opacity = isVisited ? 1.0 : 0.25;
                
                if (isDepot) {{
                    fillColor = 'var(--warning)';
                    strokeColor = '#fff';
                    radius = 24;
                    opacity = 1.0;
                }} else if (isVisited) {{
                    strokeColor = 'var(--accent)';
                }}
                
                nodesHtml += `
                    <g opacity="${{opacity}}" class="node-g" data-label="${{id}}">
                        <circle cx="${{c.x}}" cy="${{c.y}}" r="${{radius}}"
                                fill="${{fillColor}}"
                                stroke="${{strokeColor}}"
                                stroke-width="2"
                                class="node" />
                        <text x="${{c.x}}" y="${{c.y}}"
                              text-anchor="middle"
                              dominant-baseline="central"
                              fill="#fff"
                              font-size="12"
                              font-weight="bold"
                              style="pointer-events: none;">${{id}}</text>
                    </g>
                `;
            }});
            
            svg.innerHTML = defsHtml + '<g class="viewport-g">' + linksHtml + nodesHtml + '</g>';
        }}

        const zoomController = {{}};

        function setupPanZoom(svgId) {{
            const svg = document.getElementById("svg-" + svgId);
            const viewport = svg.querySelector('.viewport-g');
            
            let scale = 1;
            let translateX = 0;
            let translateY = 0;
            let isDragging = false;
            let startX, startY;
            
            function updateTransform() {{
                viewport.setAttribute('transform', 'translate(' + translateX + ', ' + translateY + ') scale(' + scale + ')');
            }}
            
            svg.addEventListener('wheel', (e) => {{
                e.preventDefault();
                const zoomFactor = 1.1;
                const rect = svg.getBoundingClientRect();
                const mouseX = e.clientX - rect.left;
                const mouseY = e.clientY - rect.top;
                
                const svgX = (mouseX - translateX) / scale;
                const svgY = (mouseY - translateY) / scale;
                
                if (e.deltaY < 0) {{
                    scale *= zoomFactor;
                }} else {{
                    scale /= zoomFactor;
                }}
                scale = Math.max(0.1, Math.min(10, scale));
                
                translateX = mouseX - svgX * scale;
                translateY = mouseY - svgY * scale;
                
                updateTransform();
            }}, {{ passive: false }});
            
            svg.addEventListener('mousedown', (e) => {{
                const tag = e.target.tagName;
                if (tag === 'svg' || e.target.classList.contains('link') || e.target.classList.contains('node')) {{
                    isDragging = true;
                    startX = e.clientX - translateX;
                    startY = e.clientY - translateY;
                    svg.style.cursor = 'grabbing';
                }}
            }});
            
            window.addEventListener('mousemove', (e) => {{
                if (!isDragging) return;
                translateX = e.clientX - startX;
                translateY = e.clientY - startY;
                updateTransform();
            }});
            
            window.addEventListener('mouseup', () => {{
                if (isDragging) {{
                    isDragging = false;
                    svg.style.cursor = 'default';
                }}
            }});
            
            return {{
                zoomIn: () => {{
                    const rect = svg.getBoundingClientRect();
                    const centerX = rect.width / 2;
                    const centerY = rect.height / 2;
                    const svgX = (centerX - translateX) / scale;
                    const svgY = (centerY - translateY) / scale;
                    
                    scale *= 1.25;
                    scale = Math.min(10, scale);
                    translateX = centerX - svgX * scale;
                    translateY = centerY - svgY * scale;
                    updateTransform();
                }},
                zoomOut: () => {{
                    const rect = svg.getBoundingClientRect();
                    const centerX = rect.width / 2;
                    const centerY = rect.height / 2;
                    const svgX = (centerX - translateX) / scale;
                    const svgY = (centerY - translateY) / scale;
                    
                    scale /= 1.25;
                    scale = Math.max(0.1, scale);
                    translateX = centerX - svgX * scale;
                    translateY = centerY - svgY * scale;
                    updateTransform();
                }},
                reset: () => {{
                    scale = 1;
                    translateX = 0;
                    translateY = 0;
                    updateTransform();
                }}
            }};
        }}

        function toggleFullscreen(panelElement) {{
            if (!document.fullscreenElement) {{
                panelElement.requestFullscreen().catch(err => {{
                    console.error("Erro ao ativar tela cheia: " + err.message);
                }});
            }} else {{
                document.exitFullscreen();
            }}
        }}

        function selectRoute(svgId, routeId) {{
            const selectEl = document.getElementById("select-" + svgId);
            if (selectEl) {{
                if (selectEl.value === String(routeId)) {{
                    selectEl.value = 'all';
                }} else {{
                    selectEl.value = String(routeId);
                }}
                filterRoute(svgId, selectEl.value);
            }}
        }}

        function highlightRoute(svgId, routeId, orig, dest, carga, event) {{
            const selectEl = document.getElementById("select-" + svgId);
            if (selectEl && selectEl.value !== 'all' && String(selectEl.value) !== String(routeId)) {{
                return;
            }}
            
            document.querySelectorAll(`#svg-${{svgId}} .link`).forEach(el => {{
                el.style.opacity = '0.1';
            }});
            document.querySelectorAll(`#svg-${{svgId}} .link-${{svgId}}-${{routeId}}`).forEach(el => {{
                el.style.opacity = '1.0';
                el.style.strokeWidth = '6px';
            }});
            
            const tooltip = document.getElementById('tooltip');
            tooltip.innerHTML = `
                <strong>Ônibus #${{routeId}}</strong><br>
                Trecho: ${{orig}} &rarr; ${{dest}}<br>
                Ocupação: <strong>${{carga}} passageiros</strong>
            `;
            tooltip.style.opacity = '1';
            moveTooltip(event);
        }}

        function moveTooltip(event) {{
            const tooltip = document.getElementById('tooltip');
            tooltip.style.left = (event.pageX + 15) + 'px';
            tooltip.style.top = (event.pageY + 15) + 'px';
        }}

        function clearHighlight(svgId, routeId) {{
            const selectEl = document.getElementById("select-" + svgId);
            if (selectEl && selectEl.value !== 'all') {{
                filterRoute(svgId, selectEl.value);
                const tooltip = document.getElementById('tooltip');
                tooltip.style.opacity = '0';
                return;
            }}
            
            document.querySelectorAll(`#svg-${{svgId}} .link`).forEach(el => {{
                el.style.opacity = '0.65';
                el.style.strokeWidth = '3';
            }});
            const tooltip = document.getElementById('tooltip');
            tooltip.style.opacity = '0';
        }}

        function filterRoute(svgId, routeVal) {{
            const svg = document.getElementById("svg-" + svgId);
            if (!svg) return;
            
            const allLinks = svg.querySelectorAll('.link');
            const allNodes = svg.querySelectorAll('.node-g');
            
            if (routeVal === 'all') {{
                allLinks.forEach(link => {{
                    link.style.display = 'block';
                    link.style.opacity = '0.65';
                    link.setAttribute('stroke-width', '3');
                }});
                
                let data = svgId === 'classico' ? dataClassico : dataMulti;
                let visitados = new Set();
                data.forEach(r => {{
                    r.paradas.forEach(p => visitados.add(p));
                }});
                
                allNodes.forEach(node => {{
                    const nodeLabel = node.getAttribute('data-label');
                    if (nodeLabel === depotId) {{
                        node.style.opacity = '1';
                    }} else if (visitados.has(nodeLabel)) {{
                        node.style.opacity = '1';
                    }} else {{
                        node.style.opacity = '0.25';
                    }}
                }});
            }} else {{
                const targetClass = `link-${{svgId}}-${{routeVal}}`;
                
                let data = svgId === 'classico' ? dataClassico : dataMulti;
                let targetRoute = data.find(r => String(r.id) === String(routeVal));
                let paradasSet = new Set(targetRoute ? targetRoute.paradas : []);
                
                allLinks.forEach(link => {{
                    if (link.classList.contains(targetClass)) {{
                        link.style.display = 'block';
                        link.style.opacity = '1';
                        link.setAttribute('stroke-width', '4.5');
                    }} else {{
                        link.style.display = 'none';
                    }}
                }});
                
                allNodes.forEach(node => {{
                    const nodeLabel = node.getAttribute('data-label');
                    if (paradasSet.has(nodeLabel) || nodeLabel === depotId) {{
                        node.style.opacity = '1';
                    }} else {{
                        node.style.opacity = '0.15';
                    }}
                }});
            }}
        }}

        window.onload = () => {{
            drawSvgGraph('classico', dataClassico);
            drawSvgGraph('multi', dataMulti);
            
            zoomController['classico'] = setupPanZoom('classico');
            zoomController['multi'] = setupPanZoom('multi');
        }};
    </script>
</body>
</html>
"""

    with open(html_file, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"\n[plotar_rotas] Visualização gerada com sucesso em: {html_file}")
    
    # Abrir no navegador automaticamente
    webbrowser.open(html_file.as_uri())

if __name__ == "__main__":
    main()
