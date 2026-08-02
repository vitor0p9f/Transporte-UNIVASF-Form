"""
vrp_adapter.py
--------------
Traduz os rótulos da branch python/VRP (stops/*.json) para os nomes
canônicos do banco de dados / trips.csv, e constrói a matriz de distâncias
real sobreposta à sintética.

Uso principal via convert_vrp_stops.py.
"""

# ── Mapeamento VRP label → nome canônico (trips.csv / database.sql) ───────────
VRP_TO_CANONICAL: dict[str, str] = {
    # Campuses UNIVASF
    "UNIVASF / PETROLINA":                                  "UNIVASF Campus Petrolina",
    "UNIVASF / JUAZEIRO":                                   "UNIVASF Campus Juazeiro",
    "UNIVASF CCA / PETROLINA":                              "UNIVASF Campus CCA",
    "BLOCO DE SALAS DO CCA / PETROLINA":                    "Bloco de Salas de Aula CCA",
    "BLOCO VELHO DO CCA / PETROLINA":                       "UNIVASF Campus Ciências Agrárias – Bloco Antigo",
    "ALOJAMENTO ESTUDANTIL DO CCA / PETROLINA":             "Residência Estudantil CCA",
    "CLÍNICA VETERINÁRIA UNIVERSITÁRIA DO CCA / PETROLINA": "Hospital Veterinário CCA",

    # Juazeiro
    "CAMELÓDROMO 2 DE JULHO / JUAZEIRO":                    "Terminal de Juazeiro – Camelódromo 2 de Julho",
    "ESTAÇÃO ANTIGA / JUAZEIRO":                            "Estação Velha Juazeiro",
    "LOJAS AMERICANAS / JUAZEIRO":                          "Rua do Paraíso ao lado das Lojas Americanas",
    "GBARBOSA ADOLFO VIANA / JUAZEIRO":                     "GBarbosa Juazeiro – Av. Adolfo Viana",
    "GBARBOSA SANTO ANTONIO / JUAZEIRO":                    "GBarbosa Juazeiro",
    "POSTO RAUL LINS ENTRADA DO BAIRRO CASTELO BRANCO / JUAZEIRO": "Posto Raul Lins / Bairro Castelo Branco",
    "VERDÃO / JUAZEIRO":                                    "Verdão Juazeiro",

    # Petrolina – vias urbanas / pontos comerciais
    "ACADEMIA I9 / PETROLINA":                              "Academia I9",
    "ABARÉ RADIADORES / PETROLINA":                         "Abaré",
    "ALDIEGAS / PETROLINA":                                 "Ponto Aldiegas",
    "ANTIGA ESTAÇÃO FERROVIÁRIA / PETROLINA":               "Estação Velha / Cooperativa Brasil",
    "ANTIGO BAR DA TRIPA / PETROLINA":                      "Antigo Bar da Tripa – Av. Monsenhor Ângelo Sampaio",
    "BEIRA RIO REVENDA AMBEV / PETROLINA":                  "Distribuidora de Bebidas Revalle",
    "CLÍNICA POPULAR BAIRRO AREIA BRANCA / PETROLINA":      "Clínica Popular Av. São Francisco (Areia Branca)",
    "CONDOMÍNIO MAIS VIVER / PETROLINA":                    "Estrada da Banana – Condomínio Mais Viver",
    "CONSTRUTEO / PETROLINA":                               "Costrutéo (ponto de ônibus)",
    "DETRAN / PETROLINA":                                   "DETRAN – Av. Monsenhor (via principal)",
    "DR DISTRIBUIDORA / PETROLINA":                         "Ponto BR 428 – DR Distribuidora (Vila Marcela)",
    "FEIRA DA COHAB MASSANGANO / PETROLINA":                "Feira da COHAB Massangano",
    "GBARBOSA AV. MONSENHOR ÂNGELO SAMPAIO / PETROLINA":    "GBarbosa Av. Monsenhor Ângelo Sampaio",
    "HOTEL E POUSADA CARRANCA / PETROLINA":                 "Ponto BR 428 – Posto Carranca",
    "IGREJA FILADÉLFIA / PETROLINA":                        "Igreja Filadélfia",
    "ISAÍAS VEÍCULOS / PETROLINA":                          "BR 407 – Isaías Automóveis / Posto Delta",
    "IZABELLA MATERIAL DE CONSTRUÇÃO BAIRRO COSME E DAMIÃO / PETROLINA": "BR 407 – Izabela Construções",
    "LOJA DE MATERIAL DE CONSTRUÇÃO CANTEIRO DE OBRAS / PETROLINA": "Canteiro de Obras Av. 7 de Setembro",
    "MECÂNICA OURO DIESEL / PETROLINA":                     "Mecânica Ouro Diesel",
    "MINISTÉRIO PÚBLICO FEDERAL / PETROLINA":               "Ministério Público Federal",
    "NUTIVA AGRO / PETROLINA":                              "Av. Transnordestina – Nutiva Agro",
    "PARK MUNDO DA LUA / PETROLINA":                        "Parque Mundo da Lua",
    "PETRAPE / PETROLINA":                                  "Petrape",
    "PLANTE BEM MATRIZ / PETROLINA":                        "Plante Bem",
    "POSTO ALE / PETROLINA":                                "Posto ALE",
    "POSTO BBB / PETROLINA":                                "Posto de Gasolina Big Brother",
    "POSTO VALE DOURADO ENTRADA DO BAIRRO PEDRA LINDA / PETROLINA": "Av. Transnordestina – Posto Pedra Linda",
    "RESTAURANTE DONA BRANCA / PETROLINA":                  "Estrada da Banana – Restaurante Dona Branca",
    "SEMENTEIRA / PETROLINA":                               "Sementeira",
    "SUCATÃO MORÃES / PETROLINA":                           "Ponto BR 428 – Sucatão Moraes (Loteamento Recife)",
    "SUPERMERCADO REGENTE AV. SOUZA FILHO / PETROLINA":     "Supermercado Regente",
    "TERMINAL RODOVIÁRIO / PETROLINA":                      "Rodoviária de Petrolina",
}

