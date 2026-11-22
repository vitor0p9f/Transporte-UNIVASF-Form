# Resultados controlados — Tempo e Capacidade

Gerado em 2026-11-21 22:49.

As restrições de tempo e de capacidade estão ativas nas duas heurísticas. Os cenários são a cópia controlada (`scenarios_control.csv` + `scenarios_base_control.csv`) e a frota é a homogênea de `fleet_control.csv`: todos os ônibus são o modelo de menor capacidade do `fleet.csv` (24 lugares e 4.61 km/L). As origens e os destinos permitidos vêm das colunas `origin` e `destination_labels` do cenário, as mesmas para as duas heurísticas, e o Clarke-Wright é limitado ao número de ônibus da frota.

O **TOP (custo)** pontua passageiros por real: cada rota paga o combustível (km / km por litro do ônibus × diesel do cenário) e o motorista (horas × valor da hora do cenário). Maximizar passageiros por real é equivalente a minimizar o custo por passageiro; na inserção de uma parada, o score marginal minimiza o custo por passageiro extra. O custo mostrado é recalculado por ônibus a partir das rotas finais, cobrando apenas as rotas que atendem alguém.

| Cenário | Instância | Período | Heurística | Passageiros atendidos / Total | Ônibus usados / Frota | Maior rota / Limite (min) | Pico / Capacidade de referência | Diesel (R$/L) | Motorista (R$/h) | Custo operacional (R$) | Custo por passageiro (R$) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 | p1_4_b | night_2 | TOP (custo) | 37/59 | 4/12 | 104/106 | 3/24 | 5.91 | 33.94 | 458.21 | 12.38 |
| 16 | p1_4_b | night_2 | Clarke-Wright | 18/59 | 3/12 | 105/106 | 6/24 | 5.91 | 33.94 | 324.64 | 18.04 |
| 19 | p1_4_r | afternoon_2 | TOP (custo) | 59/66 | 7/7 | 144/171 | 3/24 | 6.41 | 28.41 | 994.22 | 16.85 |
| 19 | p1_4_r | afternoon_2 | Clarke-Wright | 29/66 | 3/7 | 132/171 | 11/24 | 6.41 | 28.41 | 310.62 | 10.71 |
| 32 | p1_3_h | morning_2 | TOP (custo) | 48/54 | 6/12 | 146/146 | 4/24 | 5.65 | 31.42 | 791.76 | 16.50 |
| 32 | p1_3_h | morning_2 | Clarke-Wright | 17/54 | 3/12 | 102/146 | 5/24 | 5.65 | 31.42 | 259.34 | 15.26 |
| 65 | base | morning_1 | TOP (custo) | 196/198 | 8/12 | 118/120 | 22/24 | 6.00 | 25.00 | 820.03 | 4.18 |
| 65 | base | morning_1 | Clarke-Wright | 75/198 | 9/12 | 73/120 | 24/24 | 6.00 | 25.00 | 369.19 | 4.92 |
| 69 | base | night_1 | TOP (custo) | 158/158 | 11/12 | 117/120 | 24/24 | 6.00 | 25.00 | 784.59 | 4.97 |
| 69 | base | night_1 | Clarke-Wright | 80/158 | 6/12 | 79/120 | 9/24 | 6.00 | 25.00 | 334.31 | 4.18 |

## Verificação global de ocupação

Esta tabela é complementar. O indicador `Pico / Capacidade de referência` acima continua associado à rota mais longa; aqui o pico simultâneo é procurado em todas as rotas e comparado com a capacidade física original do ônibus.

| Cenário | Heurística | Pico global / Capacidade física | Ônibus do pico | Rota do pico | Rotas acima da capacidade | Maior excedente | Ônibus/rota do maior excedente |
|---|---|---|---|---|---|---|---|
| 16 | TOP (custo) | 8/24 | 1 | 1 -> 16 -> 13 -> 6 -> 4 -> 15 -> 14 -> 7 | 0 | 0 | — |
| 16 | Clarke-Wright | 6/24 | 1 | 1 -> 17 -> 29 -> 27 -> 31 -> 30 -> 25 -> 24 -> 23 -> 22 -> 26 -> 20 -> 21 -> 12 -> 7 | 0 | 0 | — |
| 19 | TOP (custo) | 8/24 | 1 | 5 -> 2 -> 13 -> 8 -> 21 -> 11 -> 10 -> 1 -> 29 -> 17 -> 14 -> 16 -> 3 | 0 | 0 | — |
| 19 | Clarke-Wright | 11/24 | 2 | 5 -> 18 -> 1 -> 19 -> 21 -> 22 -> 24 -> 26 -> 27 -> 16 -> 14 -> 7 -> 3 | 0 | 0 | — |
| 32 | TOP (custo) | 7/24 | 1 | 27 -> 21 -> 8 -> 5 -> 7 -> 10 -> 17 -> 32 -> 23 -> 26 -> 31 | 0 | 0 | — |
| 32 | Clarke-Wright | 5/24 | 3 | 27 -> 28 -> 15 -> 14 -> 16 -> 17 -> 29 -> 30 -> 25 -> 31 | 0 | 0 | — |
| 65 | TOP (custo) | 24/24 | 2 | 44 -> 9 -> 24 -> 7 -> 38 -> 30 -> 40 -> 36 -> 8 -> 19 -> 45 | 0 | 0 | — |
| 65 | Clarke-Wright | 24/24 | 8 | 44 -> 9 -> 12 -> 8 -> 4 -> 7 -> 35 -> 45 | 0 | 0 | — |
| 69 | TOP (custo) | 24/24 | 1 | 45 -> 25 -> 21 -> 34 -> 30 -> 7 -> 18 -> 5 -> 44 | 0 | 0 | — |
| 69 | Clarke-Wright | 24/24 | 2 | 43 -> 7 -> 31 -> 30 -> 29 -> 21 -> 46 -> 44 | 0 | 0 | — |

