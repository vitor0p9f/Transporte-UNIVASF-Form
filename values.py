import json
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional
import re

# ------------------------------------------------------------
# 1. Funções originais (carregar_nos, calcular_rota_de_pasta, etc.)
# ------------------------------------------------------------
def carregar_nos(pasta: str) -> List[Dict[str, Any]]:
    nos = []
    caminho_pasta = Path(pasta)
    if not caminho_pasta.is_dir():
        raise NotADirectoryError(f"'{pasta}' não é uma pasta válida.")
    for arquivo in caminho_pasta.glob("*.json"):
        with open(arquivo, "r", encoding="utf-8") as f:
            dados = json.load(f)
        if isinstance(dados, list):
            nos.extend(dados)
        elif isinstance(dados, dict):
            nos.append(dados)
    return nos

def calcular_rota_de_pasta(pasta: str, sequencia: List[str]) -> Tuple[float, float]:
    nos = carregar_nos(pasta)
    grafo = {}
    for no in nos:
        label = no["label"]
        vizinhos = {}
        for aresta in no.get("edges", []):
            vizinhos[aresta["destination"]] = {
                "distancia": aresta["distance"],
                "tempo": aresta["estimated_travel_time"]
            }
        grafo[label] = vizinhos
    dist_total, tempo_total = 0.0, 0.0
    for i in range(len(sequencia)-1):
        o, d = sequencia[i], sequencia[i+1]
        if o == d: continue
        if o not in grafo: raise ValueError(f"Parada '{o}' não encontrada.")
        if d not in grafo[o]: raise ValueError(f"Conexão '{o}' -> '{d}' não existe.")
        dist_total += grafo[o][d]["distancia"]
        tempo_total += grafo[o][d]["tempo"]
    return dist_total, tempo_total

# ------------------------------------------------------------
# 2. Processamento do CSV e mapeamento de turnos
# ------------------------------------------------------------
TURNOS_CANONICOS = ["manha1", "manha2", "tarde1", "tarde2", "noite1", "noite2"]

TURNO_DESCRICAO = {
    "manha1": "Manhã 1 (6h–8h)",
    "manha2": "Manhã 2 (9h–10h)",
    "tarde1": "Tarde 1 (11h–13h)",
    "tarde2": "Tarde 2 (14h–16h)",
    "noite1": "Noite 1 (17h–18h)",
    "noite2": "Noite 2 (18h–23h)",
}

TIPO_LEGENDAS = {
    "destino": "Pontos de desembarque",
    "origem": "Pontos de embarque",
}

MAPA_TURNOS = {
    "manha_1": 0,
    "manha_2": 1,
    "tarde_1": 2,
    "tarde_2": 3,
    "noite_1": 4,
    "noite_2": 5,
}

def normalizar(texto: str) -> str:
    return texto.strip().lower().replace(" ", "").replace("_", "").replace("-", "")

def carregar_e_limpar_csv(caminho_csv: str, stops_remover: Optional[List[str]] = None) -> pd.DataFrame:
    df = pd.read_csv(caminho_csv)
    cols = [c for c in df.columns if c != 'id']
    df = df.drop_duplicates(subset=cols, keep='first')
    df = df[df['embarque'] != df['desembarque']]
    df = df.dropna(subset=['embarque', 'desembarque'])
    df['embarque'] = df['embarque'].str.strip()
    df['desembarque'] = df['desembarque'].str.strip()

    if stops_remover:
        mask = df['embarque'].isin(stops_remover) | df['desembarque'].isin(stops_remover)
        df = df[~mask]

    return df

def diagnosticar_turnos(df: pd.DataFrame):
    print("Distribuição de turnos:")
    print(df['turno'].value_counts().to_string())
    nao_mapeados = [t for t in df['turno'].unique() if t not in MAPA_TURNOS]
    if nao_mapeados:
        print(f"Atenção: turnos não mapeados (serão ignorados nos vetores): {nao_mapeados}")
    print()

