# Comparativo de Modelos: Clarke-Wright Clássico vs. Multi-Objetivo

Este documento apresenta uma análise comparativa aprofundada dos resultados obtidos pelos algoritmos de roteamento **Clarke-Wright Clássico (CVRP/OVRP)** e o proposto **Clarke-Wright Multi-Objetivo (Multi-CW)**, rodados para o turno `manha_1` na UNIVASF.

---

## 1. Tabela Comparativa de Métricas

A tabela abaixo consolida os resultados operacionais e de qualidade de serviço de ambos os modelos:

| Métrica | Clarke-Wright Clássico | Clarke-Wright Multi-Objetivo | Status da Otimização |
| :--- | :---: | :---: | :---: |
| **Veículos Utilizados** | 4 | **5** | +1 veículo no Multi-CW |
| **Distância Total (km)** | 166.40 km | 202.10 km | +35.7 km no Multi-CW (~21.4%) |
| **Tempo de Viagem (min)** | 362.0 min | 430.0 min | +68.0 min no Multi-CW (~18.7%) |
| **Custo Combustível (R$)** | R$ 404.12 | R$ 491.06 | +R$ 86.94 no Multi-CW |
| **Lotação Máxima (pass.)** | 68 | **43** | **Dentro do limite (Cap: 48)** |
| **Veículos Superlotados** | 2 | **0** | **100% de conformidade** |
| **Passageiros em Desconforto** | 57 | **10** | **Redução de 82.4% no desconforto** |
| **Veículos Estourados ($T_{\text{max}} = 90$ min)** | 2 | **0** | **100% de conformidade** |
| **Pontos Não Atendidos** | Nenhum | Nenhum | Ambos atendem a 100% das demandas |

---

## 2. Análise Detalhada dos Resultados

### 2.1. Eficiência de Custo vs. Qualidade e Legalidade
À primeira vista, o **Clarke-Wright Clássico** parece mais econômico: ele utiliza **4 ônibus** em vez de 5, percorre **35.7 km a menos** e economiza **R$ 86.94** de combustível.
No entanto, essa "economia" no papel gera uma operação completamente **inviável na prática**:

1. **Superlotação Extrema (Risco à Segurança e Multas):**
   - O Clarke-Wright Clássico registrou uma lotação máxima de **68 passageiros** em um ônibus com capacidade máxima para **48 pessoas**. 
   - Havia **2 veículos operando em superlotação**. Isso representa uma infração gravíssima de trânsito, risco severo à segurança física dos estudantes e alta probabilidade de apreensão do veículo em fiscalizações.
   - O **Multi-Objetivo** limitou estritamente a lotação máxima em **43 passageiros**, garantindo **zero veículos superlotados** e mantendo todos dentro da capacidade legal (48).
   
2. **Nível de Desconforto dos Usuários:**
   - O limite de assentos confortáveis (sem pessoas em pé no corredor por muito tempo) é de **36 passageiros**.
   - No modelo Clássico, **57 passageiros** viajaram em condições de desconforto extremo.
   - No modelo **Multi-Objetivo**, esse número caiu drasticamente para apenas **10 passageiros**, proporcionando uma viagem muito mais humana e confortável.

3. **Estouro do Tempo Máximo de Rota ($T_{\text{max}}$):**
   - O limite aceitável de duração de uma rota para estudantes e motoristas é de **90 minutos**.
   - No modelo Clássico, **2 rotas estouraram esse limite**, fazendo com que os usuários passassem mais de uma hora e meia dentro do veículo, gerando atrasos nas aulas e fadiga.
   - No modelo **Multi-Objetivo**, **nenhuma rota ultrapassou os 90 minutos**, respeitando a restrição de pontualidade.

---

## 3. Conclusão da Otimização

A comparação deixa clara a importância da modelagem **Multi-Objetivo**:
- O algoritmo **Clássico** visa apenas a economia de distância física, gerando rotas sobrecarregadas e inviáveis legalmente.
- O algoritmo **Multi-Objetivo** age como um balanceador realista: ao custo marginal de **1 ônibus extra** e um acréscimo de **21.4% na quilometragem**, ele entrega uma solução que **elimina multas por superlotação, garante a segurança dos passageiros e respeita o teto de 90 minutos de viagem**.

Trata-se de um excelente investimento operacional, onde o pequeno acréscimo no custo do diesel viabiliza a conformidade e a segurança de toda a rede de transporte universitário da UNIVASF.
