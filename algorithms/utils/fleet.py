"""
fleet.py
--------
Define os modelos de ônibus utilizados pelo algoritmo.

Enquanto os dados reais da frota não estão disponíveis, utiliza-se
um modelo genérico baseado em parâmetros típicos de ônibus urbanos
a diesel operando no Brasil.

Quando os dados reais forem fornecidos, basta substituir o
ONIBUS_GENERICO ou adicionar novos modelos na lista FROTA.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ModeloOnibus:
    """
    Representa um modelo de ônibus com suas características operacionais.

    Atributos:
        nome         : identificação do modelo
        capacidade   : número máximo de passageiros (sentados)
        consumo_km_l : consumo médio em km/litro
        custo_litro  : preço do litro do diesel (R$)
        observacoes  : notas extras (opcional)
    """
    nome:          str
    capacidade:    int
    consumo_km_l:  float
    custo_litro:   float
    observacoes:   str = ""

    @property
    def custo_por_km(self) -> float:
        """Custo operacional de combustível por quilômetro (R$/km)."""
        return round(self.custo_litro / self.consumo_km_l, 4)

    def custo_rota(self, distancia_km: float) -> float:
        """Custo total de combustível para percorrer uma rota (R$)."""
        return round(distancia_km * self.custo_por_km, 2)

    def __repr__(self) -> str:
        return (
            f"{self.nome} | cap={self.capacidade} pass. | "
            f"{self.consumo_km_l} km/L | R${self.custo_litro}/L → "
            f"R${self.custo_por_km:.4f}/km"
        )


# ── Modelo genérico ───────────────────────────────────────────────────────────
# Baseado em parâmetros típicos de ônibus urbanos/rodoviários a diesel no Brasil.
# Substitua pelos dados reais da frota UNIVASF quando disponíveis.

ONIBUS_GENERICO = ModeloOnibus(
    nome         = "Genérico (substituir pelos dados reais)",
    capacidade   = 48,          # passageiros sentados — padrão ônibus urbano
    consumo_km_l = 2.8,         # km/litro — média urbano/rodoviário diesel
    custo_litro  = 6.80,        # R$/litro — diesel S-10 referência Mai/2026
    observacoes  = (
        "Modelo placeholder. Substituir por: fabricante, modelo, ano, "
        "capacidade real, consumo real do veículo e preço do combustível "
        "praticado pela UNIVASF."
    ),
)

# ── Lista da frota (adicionar modelos reais aqui) ─────────────────────────────
# Quando houver dados reais, adicione cada modelo da frota UNIVASF nesta lista.
# O algoritmo poderá então alocar o modelo mais adequado para cada rota.
#
# Exemplo de como adicionar um modelo real:
#
#   ONIBUS_MERCEDES_OF1721 = ModeloOnibus(
#       nome         = "Mercedes-Benz OF 1721",
#       capacidade   = 44,
#       consumo_km_l = 3.1,
#       custo_litro  = 6.80,
#   )
#
#   FROTA = [ONIBUS_MERCEDES_OF1721, ...]

FROTA: list[ModeloOnibus] = [ONIBUS_GENERICO]


def modelo_por_nome(nome: str) -> Optional[ModeloOnibus]:
    """Busca um modelo da frota pelo nome (case-insensitive)."""
    nome_lower = nome.lower()
    for m in FROTA:
        if nome_lower in m.nome.lower():
            return m
    return None


def imprimir_frota() -> None:
    """Exibe todos os modelos cadastrados."""
    print("\n" + "=" * 60)
    print("FROTA CADASTRADA")
    print("=" * 60)
    for i, m in enumerate(FROTA, 1):
        print(f"\n  [{i}] {m}")
        if m.observacoes:
            print(f"      ⚠  {m.observacoes}")
    print()
