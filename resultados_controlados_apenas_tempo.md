# Resultados controlados — Apenas Restrição Temporal

Gerado em 2026-11-18 11:28.

Apenas o limite de tempo está ativo: a capacidade foi desativada nas decisões e na avaliação das duas heurísticas (frota com capacidade infinita). Os cenários são a cópia controlada (`scenarios_control.csv` + `scenarios_base_control.csv`) e a frota é a homogênea de `fleet_control.csv`: todos os ônibus são o modelo de menor capacidade do `fleet.csv` (24 lugares e 4.61 km/L). As origens e os destinos permitidos vêm das colunas `origin` e `destination_labels` do cenário, as mesmas para as duas heurísticas, e o Clarke-Wright é limitado ao número de ônibus da frota.

O **TOP (custo)** pontua passageiros por real: cada rota paga o combustível (km / km por litro do ônibus × diesel do cenário) e o motorista (horas × valor da hora do cenário). Maximizar passageiros por real é equivalente a minimizar o custo por passageiro; na inserção de uma parada, o score marginal minimiza o custo por passageiro extra. O **Clarke-Wright** usa esse mesmo custo: os savings do CW-1 e o desempate das seleções (λ, two-phase e pós-melhoria) são medidos em reais, com combustível + motorista. Como o CW não conhece a frota durante a construção, ele aplica um modelo de referência único (o ônibus da capacidade efetiva). O custo mostrado é recalculado por ônibus a partir das rotas finais, cobrando apenas as rotas que atendem alguém.

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
| 69 | base | night_1 | Clarke-Wright | 109/158 | 2/12 | 97/120 | 90/24 | 6.00 | 25.00 | 144.17 | 1.32 |

