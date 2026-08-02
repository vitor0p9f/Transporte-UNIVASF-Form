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
    capacidade_conforto: Optional[int] = None   # lotação confortável (sentados);
                                                 # None → usa `capacidade`
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

# ── Modelo de referência para os cálculos ─────────────────────────────────────
# Parâmetros baseados em ônibus rodoviários/urbanos a diesel tipicamente
# utilizados em rotas intermunicipais de universidades públicas do NE brasileiro.
#
# Consumo médio 3,0 km/L considera o perfil misto da rota UNIVASF:
#   — trecho urbano Petrolina/Juazeiro (~8 km): ~2,5 km/L
#   — rodovia Transnordestina até CCA (~18 km): ~3,5 km/L
#   — média ponderada ≈ 3,0 km/L
#
# Diesel S-10 (ANP, referência NE Brasil, mai/2026): R$ 6,80/L
# → Custo operacional ≈ R$ 2,27/km
#
# Capacidade de conforto (36) = todos sentados; capacidade máxima (44)
# inclui passageiros em pé (corredor), situação frequente nos turnos manhã_1
# e noite_1 (lotação média percebida de 4,4/5 e 4,0/5 respectivamente).
#
# Para substituir pelos dados reais: consultar o contrato de fretamento da
# UNIVASF (PRAD/DITIN) — fabricante, modelo, ano, placa, capacidade homologada
# e consumo certificado do veículo.

ONIBUS_GENERICO = ModeloOnibus(
    nome         = "Ônibus rodoviário — referência NE Brasil",
    capacidade   = 44,
    consumo_km_l = 3.0,
    custo_litro  = 6.80,
    capacidade_conforto = 36,
    observacoes  = (
        "Parâmetros de referência para o transporte UNIVASF (Petrolina–CCA). "
        "Substituir por fabricante, modelo, ano, capacidade e consumo reais "
        "do contrato de fretamento vigente."
    ),
)

# ── Frota UNIVASF (identificada no banco de dados) ────────────────────────────
# O database.sql registra 10 ônibus (A–D, E–F, G–H, J, L) operando nos turnos.
# Enquanto as especificações técnicas reais não são fornecidas, todos os modelos
# compartilham os parâmetros do ONIBUS_GENERICO.  Quando disponíveis, crie
# instâncias distintas de ModeloOnibus para cada veículo/modelo da frota real.

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
