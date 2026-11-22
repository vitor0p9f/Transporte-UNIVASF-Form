# Resultados controlados — Apenas Restrição Temporal

Gerado em 2026-11-22 13:56.

Apenas o limite de tempo está ativo: a capacidade foi desativada nas decisões e na avaliação das duas heurísticas (frota com capacidade infinita). Os cenários são a cópia controlada (`scenarios_control.csv` + `scenarios_base_control.csv`) e a frota é a homogênea de `fleet_control.csv`: todos os ônibus são o modelo de menor capacidade do `fleet.csv` (24 lugares e 4.61 km/L). As origens e os destinos permitidos vêm das colunas `origin` e `destination_labels` do cenário, as mesmas para as duas heurísticas, e o Clarke-Wright é limitado ao número de ônibus da frota.

O **TOP (custo)** pontua passageiros por real: cada rota paga o combustível (km / km por litro do ônibus × diesel do cenário) e o motorista (horas × valor da hora do cenário). Maximizar passageiros por real é equivalente a minimizar o custo por passageiro; na inserção de uma parada, o score marginal minimiza o custo por passageiro extra. O custo mostrado é recalculado por ônibus a partir das rotas finais, cobrando apenas as rotas que atendem alguém.

O **Clarke-Wright** usa esse mesmo custo operacional (combustível + motorista) no cálculo das economias, na escolha de direção e terminais, na seleção por lambda e nas melhorias locais. Assim, o critério que constrói as rotas coincide com o custo exibido na tabela.

| Cenário | Instância | Período | Heurística | Passageiros atendidos / Total | Ônibus usados / Frota | Maior rota / Limite (min) | Pico / Capacidade de referência | Diesel (R$/L) | Motorista (R$/h) | Custo operacional (R$) | Custo por passageiro (R$) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 | p1_4_b | night_2 | TOP (custo) | 37/59 | 4/12 | 104/106 | 3/24 | 5.91 | 33.94 | 458.21 | 12.38 |
| 16 | p1_4_b | night_2 | Clarke-Wright | 23/59 | 2/12 | 99/106 | 9/24 | 5.91 | 33.94 | 207.53 | 9.02 |
| 19 | p1_4_r | afternoon_2 | TOP (custo) | 59/66 | 7/7 | 144/171 | 3/24 | 6.41 | 28.41 | 994.22 | 16.85 |
| 19 | p1_4_r | afternoon_2 | Clarke-Wright | 30/66 | 1/7 | 171/171 | 20/24 | 6.41 | 28.41 | 190.69 | 6.36 |
| 32 | p1_3_h | morning_2 | TOP (custo) | 48/54 | 6/12 | 146/146 | 4/24 | 5.65 | 31.42 | 791.76 | 16.50 |
| 32 | p1_3_h | morning_2 | Clarke-Wright | 26/54 | 1/12 | 146/146 | 18/24 | 5.65 | 31.42 | 159.38 | 6.13 |
| 65 | base | morning_1 | TOP (custo) | 198/198 | 7/12 | 118/120 | 84/24 | 6.00 | 25.00 | 660.73 | 3.34 |
| 65 | base | morning_1 | Clarke-Wright | 140/198 | 2/12 | 111/120 | 108/24 | 6.00 | 25.00 | 162.21 | 1.16 |
| 69 | base | night_1 | TOP (custo) | 158/158 | 7/12 | 115/120 | 18/24 | 6.00 | 25.00 | 517.81 | 3.28 |
| 69 | base | night_1 | Clarke-Wright | 128/158 | 2/12 | 120/120 | 116/24 | 6.00 | 25.00 | 144.17 | 1.13 |

## Verificação global de ocupação

Esta tabela é complementar. O indicador `Pico / Capacidade de referência` acima continua associado à rota mais longa; aqui o pico simultâneo é procurado em todas as rotas e comparado com a capacidade física original do ônibus.

