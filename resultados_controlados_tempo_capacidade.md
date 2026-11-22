# Resultados controlados — Tempo e Capacidade

Gerado em 2026-11-22 13:56.

As restrições de tempo e de capacidade estão ativas nas duas heurísticas. Os cenários são a cópia controlada (`scenarios_control.csv` + `scenarios_base_control.csv`) e a frota é a homogênea de `fleet_control.csv`: todos os ônibus são o modelo de menor capacidade do `fleet.csv` (24 lugares e 4.61 km/L). As origens e os destinos permitidos vêm das colunas `origin` e `destination_labels` do cenário, as mesmas para as duas heurísticas, e o Clarke-Wright é limitado ao número de ônibus da frota.

O **TOP (custo)** pontua passageiros por real: cada rota paga o combustível (km / km por litro do ônibus × diesel do cenário) e o motorista (horas × valor da hora do cenário). Maximizar passageiros por real é equivalente a minimizar o custo por passageiro; na inserção de uma parada, o score marginal minimiza o custo por passageiro extra. O custo mostrado é recalculado por ônibus a partir das rotas finais, cobrando apenas as rotas que atendem alguém.

O **Clarke-Wright** usa esse mesmo custo operacional (combustível + motorista) no cálculo das economias, na escolha de direção e terminais, na seleção por lambda e nas melhorias locais. Assim, o critério que constrói as rotas coincide com o custo exibido na tabela.

| Cenário | Instância | Período | Heurística | Passageiros atendidos / Total | Ônibus usados / Frota | Maior rota / Limite (min) | Pico / Capacidade de referência | Diesel (R$/L) | Motorista (R$/h) | Custo operacional (R$) | Custo por passageiro (R$) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 | p1_4_b | night_2 | TOP (custo) | 37/59 | 4/12 | 104/106 | 3/24 | 5.91 | 33.94 | 458.21 | 12.38 |
| 16 | p1_4_b | night_2 | Clarke-Wright | 21/59 | 3/12 | 87/106 | 6/24 | 5.91 | 33.94 | 260.22 | 12.39 |
| 19 | p1_4_r | afternoon_2 | TOP (custo) | 59/66 | 7/7 | 144/171 | 3/24 | 6.41 | 28.41 | 994.22 | 16.85 |
| 19 | p1_4_r | afternoon_2 | Clarke-Wright | 23/66 | 3/7 | 111/171 | 8/24 | 6.41 | 28.41 | 283.21 | 12.31 |
| 32 | p1_3_h | morning_2 | TOP (custo) | 48/54 | 6/12 | 146/146 | 4/24 | 5.65 | 31.42 | 791.76 | 16.50 |
| 32 | p1_3_h | morning_2 | Clarke-Wright | 17/54 | 3/12 | 119/146 | 5/24 | 5.65 | 31.42 | 281.96 | 16.59 |
| 65 | base | morning_1 | TOP (custo) | 196/198 | 8/12 | 118/120 | 22/24 | 6.00 | 25.00 | 820.03 | 4.18 |
| 65 | base | morning_1 | Clarke-Wright | 70/198 | 9/12 | 101/120 | 17/24 | 6.00 | 25.00 | 345.02 | 4.93 |
| 69 | base | night_1 | TOP (custo) | 158/158 | 11/12 | 117/120 | 24/24 | 6.00 | 25.00 | 784.59 | 4.97 |
| 69 | base | night_1 | Clarke-Wright | 88/158 | 6/12 | 67/120 | 18/24 | 6.00 | 25.00 | 302.24 | 3.43 |

## Verificação global de ocupação

Esta tabela é complementar. O indicador `Pico / Capacidade de referência` acima continua associado à rota mais longa; aqui o pico simultâneo é procurado em todas as rotas e comparado com a capacidade física original do ônibus.

| Cenário | Heurística | Pico global / Capacidade física | Ônibus do pico | Rota do pico | Rotas acima da capacidade | Maior excedente | Ônibus/rota do maior excedente |
|---|---|---|---|---|---|---|---|
| 16 | TOP (custo) | 8/24 | 1 | 1 -> 16 -> 13 -> 6 -> 4 -> 15 -> 14 -> 7 | 0 | 0 | — |
| 16 | Clarke-Wright | 6/24 | 3 | 1 -> 32 -> 18 -> 29 -> 17 -> 16 -> 15 -> 14 -> 4 -> 7 -> 13 -> 5 | 0 | 0 | — |
| 19 | TOP (custo) | 8/24 | 1 | 5 -> 2 -> 13 -> 8 -> 21 -> 11 -> 10 -> 1 -> 29 -> 17 -> 14 -> 16 -> 3 | 0 | 0 | — |
| 19 | Clarke-Wright | 8/24 | 2 | 5 -> 4 -> 14 -> 15 -> 16 -> 17 -> 29 -> 30 -> 31 -> 25 -> 12 -> 9 -> 11 -> 10 | 0 | 0 | — |
| 32 | TOP (custo) | 7/24 | 1 | 27 -> 21 -> 8 -> 5 -> 7 -> 10 -> 17 -> 32 -> 23 -> 26 -> 31 | 0 | 0 | — |
| 32 | Clarke-Wright | 5/24 | 1 | 27 -> 20 -> 21 -> 30 -> 23 -> 12 -> 11 -> 10 -> 8 -> 2 -> 3 -> 7 -> 4 -> 5 -> 6 | 0 | 0 | — |
| 65 | TOP (custo) | 24/24 | 2 | 44 -> 9 -> 24 -> 7 -> 38 -> 30 -> 40 -> 36 -> 8 -> 19 -> 45 | 0 | 0 | — |
| 65 | Clarke-Wright | 17/24 | 4 | 44 -> 41 -> 16 -> 36 -> 27 -> 12 -> 7 -> 8 -> 4 -> 25 -> 38 -> 44 | 0 | 0 | — |
| 69 | TOP (custo) | 24/24 | 1 | 45 -> 25 -> 21 -> 34 -> 30 -> 7 -> 18 -> 5 -> 44 | 0 | 0 | — |
| 69 | Clarke-Wright | 23/24 | 6 | 43 -> 7 -> 25 -> 19 -> 28 -> 2 -> 29 -> 44 | 0 | 0 | — |

