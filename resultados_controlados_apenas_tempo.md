# Resultados controlados — Apenas Restrição Temporal

Gerado em 2026-11-12 21:37.

Apenas o limite de tempo está ativo: a capacidade foi desativada nas decisões e na avaliação das duas heurísticas (frota com capacidade infinita). Os cenários são a cópia controlada (`scenarios_control.csv` + `scenarios_base_control.csv`) e a frota é a homogênea de `fleet_control.csv`: todos os ônibus são o modelo de menor capacidade do `fleet.csv` (24 lugares e 4.61 km/L). O depósito é o primeiro nó da coluna `origin` do cenário, o mesmo para as duas heurísticas, e o Clarke-Wright é limitado ao número de ônibus da frota.

O **TOP (custo)** pontua passageiros por real: cada rota paga o combustível (km / km por litro do ônibus × diesel do cenário) e o motorista (horas × valor da hora do cenário). Maximizar passageiros por real é equivalente a minimizar o custo por passageiro; na inserção de uma parada, o score marginal minimiza o custo por passageiro extra. O custo mostrado é recalculado por ônibus a partir das rotas finais, cobrando apenas as rotas que atendem alguém.

| Cenário | Instância | Período | Heurística | Passageiros atendidos / Total | Ônibus usados / Frota | Maior rota / Limite (min) | Pico / Capacidade de referência | Diesel (R$/L) | Motorista (R$/h) | Custo operacional (R$) | Custo por passageiro (R$) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 | p1_4_b | night_2 | TOP (custo) | 37/59 | 4/12 | 104/106 | 3/24 | 5.91 | 33.94 | 458.21 | 12.38 |
| 16 | p1_4_b | night_2 | Clarke-Wright | 14/59 | 2/12 | 82/106 | 5/24 | 5.91 | 33.94 | 172.14 | 12.30 |
| 19 | p1_4_r | afternoon_2 | TOP (custo) | 59/66 | 7/7 | 144/171 | 3/24 | 6.41 | 28.41 | 994.22 | 16.85 |
| 19 | p1_4_r | afternoon_2 | Clarke-Wright | 26/66 | 1/7 | 153/171 | 15/24 | 6.41 | 28.41 | 170.61 | 6.56 |
| 32 | p1_3_h | morning_2 | TOP (custo) | 49/54 | 5/12 | 146/146 | 6/24 | 5.65 | 31.42 | 756.06 | 15.43 |
| 32 | p1_3_h | morning_2 | Clarke-Wright | 14/54 | 2/12 | 112/146 | 7/24 | 5.65 | 31.42 | 157.67 | 11.26 |
| 65 | base | morning_1 | TOP (custo) | 198/198 | 7/12 | 118/120 | 84/24 | 6.00 | 25.00 | 660.73 | 3.34 |
| 65 | base | morning_1 | Clarke-Wright | 9/198 | 1/12 | 104/120 | 6/24 | 6.00 | 25.00 | 104.96 | 11.66 |
| 69 | base | night_1 | TOP (custo) | 152/158 | 5/12 | 115/120 | 28/24 | 6.00 | 25.00 | 533.61 | 3.51 |
| 69 | base | night_1 | Clarke-Wright | 15/158 | 1/12 | 79/120 | 12/24 | 6.00 | 25.00 | 77.98 | 5.20 |