| Cenário | Heurística | Pico global / Capacidade física | Ônibus do pico | Rota do pico | Rotas acima da capacidade | Maior excedente | Ônibus/rota do maior excedente |
|---|---|---|---|---|---|---|---|
| 16 | TOP (custo) | 8/24 | 1 | 1 -> 16 -> 13 -> 6 -> 4 -> 15 -> 14 -> 7 | 0 | 0 | — |
| 16 | Clarke-Wright | 9/24 | 1 | 1 -> 32 -> 19 -> 20 -> 27 -> 31 -> 30 -> 26 -> 25 -> 24 -> 23 -> 22 -> 21 -> 12 -> 11 -> 10 -> 9 -> 8 -> 2 -> 3 -> 7 | 0 | 0 | — |
| 19 | TOP (custo) | 8/24 | 1 | 5 -> 2 -> 13 -> 8 -> 21 -> 11 -> 10 -> 1 -> 29 -> 17 -> 14 -> 16 -> 3 | 0 | 0 | — |
| 19 | Clarke-Wright | 20/24 | 1 | 5 -> 4 -> 14 -> 15 -> 16 -> 17 -> 29 -> 28 -> 1 -> 32 -> 18 -> 13 -> 6 -> 7 -> 3 -> 2 -> 8 -> 9 -> 10 -> 11 -> 12 -> 21 -> 19 -> 27 -> 31 -> 30 -> 26 -> 20 -> 22 -> 25 -> 24 | 0 | 0 | — |
| 32 | TOP (custo) | 7/24 | 1 | 27 -> 21 -> 8 -> 5 -> 7 -> 10 -> 17 -> 32 -> 23 -> 26 -> 31 | 0 | 0 | — |
| 32 | Clarke-Wright | 18/24 | 1 | 18 -> 32 -> 28 -> 29 -> 17 -> 16 -> 15 -> 14 -> 4 -> 5 -> 6 -> 7 -> 3 -> 2 -> 8 -> 10 -> 11 -> 12 -> 21 -> 22 -> 23 -> 24 -> 25 -> 26 -> 30 -> 31 | 0 | 0 | — |
| 65 | TOP (custo) | 84/24 | 1 | 44 -> 20 -> 45 -> 37 -> 40 -> 38 -> 30 -> 35 -> 19 -> 25 -> 39 -> 8 -> 7 -> 44 | 3 | 60 | 1: 44 -> 20 -> 45 -> 37 -> 40 -> 38 -> 30 -> 35 -> 19 -> 25 -> 39 -> 8 -> 7 -> 44 |
| 65 | Clarke-Wright | 108/24 | 2 | 44 -> 17 -> 34 -> 46 -> 21 -> 9 -> 45 -> 37 -> 24 -> 31 -> 39 -> 19 -> 35 -> 30 -> 40 -> 38 -> 36 -> 27 -> 25 -> 4 -> 8 -> 12 -> 7 -> 43 | 1 | 84 | 2: 44 -> 17 -> 34 -> 46 -> 21 -> 9 -> 45 -> 37 -> 24 -> 31 -> 39 -> 19 -> 35 -> 30 -> 40 -> 38 -> 36 -> 27 -> 25 -> 4 -> 8 -> 12 -> 7 -> 43 |
| 69 | TOP (custo) | 46/24 | 1 | 45 -> 25 -> 7 -> 43 -> 12 -> 8 -> 23 -> 29 -> 40 -> 31 -> 30 -> 18 -> 5 -> 44 | 3 | 22 | 1: 45 -> 25 -> 7 -> 43 -> 12 -> 8 -> 23 -> 29 -> 40 -> 31 -> 30 -> 18 -> 5 -> 44 |
| 69 | Clarke-Wright | 116/24 | 2 | 43 -> 7 -> 12 -> 8 -> 25 -> 36 -> 14 -> 32 -> 23 -> 19 -> 28 -> 31 -> 30 -> 40 -> 1 -> 2 -> 22 -> 15 -> 20 -> 26 -> 29 -> 37 -> 18 -> 5 -> 9 -> 21 -> 34 -> 46 -> 44 | 1 | 92 | 2: 43 -> 7 -> 12 -> 8 -> 25 -> 36 -> 14 -> 32 -> 23 -> 19 -> 28 -> 31 -> 30 -> 40 -> 1 -> 2 -> 22 -> 15 -> 20 -> 26 -> 29 -> 37 -> 18 -> 5 -> 9 -> 21 -> 34 -> 46 -> 44 |