# ------------------------------------------------------------
# 3. Geração do TXT com paradas do CSV (mantido)
# ------------------------------------------------------------
def exportar_paradas_csv_para_txt(df: pd.DataFrame, mapa_turnos: dict, arquivo_saida: str):
    counters = {}
    idx_turno = {t: mapa_turnos[t] for t in df['turno'].unique() if t in mapa_turnos}

    for _, row in df.iterrows():
        turno = row['turno']
        if turno not in idx_turno:
            continue
        i = idx_turno[turno]

        emb = row['embarque']
        if emb not in counters:
            counters[emb] = [[0]*6, [0]*6]
        counters[emb][0][i] += 1

        des = row['desembarque']
        if des not in counters:
            counters[des] = [[0]*6, [0]*6]
        counters[des][1][i] += 1

    with open(arquivo_saida, "w", encoding="utf-8") as f:
        for parada, (boardings, alightings) in sorted(counters.items()):
            f.write(f"Parada: {parada}\n")
            f.write(f"  Boardings : {boardings}\n")
            f.write(f"  Alightings: {alightings}\n\n")

    soma_b = sum(sum(b) for b, _ in counters.values())
    soma_a = sum(sum(a) for _, a in counters.values())
    print(f"Arquivo '{arquivo_saida}' gerado com {len(counters)} paradas distintas.")
    print(f"Soma total de boardings no TXT: {soma_b}")
    print(f"Soma total de alightings no TXT: {soma_a}\n")

# ------------------------------------------------------------
# 4. GRÁFICOS A PARTIR DO JSON (com limpeza especial) – TODOS OS PONTOS
# ------------------------------------------------------------
def limpar_nome_parada(nome: str) -> str:
    """
    Aplica regras específicas para nomes de paradas:
    - 'UNIVASF CCA / Petrolina' → 'CAMPUS CCA'
    - 'UNIVASF / JUAZEIRO' → 'CAMPUS JUAZEIRO'
    - 'UNIVASF / PETROLINA' → 'CAMPUS PETROLINA'
    - Remove o sufixo ' / Cidade' para os demais.
    """
    nome_original = nome.strip()
    
    mapeamento = {
        "UNIVASF CCA / PETROLINA": "CAMPUS CCA",
        "UNIVASF / JUAZEIRO": "CAMPUS JUAZEIRO",
        "UNIVASF / PETROLINA": "CAMPUS PETROLINA",
        "LOJAS AMERICANAS / JUAZEIRO": "LOJAS AMERICANAS DE JUAZEIRO",
        "ANTIGA ESTAÇÃO FERROVIÁRIA / PETROLINA": "ANTIGA ESTAÇÃO FERROVIÁRIA DE PETROLINA",
        "ESTAÇÃO ANTIGA / JUAZEIRO": "ESTAÇÃO ANTIGA DE JUAZEIRO",
        "VERDÃO / JUAZEIRO": "VERDÃO DE JUAZEIRO",
        "LOJA DE MATERIAL DE CONSTRUÇÃO CANTEIRO DE OBRAS / PETROLINA": " LOJA DE MATERIAL DE CONTRUÇÃO CANTEIRO DE OBRAS DE PETROLINA",
        "DETRAN / PETROLINA": "DETRAN DE PETROLINA",
        "MINISTÉRIO PÚBLICO FEDERAL / PETROLINA": "MINISTÉRIO PÚBLICO FEDERAL DE PETROLINA",
        "PLANTE BEM MATRIZ / PETROLINA": "PLANTE BEM MATRIZ DE PETROLINA",
        "ABARÉ RADIADORES / PETROLINA": "ABARÉ RADIADORES DE PETROLINA",
        "TERMINAL RODOVIÁRIO / PETROLINA": "TERMINAL RODOVIÁRIO DE PETROLINA"
    }
    
    if nome_original in mapeamento:
        return mapeamento[nome_original]
    
    if nome_original.startswith("UNIVASF"):
        partes = nome_original.split(" / ")
        if len(partes) > 1:
            sem_prefixo = partes[0].replace("UNIVASF", "").strip()
            if sem_prefixo:
                return f"Campus {sem_prefixo}"
            else:
                return f"Campus {partes[1]}"
        else:
            return "Campus"
    
    if " / " in nome_original:
        return nome_original.split(" / ")[0].strip()
    
    return nome_original

def extrair_cidade(label: str) -> Optional[str]:
    """Retorna 'PETROLINA', 'JUAZEIRO' ou None baseado no sufixo após ' / '."""
    if ' / ' in label:
        cidade = label.split(' / ')[-1].strip().upper()
        if 'PETROLINA' in cidade:
            return 'PETROLINA'
        elif 'JUAZEIRO' in cidade:
            return 'JUAZEIRO'
    return None

