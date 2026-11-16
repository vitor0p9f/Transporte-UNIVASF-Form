# Resultados controlados — Tempo e Capacidade

Relatório reprodutível · seed 42.

As restrições de tempo e de capacidade estão ativas nas duas heurísticas. Os cenários são a cópia controlada (`scenarios_control.csv` + `scenarios_base_control.csv`) e a frota é a homogênea de `fleet_control.csv`: todos os ônibus são o modelo de menor capacidade do `fleet.csv` (24 lugares e 4.61 km/L). O depósito é o primeiro nó da coluna `origin` do cenário, o mesmo para as duas heurísticas, e o Clarke-Wright é limitado ao número de ônibus da frota.

O **TOP (custo)** pontua passageiros por real: cada rota paga o combustível (km / km por litro do ônibus × diesel do cenário) e o motorista (horas × valor da hora do cenário). Maximizar passageiros por real é equivalente a minimizar o custo por passageiro; na inserção de uma parada, o score marginal minimiza o custo por passageiro extra. O custo mostrado é recalculado por ônibus a partir das rotas finais, cobrando apenas as rotas que atendem alguém. O CW é um baseline adaptado: as economias de distância constroem as rotas, e a seleção prioriza atendimento, com custo operacional como desempate. A carga estática da fusão soma a demanda OD que toca as paradas intermediárias, contando cada par uma vez; as âncoras não são clientes dessa projeção, mas entram na simulação de embarque. O pipeline é construção → anchoring → corte da frota → CW-3 → avaliação. A two-phase usa limite superior otimista, não atendimento exato. As duas heurísticas são avaliadas pela mesma simulação, mesmos limites, frota homogênea e fórmula de custo (diesel + motorista).

| Cenário | Instância | Período | Heurística | Passageiros atendidos / Total | Ônibus usados / Frota | Maior rota / Limite (min) | Pico / Capacidade de referência | Diesel (R$/L) | Motorista (R$/h) | Custo operacional (R$) | Custo por passageiro (R$) |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 16 | p1_4_b | night_2 | TOP (custo) | 37/59 | 4/12 | 104/106 | 3/24 | 5.91 | 33.94 | 458.21 | 12.38 |
| 16 | p1_4_b | night_2 | Clarke-Wright | 31/59 | 4/12 | 102/106 | 6/24 | 5.91 | 33.94 | 398.85 | 12.87 |
| 19 | p1_4_r | afternoon_2 | TOP (custo) | 59/66 | 7/7 | 144/171 | 3/24 | 6.41 | 28.41 | 994.22 | 16.85 |
| 19 | p1_4_r | afternoon_2 | Clarke-Wright | 30/66 | 4/7 | 126/171 | 3/24 | 6.41 | 28.41 | 422.80 | 14.09 |
| 32 | p1_3_h | morning_2 | TOP (custo) | 49/54 | 5/12 | 146/146 | 6/24 | 5.65 | 31.42 | 756.06 | 15.43 |
| 32 | p1_3_h | morning_2 | Clarke-Wright | 33/54 | 4/12 | 139/146 | 5/24 | 5.65 | 31.42 | 453.88 | 13.75 |
| 65 | base | morning_1 | TOP (custo) | 196/198 | 8/12 | 118/120 | 22/24 | 6.00 | 25.00 | 820.03 | 4.18 |
| 65 | base | morning_1 | Clarke-Wright | 56/198 | 10/12 | 65/120 | 13/24 | 6.00 | 25.00 | 381.67 | 6.82 |
| 69 | base | night_1 | TOP (custo) | 124/158 | 4/12 | 120/120 | 24/24 | 6.00 | 25.00 | 499.24 | 4.03 |
| 69 | base | night_1 | Clarke-Wright | 30/158 | 5/12 | 70/120 | 5/24 | 6.00 | 25.00 | 280.55 | 9.35 |

