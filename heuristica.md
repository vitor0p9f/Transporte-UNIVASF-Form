# Heurística TOP UNIVASF — visão geral

O código é a fonte da verdade (`algorithms/top_UNIVASF.py`); o passo a passo
completo, em pseudocódigo, está em `heuristica_pseudocodigo.txt`.

## 1. Fluxo principal (a rodada)

```mermaid
flowchart TD
    A["carrega a instância e a frota"] --> B{"ainda há demanda?"}
    B -- "não" --> Z["planos finais<br/>(só ônibus com passageiros)"]
    B -- "sim" --> C["RODADA: cada ônibus propõe 1 passo"]
    C --> D{"o ônibus já tem<br/>par travado?"}
    D -- "não" --> E["RASCUNHO (draft)<br/>escolhe a rota-base [o, d] ou [o, P, d]<br/>pontuação = passageiros do trecho / tempo do trecho"]
    D -- "sim" --> F["EXPANSÃO<br/>insere 1 ponto guiado pela demanda<br/>pontuação = ganho de passageiros / tempo extra"]
    E --> G["CONFLITO: agrupa as propostas que<br/>compartilham um ponto ou um par origem-destino"]
    F --> G
    G --> H{"algum grupo<br/>tem mais de uma?"}
    H -- "não" --> I["todas se efetivam juntas"]
    H -- "sim" --> J["só a de maior pontuação age<br/>(desempate: ganho de passageiros,<br/>menor tempo, menor id de ônibus)"]
    I --> K["EFETIVA: abate da demanda global"]
    J --> K
    K --> B
```

## 2. Detalhe da expansão (onde o ponto novo entra)

```mermaid
flowchart TD
    P["candidato P fora da rota,<br/>com demanda ligada a algum ponto da rota"] --> R1{"chega A para P?<br/>(A já na rota)"}
    P --> R2{"sai P para Y?<br/>(Y já na rota)"}
    R1 -- "A é o destino final" --> T1["estende a rota: [..., d, P, d]"]
    R1 -- "caso geral" --> T2["P logo depois de A"]
    R2 -- "Y é a partida o<br/>e o diferente de d" --> T3["dobradinha (nova): [o, P, o, ...]"]
    R2 -- "caso geral" --> T4["P logo antes de Y"]
    T1 --> S["simula a rota inteira<br/>(capacidade trecho a trecho, tempo dentro do limite)"]
    T2 --> S
    T3 --> S
    T4 --> S
    S --> SC["pontuação = ganho de passageiros / tempo extra<br/>descarta se for menor ou igual a zero, ou sem par novo"]
    SC --> BE["fica a melhor proposta do ônibus na rodada"]
```

## Legenda

- **rascunho (draft)** — ônibus sem par travado escolhe a rota-base; a rota
  nasce na origem do par (sem deslocamento vazio).
- **expansão** — ônibus com par travado insere 1 ponto; a posição vem da
  demanda. A **dobradinha** `[o, P, o, ...]` é o caso em que a demanda é
  `P→o` (sair para a partida) e a rota não termina na partida — é a única
  posição que revisita a origem.
- **conflito** — propostas que compartilham chave (ponto ou par
  origem-destino) caem no mesmo grupo, direto ou por transitividade.
- **pontuações** — rascunho: `passageiros do trecho ÷ tempo do trecho`;
  expansão: `ganho de passageiros ÷ tempo extra`. O relatório final usa
  `passageiros totais ÷ tempo total`.