import unicodedata

def slugify_turno(desc: str) -> str:
    """Converte descrição do turno para slug minúsculo com underscores."""
    # Remove conteúdo entre parênteses
    desc_limpa = re.sub(r'\([^)]*\)', '', desc).strip()
    # Normaliza para NFKD (decompõe acentos) e converte para ASCII
    desc_sem_acento = unicodedata.normalize('NFKD', desc_limpa).encode('ASCII', 'ignore').decode('ASCII')
    # Converte para minúsculo, substitui espaços por underscore
    slug = desc_sem_acento.lower().replace(' ', '_')
    # Remove quaisquer caracteres que não sejam letras, números ou underscore
    slug = re.sub(r'[^a-z0-9_]', '', slug)
    return slug

def _gerar_grafico_barras(dados: Dict[str, int], turno_desc: str, tipo: str, prefixo: str):
    """Gera um gráfico de barras horizontais com TODOS os itens (sem limite)."""
    items = sorted(dados.items(), key=lambda x: x[1], reverse=True)  # sem cortar
    if not items:
        print(f"Turno '{turno_desc}' ({tipo}): sem dados, gráfico não gerado.")
        return

    paradas, contagens = zip(*items)
    total = sum(contagens)

    # Altura proporcional ao número de paradas (mínimo 8, 0.3 polegadas por barra)
    altura = max(8, len(paradas) * 0.3)
    fig, ax = plt.subplots(figsize=(12, altura))
    bars = ax.barh(paradas, contagens, color='steelblue', edgecolor='white')

    for bar, qtd, perc in zip(bars, contagens, [100 * c / total for c in contagens]):
        ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                f'{qtd} ({perc:.1f}%)', va='center', fontsize=11)

    titulo = f"{TIPO_LEGENDAS[tipo]} - {turno_desc}"
    ax.set_title(titulo, fontsize=16)
    ax.set_xlabel('Quantidade de viagens', fontsize=13)
    ax.invert_yaxis()
    ax.set_xlim(0, max(contagens) * 1.30)
    ax.tick_params(axis='both', labelsize=11)

    plt.tight_layout()
    slug = slugify_turno(turno_desc)
    nome_arquivo = f"{prefixo}_{slug}.png"
    plt.savefig(nome_arquivo, dpi=300, bbox_inches='tight')
    plt.close()
    print(f"Gráfico salvo: {nome_arquivo}")

def gerar_graficos_a_partir_json(nos: List[Dict[str, Any]]):
    """Gera gráficos de barras (embarques e desembarques) para cada turno, usando os JSONs."""
    embarques_por_turno = {i: {} for i in range(6)}
    desembarques_por_turno = {i: {} for i in range(6)}

    for no in nos:
        label_original = no.get('label', '')
        label_limpo = limpar_nome_parada(label_original)
        boardings = no.get('boardings', [0]*6)
        alightings = no.get('alightings', [0]*6)
        for i in range(6):
            if boardings[i]:
                embarques_por_turno[i][label_limpo] = embarques_por_turno[i].get(label_limpo, 0) + boardings[i]
            if alightings[i]:
                desembarques_por_turno[i][label_limpo] = desembarques_por_turno[i].get(label_limpo, 0) + alightings[i]

    for i in range(6):
        turno_nome = TURNOS_CANONICOS[i]
        descricao = TURNO_DESCRICAO.get(turno_nome, turno_nome)
        if embarques_por_turno[i]:
            _gerar_grafico_barras(
                dados=embarques_por_turno[i],
                turno_desc=descricao,
                tipo='origem',
                prefixo='top_embarques'
            )
        if desembarques_por_turno[i]:
            _gerar_grafico_barras(
                dados=desembarques_por_turno[i],
                turno_desc=descricao,
                tipo='destino',
                prefixo='top_desembarques'
            )

