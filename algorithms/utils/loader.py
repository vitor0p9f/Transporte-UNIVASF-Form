"""
loader.py
---------
Carrega e pré-processa os dados exportados do Supabase (viagens.csv)
para o formato interno usado pelos algoritmos de otimização.

Saída principal:
  - demand: dict[turno_slug -> dict[parada -> {"boarding": int, "alighting": int}]]
  - avg_load: dict[turno_slug -> dict[parada -> float]]  (lotação média percebida)
"""

import pandas as pd
from pathlib import Path
from collections import defaultdict

# Caminho padrão do CSV exportado do Supabase
DATA_DIR = Path(__file__).parent.parent / "data"
DEFAULT_CSV = DATA_DIR / "viagens.csv"

# Turnos válidos (slugs conforme cadastrado no Supabase)
TURNOS_VALIDOS = ["manha_1", "manha_2", "tarde_1", "tarde_2", "noite_1", "noite_2"]


def carregar_viagens(caminho_csv: Path = DEFAULT_CSV) -> pd.DataFrame:
    """
    Lê o CSV exportado do Supabase e retorna um DataFrame limpo.

    Passos:
      1. Lê o arquivo CSV
      2. Remove linhas duplicadas por e-mail + turno (mantém a mais recente)
      3. Remove linhas com campos obrigatórios nulos
      4. Filtra apenas turnos válidos
    """
    if not caminho_csv.exists():
        raise FileNotFoundError(
            f"Arquivo não encontrado: {caminho_csv}\n"
            f"Exporte a tabela 'viagens' do Supabase como CSV e coloque em: {DATA_DIR}"
        )

    df = pd.read_csv(caminho_csv, parse_dates=["created_at"])

    # Remove colunas desnecessárias para o algoritmo
    colunas_necessarias = ["id", "email", "turno", "embarque", "desembarque", "lotacao", "created_at"]
    df = df[[c for c in colunas_necessarias if c in df.columns]]

    # Remove linhas com campos obrigatórios nulos
    df = df.dropna(subset=["turno", "embarque", "desembarque", "lotacao"])

    # Filtra turnos válidos
    df = df[df["turno"].isin(TURNOS_VALIDOS)]

    # Remove duplicatas por e-mail + turno: mantém a mais recente
    if "email" in df.columns and "created_at" in df.columns:
        df = df.sort_values("created_at", ascending=False)
        df = df.drop_duplicates(subset=["email", "turno"], keep="first")

    df["lotacao"] = pd.to_numeric(df["lotacao"], errors="coerce").fillna(0).astype(int)

    print(f"[loader] {len(df)} viagens carregadas de '{caminho_csv.name}'")
    return df.reset_index(drop=True)


def construir_demanda(df: pd.DataFrame) -> dict:
    """
    Agrega os dados de viagens em demanda por turno e parada.

    Retorna:
        demand[turno][parada] = {
            "boarding": int,    # nº de pessoas que embarcam nessa parada
            "alighting": int,   # nº de pessoas que desembarcam nessa parada
            "avg_load": float,  # lotação média percebida (1-5)
        }
    """
    demand = defaultdict(lambda: defaultdict(lambda: {"boarding": 0, "alighting": 0, "loads": []}))

    for _, row in df.iterrows():
        turno     = row["turno"]
        embarque  = str(row["embarque"]).strip()
        desemb    = str(row["desembarque"]).strip()
        lotacao   = int(row["lotacao"])

        demand[turno][embarque]["boarding"]  += 1
        demand[turno][embarque]["loads"].append(lotacao)

        demand[turno][desemb]["alighting"]   += 1

    # Calcula média de lotação e limpa lista auxiliar
    resultado = {}
    for turno, paradas in demand.items():
        resultado[turno] = {}
        for parada, vals in paradas.items():
            avg = round(sum(vals["loads"]) / len(vals["loads"]), 2) if vals["loads"] else 0.0
            resultado[turno][parada] = {
                "boarding":  vals["boarding"],
                "alighting": vals["alighting"],
                "avg_load":  avg,
            }

    return resultado


def resumo_demanda(demand: dict) -> None:
    """Imprime um resumo legível da demanda por turno."""
    print("\n" + "=" * 60)
    print("RESUMO DE DEMANDA POR TURNO")
    print("=" * 60)

    for turno in TURNOS_VALIDOS:
        if turno not in demand:
            print(f"\n[{turno}] — sem dados")
            continue

        paradas = demand[turno]
        total_embarques  = sum(p["boarding"]  for p in paradas.values())
        total_desembarques = sum(p["alighting"] for p in paradas.values())
        carga_media = round(
            sum(p["avg_load"] for p in paradas.values() if p["avg_load"] > 0)
            / max(1, sum(1 for p in paradas.values() if p["avg_load"] > 0)),
            2
        )

        print(f"\n[{turno}]")
        print(f"  Paradas com demanda : {len(paradas)}")
        print(f"  Total embarques     : {total_embarques}")
        print(f"  Total desembarques  : {total_desembarques}")
        print(f"  Lotação média       : {carga_media}/5")


def carregar_tudo(caminho_csv: Path = DEFAULT_CSV) -> tuple[pd.DataFrame, dict]:
    """
    Função conveniente: carrega CSV + constrói demanda.

    Uso:
        from utils.loader import carregar_tudo
        df, demand = carregar_tudo()
    """
    df = carregar_viagens(caminho_csv)
    demand = construir_demanda(df)
    resumo_demanda(demand)
    return df, demand
