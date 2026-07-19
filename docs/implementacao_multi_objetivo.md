# Algoritmo Clarke-Wright Multi-Objetivo (Multi-CW)

Este documento descreve detalhadamente a implementação, a modelagem matemática e a lógica algorítmica da versão **Multi-Objetivo** do heurístico de poupança (Savings) de Clarke-Wright, desenvolvida especificamente para o problema de roteamento de ônibus da UNIVASF.

A implementação encontra-se no arquivo [clarke_wright_multi.py](file:///home/vitor/Programming/Transporte-UNIVASF-Form/algorithms/clarke_wright_multi.py).

---

## 1. Visão Geral e Contexto (OVRP)

O problema é modelado como um **Problema de Roteamento de Veículos Aberto (Open Vehicle Routing Problem - OVRP)** com paradas intermediárias de embarque e desembarque (*Pick-up and Delivery*).
Diferente do VRP clássico, onde os veículos saem do depósito, atendem os clientes e obrigatoriamente retornam ao depósito:
- No nosso **OVRP**, os ônibus iniciam sua jornada no depósito (Campus Petrolina Centro), realizam os embarques e desembarques das viagens das arestas do turno e terminam sua rota na última parada de desembarque (sem necessidade de retornar vazios ao depósito).

---

## 2. Estrutura de Dados da Rota

A rota multi-objetivo é controlada pela classe `RotaMulti`:
- `paradas`: Lista ordenada das paradas visitadas (inicia com o depósito).
- `cargas_trecho`: Vetor que indica a carga exata a bordo em cada segmento da rota (entre uma parada e a próxima).
- `carga_maxima`: O pico máximo de lotação atingido em qualquer segmento da rota.
- `dist_km`: Distância total percorrida em quilômetros.
- `tempo_min`: Tempo total de viagem em minutos.
- `custo_brl`: Custo operacional estimado em reais (calculado com base no combustível).
- `viagens_atendidas`: Lista de viagens de passageiros cobertas por esta rota.

---

## 3. Função de Fitness / Custo Multi-Objetivo

Para avaliar a viabilidade e a qualidade de uma rota simulada, o algoritmo calcula o **Fitness** através da função `avaliar_fitness_rota`. O objetivo é minimizar o custo combinado da rota, que é composto por:

$$\text{Fitness} = \text{Custo de Combustível} + \text{Penalidade de Ocupação} + \text{Penalidade de Heterogeneidade} + \text{Penalidade de Tempo}$$

### 3.1. Custo de Combustível (R$)
Calculado de forma linear com base na eficiência do veículo:
- `custo_combustivel = modelo.custo_rota(dist_km)`

### 3.2. Penalidade de Lotação / Ocupação
A lotação ideal do ônibus situa-se entre 50% de sua capacidade ($C/2$) e sua capacidade máxima ($C$).
- **Caso 1: Ocupação Ideal ($C/2 \le \text{lotação} \le C$)**
  - O algoritmo aplica uma **recompensa** linear (reduzindo o custo de fitness) para encorajar ônibus cheios:
    $$\text{Recompensa} = -W_{\text{OCC\_REWARD}} \times \frac{\text{lotação} - C/2}{C - C/2}$$
- **Caso 2: Sub-ocupação ($\text{lotação} < C/2$)**
  - Aplica uma penalidade exponencial massiva para evitar que ônibus circulem vazios ou quase vazios (gastando combustível inutilmente):
    $$\text{Penalidade} = W_{\text{OCC\_PENALTY}} \times \left(e^{(C/2 - \text{lotação})} - 1.0\right)$$
- **Caso 3: Superlotação ($\text{lotação} > C$)**
  - Aplica uma penalidade exponencial massiva (de caráter impeditivo) para evitar superlotação ilegal:
    $$\text{Penalidade} = W_{\text{OCC\_PENALTY}} \times \left(e^{(\text{lotação} - C)} - 1.0\right)$$

### 3.3. Penalidade de Heterogeneidade de Destinos
Evita que uma única rota atenda passageiros que vão para muitos destinos diferentes (o que forçaria desvios enormes para quem está a bordo):
$$\text{Penalidade} = W_{\text{HETEROGENEITY}} \times (N_{\text{destinos}} - 1)^2$$

### 3.4. Penalidade de Tempo de Rota
A rota ideal deve durar no máximo $T_{\text{max}} = 90$ minutos (limite regulatório). Se a rota passar deste limite, é aplicada uma penalidade exponencial de tempo:
$$\text{Penalidade} = W_{\text{TIME\_PENALTY}} \times \left(e^{(\text{tempo} - T_{\text{max}})} - 1.0\right)$$

*Nota: Para evitar erros de overflow na exponenciação (`math.exp`), é usada a função auxiliar `safe_exp` que limita o expoente a 50.*

---

## 4. Lógica de Construção da Rota

A construção de cada rota ocorre de forma sequencial na função `construir_rota_multi_objetivo`:

1. **Seleção de Candidatos a Embarque:**
   - O algoritmo filtra todos os pontos de embarque cujos passageiros caibam nas vagas restantes atuais do ônibus (capacidade - lotação atual após desembarques naquela parada).
2. **Cálculo de Score com Poupança (Savings) e Restrições (Fitness):**
   - Para cada ponto de embarque candidato $j$, calcula-se o ganho espacial clássico de Clarke-Wright usando um coeficiente regulador $\lambda$ (lambda):
     $$\text{Savings} = d(\text{depósito}, j) - \lambda \times d(\text{nó\_atual}, j)$$
   - O score final do candidato é a diferença entre a poupança espacial e o custo multi-objetivo simulado:
     $$\text{Score} = \text{Savings} - \text{Fitness}_{\text{simulado}}$$
   
   > [!NOTE]
   > **Divisão de Papéis (Savings vs. Fitness):**
   > * **Savings (`savings_val`):** Diz respeito exclusivamente à parte espacial e geométrica. Ele calcula a atratividade geográfica de visitar a parada $j$ em seguida, com base no depósito e na distância de transição direta ($d(\text{nó\_atual}, j)$) ponderada pelo $\lambda$.
   > * **Fitness (`avaliar_fitness_rota`):** É onde entram todas as outras restrições e objetivos operacionais (limite estrito de tempo de 90 min, capacidade máxima do ônibus, lotação ideal/confortável, custo de combustível real e heterogeneidade de destinos).
   > * **Unificação:** Ao maximizar o `Score = Savings - Fitness`, o algoritmo pondera o benefício espacial contra as penalidades operacionais.
   
   - O candidato com melhor score é selecionado, adicionado à rota, e seus passageiros são embarcados.
3. **Fase de Desembarque Guloso (Nearest Neighbor):**
   - Se nenhum novo ponto de embarque couber ou for viável (devido ao tempo ou limite de vagas), e ainda houver passageiros a bordo, o ônibus viaja para a parada de desembarque pendente mais próxima no espaço para descarregar passageiros e liberar espaço.
4. **Resolução de Splits (Embarques Parciais e Controle de Paradas Ativas):**
   - Se o ônibus estiver completamente vazio, mas ainda houver passageiros aguardando no sistema que excedem a capacidade total do veículo, realiza-se um embarque parcial (*split*).
   - O ônibus é preenchido exatamente até a capacidade máxima $C$ e esses passageiros selecionados são removidos da lista de viagens pendentes.
   - **Critério de Extinção do Ponto:** O ponto de embarque $j$ **só é removido** da lista de paradas a serem atendidas (`remaining_boardings`) se todos os passageiros daquele ponto tiverem embarcado. Caso reste qualquer passageiro devido a limite de capacidade, o ponto permanece ativo na lista. Isso garante que rotas futuras passem pelo local para buscar as pessoas remanescentes, impedindo o abandono de usuários.

---

## 5. Pós-Processamento: Consolidação de Rotas Pequenas

Após gerar a lista inicial de rotas, o algoritmo executa a etapa `consolidar_rotas_pequenas`.
- Rotas que possuam um pico de carga muito baixo ($\le 8$ passageiros) são consideradas ineficientes.
- O algoritmo tenta voluntariamente extinguir essas rotas, distribuindo cada uma de suas viagens para as demais rotas ativas do sistema.
- Ao fazer a redistribuição, o algoritmo respeita estritamente o limite de capacidade e permite um estouro de tempo de no máximo 20% nas rotas receptoras. Se todas as viagens da rota pequena forem alocadas com sucesso, ela é eliminada da frota, economizando um motorista inteiro.

---

## 6. Varredura Paramétrica (Auto-Tuning de Lambda)

A função principal `clarke_wright_multi_ovrp` não depende de um $\lambda$ estático definido manualmente. Em vez disso, ela implementa um **Grid Search** automático varrendo valores de $\lambda$ de $0.1$ a $2.0$ (com incrementos de $0.1$), gerando 20 cenários diferentes de roteamento.

### 6.1. O Papel do Parâmetro Lambda ($\lambda$)
O coeficiente $\lambda$ regula a sensibilidade geográfica do algoritmo de Clarke-Wright durante a tomada de decisões:
- **$\lambda$ Baixo (ex: $0.1$ a $0.5$):** Prioriza a atração de nós distantes do depósito. A "poupança" espacial é calculada com foco em buscar passageiros nos limites externos da rede de transporte, gerando rotas mais longas e abrangentes.
- **$\lambda$ Alto (ex: $1.5$ a $2.0$):** Penaliza fortemente a distância de deslocamento entre paradas consecutivas ($d(\text{nó\_atual}, j)$). Isso induz a criação de rotas compactas, formadas por "saltos curtos", focando na consolidação local antes de seguir viagem.

### 6.2. Escolha Automática do Melhor Cenário
Para cada valor de $\lambda$ testado:
1. Constrói-se todo o conjunto de rotas de forma sequencial.
2. Aplica-se a consolidação de rotas com poucos passageiros.
3. Soma-se o custo operacional consolidado (combustível de todas as rotas).
4. O algoritmo compara os 20 planos de roteamento gerados e seleciona aquele com o **menor custo financeiro geral** (que, por definição da função de fitness, também será o plano que melhor respeita os limites de capacidade, conforto e tempo máximo de 90 minutos).