# ------------------------------------------------------------
# 5. Cálculo da rota com ocupação (nunca negativa)
# ------------------------------------------------------------
def calcular_rota_com_ocupacao_grafos(sequencia: List[str], turno_idx: int, nos: List[Dict]) -> Tuple[float, float, List[Dict], int]:
    dist, tempo = calcular_rota_de_pasta("./stops", sequencia)
    nodemap = {no['label']: no for no in nos}
    ocup = 0
    ocup_max = 0
    res = []
    n = len(sequencia)

    for i, parada in enumerate(sequencia):
        no = nodemap.get(parada)
        if no is None:
            s = d = 0
        else:
            boardings = no.get('boardings', [0]*6)
            alightings = no.get('alightings', [0]*6)
            s = boardings[turno_idx] if turno_idx < len(boardings) else 0
            d = alightings[turno_idx] if turno_idx < len(alightings) else 0

        if i == 0:
            d = 0
        elif i == n - 1:
            s = 0

        d_efetivo = min(d, ocup)
        ocup -= d_efetivo
        ocup += s
        if ocup > ocup_max:
            ocup_max = ocup

        res.append({
            'parada': parada,
            'embarques': s,
            'desembarques': d_efetivo,
            'ocupacao_apos': ocup
        })

    return dist, tempo, res, ocup_max

# ------------------------------------------------------------
# 6. Resumo por cidade e turno (AGORA BASEADO NO JSON)
# ------------------------------------------------------------
def resumo_por_cidade_json(nos: List[Dict[str, Any]]):
    """Calcula embarques/desembarques por cidade usando os dados dos JSONs."""
    emb_total = 0
    des_total = 0
    emb_petrolina = 0
    emb_juazeiro = 0
    des_petrolina = 0
    des_juazeiro = 0
    outros_emb = 0
    outros_des = 0

    emb_petrolina_turno = [0]*6
    emb_juazeiro_turno  = [0]*6
    des_petrolina_turno = [0]*6
    des_juazeiro_turno  = [0]*6
    outros_emb_turno    = [0]*6
    outros_des_turno    = [0]*6
    total_emb_turno     = [0]*6
    total_des_turno     = [0]*6

    exemplos_nao_classificados = set()

    for no in nos:
        label = no.get('label', '')
        cidade = extrair_cidade(label)
        boardings = no.get('boardings', [0]*6)
        alightings = no.get('alightings', [0]*6)

        for i in range(6):
            emb = boardings[i]
            des = alightings[i]
            if emb:
                emb_total += emb
                total_emb_turno[i] += emb
                if cidade == 'PETROLINA':
                    emb_petrolina += emb
                    emb_petrolina_turno[i] += emb
                elif cidade == 'JUAZEIRO':
                    emb_juazeiro += emb
                    emb_juazeiro_turno[i] += emb
                else:
                    outros_emb += emb
                    outros_emb_turno[i] += emb
                    if label:
                        exemplos_nao_classificados.add(label)
            if des:
                des_total += des
                total_des_turno[i] += des
                if cidade == 'PETROLINA':
                    des_petrolina += des
                    des_petrolina_turno[i] += des
                elif cidade == 'JUAZEIRO':
                    des_juazeiro += des
                    des_juazeiro_turno[i] += des
                else:
                    outros_des += des
                    outros_des_turno[i] += des
                    if label:
                        exemplos_nao_classificados.add(label)

    print("\n=== RESUMO POR CIDADE (JSON) ===")
    print(f"Total de embarques: {emb_total}")
    if emb_total > 0:
        print(f"  Petrolina: {emb_petrolina} ({100*emb_petrolina/emb_total:.1f}%)")
        print(f"  Juazeiro : {emb_juazeiro} ({100*emb_juazeiro/emb_total:.1f}%)")
    if outros_emb > 0:
        print(f"  Outros   : {outros_emb} ({100*outros_emb/emb_total:.1f}%)")
        if exemplos_nao_classificados:
            print("    Exemplos de pontos não classificados:")
            for p in sorted(exemplos_nao_classificados)[:5]:
                print(f"      - '{p}'")

    print(f"\nTotal de desembarques: {des_total}")
    if des_total > 0:
        print(f"  Petrolina: {des_petrolina} ({100*des_petrolina/des_total:.1f}%)")
        print(f"  Juazeiro : {des_juazeiro} ({100*des_juazeiro/des_total:.1f}%)")
    if outros_des > 0:
        print(f"  Outros   : {outros_des} ({100*outros_des/des_total:.1f}%)")

    print("\n=== DETALHAMENTO POR TURNO ===")
    for idx in range(6):
        nome_turno = TURNOS_CANONICOS[idx]
        desc_turno = TURNO_DESCRICAO.get(nome_turno, nome_turno)
        emb_t = total_emb_turno[idx]
        des_t = total_des_turno[idx]
        if emb_t == 0 and des_t == 0:
            continue

        print(f"\nTurno: {desc_turno} ({nome_turno})")
        if emb_t > 0:
            print(f"  Embarques totais: {emb_t}")
            print(f"    Petrolina: {emb_petrolina_turno[idx]} ({100*emb_petrolina_turno[idx]/emb_t:.1f}%)")
            print(f"    Juazeiro : {emb_juazeiro_turno[idx]} ({100*emb_juazeiro_turno[idx]/emb_t:.1f}%)")
            if outros_emb_turno[idx] > 0:
                print(f"    Outros   : {outros_emb_turno[idx]} ({100*outros_emb_turno[idx]/emb_t:.1f}%)")
        if des_t > 0:
            print(f"  Desembarques totais: {des_t}")
            print(f"    Petrolina: {des_petrolina_turno[idx]} ({100*des_petrolina_turno[idx]/des_t:.1f}%)")
            print(f"    Juazeiro : {des_juazeiro_turno[idx]} ({100*des_juazeiro_turno[idx]/des_t:.1f}%)")
            if outros_des_turno[idx] > 0:
                print(f"    Outros   : {outros_des_turno[idx]} ({100*outros_des_turno[idx]/des_t:.1f}%)")

