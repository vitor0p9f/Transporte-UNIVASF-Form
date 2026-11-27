# Resultados controlados — Tempo e Capacidade

Gerado em 2026-11-18 11:28.

As restrições de tempo e de capacidade estão ativas nas duas heurísticas. Os cenários são a cópia controlada (`scenarios_control.csv` + `scenarios_base_control.csv`) e a frota é a homogênea de `fleet_control.csv`: todos os ônibus são o modelo de menor capacidade do `fleet.csv` (24 lugares e 4.61 km/L). As origens e os destinos permitidos vêm das colunas `origin` e `destination_labels` do cenário, as mesmas para as duas heurísticas, e o Clarke-Wright é limitado ao número de ônibus da frota.

O **TOP (custo)** pontua passageiros por real: cada rota paga o combustível (km / km por litro do ônibus × diesel do cenário) e o motorista (horas × valor da hora do cenário). Maximizar passageiros por real é equivalente a minimizar o custo por passageiro; na inserção de uma parada, o score marginal minimiza o custo por passageiro extra. O **Clarke-Wright** usa esse mesmo custo: os savings do CW-1 e o desempate das seleções (λ, two-phase e pós-melhoria) são medidos em reais, com combustível + motorista. Como o CW não conhece a frota durante a construção, ele aplica um modelo de referência único (o ônibus da capacidade efetiva). O custo mostrado é recalculado por ônibus a partir das rotas finais, cobrando apenas as rotas que atendem alguém.

| Cenário | Instância | Período | Heurística | Passageiros atendidos / Total | Ônibus usados / Frota | Maior rota / Limite (min) | Pico / Capacidade de referência | Diesel (R$/L) | Motorista (R$/h) | Custo operacional (R$) | Custo por passageiro (R$) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 | p1_4_b | night_2 | TOP (custo) | 37/59 | 4/12 | 104/106 | 3/24 | 5.91 | 33.94 | 458.21 | 12.38 |
| 16 | p1_4_b | night_2 | Clarke-Wright | 21/59 | 3/12 | 87/106 | 6/24 | 5.91 | 33.94 | 260.22 | 12.39 |
| 19 | p1_4_r | afternoon_2 | TOP (custo) | 59/66 | 7/7 | 144/171 | 3/24 | 6.41 | 28.41 | 994.22 | 16.85 |
| 19 | p1_4_r | afternoon_2 | Clarke-Wright | 21/66 | 3/7 | 139/171 | 6/24 | 6.41 | 28.41 | 342.38 | 16.30 |
| 32 | p1_3_h | morning_2 | TOP (custo) | 48/54 | 6/12 | 146/146 | 4/24 | 5.65 | 31.42 | 791.76 | 16.50 |
| 32 | p1_3_h | morning_2 | Clarke-Wright | 21/54 | 3/12 | 104/146 | 6/24 | 5.65 | 31.42 | 234.50 | 11.17 |
| 65 | base | morning_1 | TOP (custo) | 196/198 | 8/12 | 118/120 | 22/24 | 6.00 | 25.00 | 820.03 | 4.18 |
| 65 | base | morning_1 | Clarke-Wright | 70/198 | 9/12 | 101/120 | 17/24 | 6.00 | 25.00 | 345.02 | 4.93 |
| 69 | base | night_1 | TOP (custo) | 158/158 | 11/12 | 117/120 | 24/24 | 6.00 | 25.00 | 784.59 | 4.97 |
| 69 | base | night_1 | Clarke-Wright | 79/158 | 6/12 | 78/120 | 18/24 | 6.00 | 25.00 | 324.55 | 4.11 |