# ── Nomes alternativos no trips.csv → nome canônico ───────────────────────────
# Múltiplas variantes de nome para o mesmo ponto físico.
# Todas as variantes são mapeadas para o mesmo nó na matriz de distâncias.
ALIAS_TO_CANONICAL: dict[str, str] = {
    # CCA - bloco velho / antigo
    "UNIVASF Campus CCA – Bloco Antigo":    "UNIVASF Campus Ciências Agrárias – Bloco Antigo",
    "Bloco Antigo CCA":                     "UNIVASF Campus Ciências Agrárias – Bloco Antigo",

    # Hospital Veterinário (ponto dentro do CCA)
    "Hospital Veterinário":                 "Hospital Veterinário CCA",

    # Academia I9 — variante com endereço
    "Academia I9 – Av. 7 de Setembro":      "Academia I9",

    # Posto Raul Lins — duas variantes do mesmo ponto
    "Posto Raul Lins – Entrada Castelo Branco": "Posto Raul Lins / Bairro Castelo Branco",

    # GBarbosa Petrolina — variante do mesmo supermercado
    "GBarbosa Petrolina":                   "GBarbosa Av. Monsenhor Ângelo Sampaio",
    "GBarbosa Petrolina – Av. Monsenhor Ângelo Sampaio": "GBarbosa Av. Monsenhor Ângelo Sampaio",

    # Estação Velha Juazeiro — variante com nome comercial
    "Estação Velha / Cooperativa Brasil":   "Estação Velha Juazeiro",

    # Sementeira — variantes com indicação de avenida
    "Sementeira – Av. da Integração":       "Sementeira",
    "Av. da Integração – Sementeira":       "Sementeira",

    # Petrape — variantes com indicação de avenida
    "Petrape – Av. da Integração":          "Petrape",
    "Av. da Integração – Petrape":          "Petrape",

    # Parque Mundo da Lua — variante pela av. da integração
    "Av. da Integração – Mundo da Lua":     "Parque Mundo da Lua",

    # Izabela Construções — variante com contexto de turno
    "Izabela Construções (Cosme Damião / sentido CCA)": "BR 407 – Izabela Construções",

    # Canteiro de Obras — variantes por localização/direção
    "Canteiro de Obras":                    "Canteiro de Obras Av. 7 de Setembro",
    "Canteiro de Obras – Av. 7 de Setembro": "Canteiro de Obras Av. 7 de Setembro",
    "Canteiro de Obras – Juazeiro":         "Canteiro de Obras Av. 7 de Setembro",

    # Mecânica Ouro Diesel — variante com endereço
    "Mecânica Ouro Diesel – Av. 7 de Setembro": "Mecânica Ouro Diesel",

    # Aldiegas — duas variantes de nome de ponto
    "Av. 7 de Setembro – Aldiegas":         "Ponto Aldiegas",

    # Abaré — variante do ponto de embarque
    "Ponto em frente à Abaré":              "Abaré",

    # Posto Pedra Linda — variante com nome mais longo
    "Av. Transnordestina – Posto de Combustível / Bairro Pedra Linda": "Av. Transnordestina – Posto Pedra Linda",

    # Secretaria de Obras — variante com avenida
    "Secretaria de Obras – Av. da Integração": "Secretaria de Obras",
    "Av. da Integração – Secretaria de Obras":  "Secretaria de Obras",
}


def canonical(name: str) -> str:
    """
    Retorna o nome canônico para um rótulo VRP ou alias trips.csv.
    Se não há mapeamento, retorna o próprio nome.
    """
    if name in VRP_TO_CANONICAL:
        return VRP_TO_CANONICAL[name]
    if name in ALIAS_TO_CANONICAL:
        return ALIAS_TO_CANONICAL[name]
    return name


def construir_matriz_real(vrp_stops: list[dict], metrica: str = "distance") -> dict[str, dict[str, float]]:
    """
    A partir da lista de stops da branch python/VRP (label em VRP naming),
    retorna uma matriz de distâncias reais indexada por nomes canônicos.

        real[origem_canonical][destino_canonical] = float (km ou min)
    """
    real: dict[str, dict[str, float]] = {}

    for stop in vrp_stops:
        vrp_label = stop.get("label", "")
        origem = canonical(vrp_label)
        if origem not in real:
            real[origem] = {}

        for edge in stop.get("edges", []):
            destino_vrp = edge.get("destination", "")
            destino = canonical(destino_vrp)
            valor = edge.get(metrica, None)
            if valor is not None and destino:
                # Usa a menor distância se existir duplicata por alias
                if destino not in real[origem] or valor < real[origem][destino]:
                    real[origem][destino] = float(valor)

    return real