# ------------------------------------------------------------
# 7. Verificação de consistência JSON vs CSV (mantido)
# ------------------------------------------------------------
def verificar_consistencia_json_vs_csv(df_original: pd.DataFrame, nos: List[Dict[str, Any]]):
    soma_boardings_json = sum(sum(no.get('boardings', [])) for no in nos)
    soma_alightings_json = sum(sum(no.get('alightings', [])) for no in nos)
    total_viagens = len(df_original)

    print("\n=== VERIFICAÇÃO DE CONSISTÊNCIA (JSON vs CSV) ===")
    print(f"Total de viagens no CSV original: {total_viagens}")
    print(f"Soma de boardings nos JSONs: {soma_boardings_json}")
    print(f"Soma de alightings nos JSONs: {soma_alightings_json}")

    if soma_boardings_json == total_viagens and soma_alightings_json == total_viagens:
        print("✓ JSONs estão consistentes com o CSV original.")
    else:
        diff_b = total_viagens - soma_boardings_json
        diff_a = total_viagens - soma_alightings_json
        print("✗ Diferença encontrada (os JSONs podem estar desatualizados):")
        print(f"   Boardings: CSV {total_viagens} vs JSON {soma_boardings_json} (diferença: {diff_b})")
        print(f"   Alightings: CSV {total_viagens} vs JSON {soma_alightings_json} (diferença: {diff_a})")
        print("   As análises de gráficos e resumo por cidade usarão os dados do JSON.")
    print()

# ------------------------------------------------------------
# 8. Execução principal
# ------------------------------------------------------------
if __name__ == "__main__":
    pasta_json = "./stops"
    arquivo_csv = "./trips.csv"

    paradas_remover = [
        "Academia Well",
        "Av. Transnordestina – Entrada Bairro Dom Avelar",
        "Av. Transnordestina – Entrada Dom Avelar",
        "Av. da Integração – Secretaria de Obras",
        "Canteiro de Obras – Juazeiro",
        "Estrada da Banana – Antiga Distribuidora Camaleão",
        "Estrada da Banana – Primeira Rotatória",
        "Farmácia Popular",
        "Final da proteção de metal – Bairro Quati",
        "Ponto BR 428 – PRF",
        "Secretaria de Obras",
        "Secretaria de Obras – Av. da Integração"
    ]

    # 1. Carregar CSV original
    df_original = carregar_e_limpar_csv(arquivo_csv, stops_remover=None)
    print("========== CSV ORIGINAL (apenas limpeza básica) ==========")
    print(f"Viagens válidas: {len(df_original)}")
    print(f"Usuários distintos: {df_original['email'].nunique()}")
    diagnosticar_turnos(df_original)

    # 2. Carregar JSONs e verificar consistência
    nos = carregar_nos(pasta_json)
    verificar_consistencia_json_vs_csv(df_original, nos)

    # 3. Aplicar remoção de paradas
    if paradas_remover:
        mask = df_original['embarque'].isin(paradas_remover) | df_original['desembarque'].isin(paradas_remover)
        df = df_original[~mask].copy()
        removidas = mask.sum()
        print(f">>> Removidas {removidas} linhas ({100*removidas/len(df_original):.1f}% do total) com as paradas da lista.\n")
    else:
        df = df_original
        removidas = 0

    print("========== APÓS A REMOÇÃO ==========")
    print(f"Viagens válidas: {len(df)}")
    print(f"Usuários distintos: {df['email'].nunique()}")
    diagnosticar_turnos(df)

    print("=== USUÁRIOS DISTINTOS POR TURNO (após remoção) ===")
    for turno in sorted(df['turno'].unique()):
        qtd = df[df['turno'] == turno]['email'].nunique()
        print(f"  {turno}: {qtd} usuários distintos")
    print()

    # 4. Gerar TXT com as paradas remanescentes (base CSV)
    exportar_paradas_csv_para_txt(df, MAPA_TURNOS, "paradas_nao_removidas.txt")

    # 5. GERAR GRÁFICOS A PARTIR DOS JSONs – AGORA COM TODOS OS PONTOS
    gerar_graficos_a_partir_json(nos)

    # 6. Resumo por cidade e turno (JSON)
    resumo_por_cidade_json(nos)

    # 7. Rota para análise de ocupação
    rota = [
        "UNIVASF / JUAZEIRO",
        "TERMINAL RODOVIÁRIO / PETROLINA",
        "SEMENTEIRA / PETROLINA",
        "PARK MUNDO DA LUA / PETROLINA",
        "UNIVASF / PETROLINA",
        "ANTIGO BAR DA TRIPA / PETROLINA",
        "GBARBOSA AV. MONSENHOR ÂNGELO SAMPAIO / PETROLINA",
        "POSTO BBB / PETROLINA",
        "LOJA DE MATERIAL DE CONSTRUÇÃO CANTEIRO DE OBRAS / PETROLINA",
        "ABARÉ RADIADORES / PETROLINA",
        "ALDIEGAS / PETROLINA",
        "POSTO SÃO FRANCISCO / PETROLINA",
        "FEIRA DA COHAB MASSANGANO / PETROLINA",
        "IZABELLA MATERIAL DE CONSTRUÇÃO BAIRRO COSME E DAMIÃO / PETROLINA",
        "ALOJAMENTO ESTUDANTIL DO CCA / PETROLINA",
        "IZABELLA MATERIAL DE CONSTRUÇÃO BAIRRO COSME E DAMIÃO / PETROLINA",
        "IGREJA FILADÉLFIA / PETROLINA",
        "CONSTRUTEO / PETROLINA",
        "POSTO ALE / PETROLINA",
        "PLANTE BEM MATRIZ / PETROLINA",
        "LOJAS AMERICANAS / JUAZEIRO",
        "UNIVASF / JUAZEIRO",
    ]

    turnos_validos = sorted(df['turno'].unique())
    print("\nTurnos disponíveis para análise de ocupação:")
    for i, t in enumerate(turnos_validos, 1):
        print(f"  {i} - {t}")

    while True:
        try:
            opcao = int(input("\nDigite o número do turno desejado: ").strip())
            if 1 <= opcao <= len(turnos_validos):
                turno_escolhido = turnos_validos[opcao - 1]
                break
            else:
                print(f"Opção inválida. Escolha um número entre 1 e {len(turnos_validos)}.")
        except ValueError:
            print("Digite um número válido.")

    if turno_escolhido not in MAPA_TURNOS:
        print(f"Erro: o turno '{turno_escolhido}' não está no MAPA_TURNOS. Atualize o dicionário.")
        exit(1)
    turno_idx = MAPA_TURNOS[turno_escolhido]

    try:
        d, t, ocup, ocup_max = calcular_rota_com_ocupacao_grafos(rota, turno_idx, nos)
        print(f"\n--- TURNO: {turno_escolhido} ---")
        print(f"Distância: {d:.2f} km | Tempo: {t} min")
        print("Evolução da ocupação:")
        for p in ocup:
            print(f"  {p['parada']}: +{p['embarques']}/-{p['desembarques']} → {p['ocupacao_apos']} passageiros")
        print(f"\nOcupação máxima: {ocup_max} passageiros")
    except Exception as e:
        print(f"Erro: {e}")