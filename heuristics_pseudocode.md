# Heurística TOP UNIVASF — pseudocódigo

> Documento em português; o código (identificadores e comentários) está em
> inglês. O código é a fonte da verdade: `algorithms/top_univasf/` — o laço das
> rodadas é `fleet.py: run_fleet`. O que estiver em `código` é nome do código, dá
> para buscar direto. O panorama com diagramas está em `heuristics.md`.

**Entradas:** matrizes de tempo e de demanda (a de distância é carregada mas não
usada), frota (`id` e lugares), limite de tempo por ônibus, filtros opcionais de
origem/destino e `max_rounds`.

## Ideia

Servir o máximo de passageiros respeitando lugares e limite de tempo por ônibus.
Em cada rodada **todo ônibus propõe um passo**; quem não conflita commita junto
e, num conflito, só o melhor score age. O que commita é descontado da demanda
global. Quem ainda não tem par travado escolhe a rota (um par OD) e, daí em
diante, só cresce a rota — um ponto por vez, guiado pela demanda.

## Pontuações

| momento | score |
|---|---|
| rota nova (`draft`) | passageiros embarcados ÷ tempo da rota |
| inserção (`expansão`) | passageiros ganhos ÷ tempo extra |
| plano final | passageiros ÷ tempo total |

- A rota nova é `[o, d]` ou `[o, P, d]`; o embarque respeita os lugares na ordem
  da rota (quem desce em `P` libera lugar). Sem passageiro ou sem tempo, score 0.
- Expansão: ganho ≤ 0 → score 0; com ganho > 0, tempo extra ≤ 0 → score infinito.

## Desempate — a ordem importa

Toda escolha compara uma tupla de campos e fica com a **maior**. Tupla se compara
da esquerda para a direita, então a primeira posição é o critério de verdade e
cada posição seguinte só decide empate exato das anteriores. `-campo` quer dizer
"menor é melhor". Ids de nó e `bus.id` estão ali só para o resultado sair sempre
igual (determinismo), não para escolher melhor.

| onde | tupla | em palavras |
|---|---|---|
| draft, por candidata | `(score, servidos, -tempo_rota, -o, -d, -margin)` | melhor score → mais passageiros → rota mais curta → menor `o` → menor `d` → no empate exato, a **rota direta** (`margin = -1`; uma rota com `P` entra com o id do nó) |
| expansão, por trial | `(score, passageiros, -tempo, -cand, trial)` | melhor score → mais passageiros → trial mais curto → menor nó inserido → a própria sequência |
| conflito, por proposta | `DraftProposal (score, servidos, -tempo, -bus.id)`<br>`ExpansionProposal (score, soma do claim, -tempo, -bus.id)` | melhor score → mais passageiros → rota mais curta → menor `bus.id` |

Numa disputa entre draft e expansão os `score` têm unidades diferentes
(eficiência da rota inteira × eficiência marginal do passo).

## A rodada

```text
remaining = demanda original            // vai sendo descontada
state_by_id[ônibus] = vazio             // ônibus sem par travado
rounds = 0 ; wins[ônibus] = 0

ENQUANTO soma(remaining) > 0:

  // 1. CADA ÔNIBUS PROPÕE UM PASSO (todos sobre o mesmo `remaining`)
  proposals = []
  PARA cada ônibus:
    SE ainda não tem par travado:
      PARA cada par (o, d) permitido:        // filtros de origem/destino
        SE o == d e remaining[o,d] > 0: pula   // self-loop não embarca
        SE tempo[o,d] < 0: pula
        P = demanda que sai de o + demanda que chega em d, menos {o, d}
        candidatas = [ [o, d] (direta) ] + [ [o, P, d] para cada P ]
        PARA cada candidata:
          SE algum trecho ou a rota tem tempo negativo, ou a rota passa do
            limite: pula
          embarcados = embarque na ordem da rota (quem desce libera lugar)
          SE a rota tem tempo 0 e embarcou alguém: pula
          score = embarcados / tempo da rota     // 0 passa, negativo não
          fica com a melhor tupla de desempate
      SE achou: propõe a rota escolhida      // o par trava aqui; sem deadhead
    SENÃO:
      SE a rota já está no limite de tempo: não propõe
      atual = simula a rota com a demanda já cobrada (`claimed`)
      PARA cada ponto fora da rota que aparece na demanda:
        REGRA A — demanda A→ponto, com A na rota:
          o ponto entra logo depois de A
          (se A é o destino final: [..., d, ponto, d])
        REGRA B — demanda ponto→Y, com Y na rota:
          o ponto entra logo antes de Y
          (se Y é o início e a rota não termina nele: [o, ponto, o, ...] — a
          dobradinha)
        simula o trial inteiro (lugares por perna, tempo e pico), e:
          SE passa do limite de tempo ou dos lugares: descarta
          score = passageiros ganhos / tempo extra    // precisa ser > 0
          claim = pares que ganharam passageiros       // precisa ser não vazio
          fica com a melhor tupla de desempate
      SE achou: propõe {pontos realmente inseridos + pares do claim}

  SE ninguém propôs nada: PARA

  // 2. CONFLITO
  agrupa as propostas que compartilham ponto ou par OD (direto ou por
  transitividade): grupo de 1 commita sozinho; grupo com mais de 1 deixa agir
  só o melhor da tupla de desempate

  // 3. COMMIT — cobra a demanda global
  PARA cada vencedor:
    SE rota nova: re-simula a rota base, cobra os pares embarcados e cria o
      estado (par travado, rota, claimed, tempo, pico)
    SE expansão: adota o trial e cobra os pares do claim
    rounds += 1 ; wins[ônibus] += 1
  SE ninguém commitou: PARA

O LAÇO TERMINA QUANDO: `remaining` zerou, ou passou `max_rounds`, ou ninguém
propôs, ou ninguém commitou.

SAÍDA — um plano por ônibus com passageiros > 0:
  (ônibus, rota, passageiros, tempo, pico, pax/min, pares servidos, par travado)
  e um resumo: rounds (= commits), vitórias por ônibus, pares e passageiros
  não servidos.
```

## Detalhes que costumam morder

- O draft aceita score 0. Se todos os pares viáveis derem 0, todo ônibus propõe o
  mesmo par mais próximo e, por rodada, só o menor `bus.id` commita — sem cobrar
  demanda.
- Draft e expansão disputam na mesma rodada, sob o mesmo `remaining`: nada é
  cobrado durante a proposta.
- Não existe deadhead: a rota nasce na origem do par (`[o,d]` ou `[o,P,d]`); a
  origem do cenário só filtra as origens que o draft pode usar.
- **Dobradinha:** quando a demanda é `ponto→o` (indo para o início) e a rota não
  termina no início, o ponto entra como `[o, ponto, o, ...]` — é o único formato
  que revisita a origem. Não vale quando `o == d`.
- A chave de conflito da expansão lista os nós realmente inseridos + os pares do
  claim (antes era o penúltimo nó da rota, o que gerava conflito à toa).
- `rounds` conta commits, não voltas do laço: dois commits na mesma volta = 2
  rounds.
- Só vira plano o ônibus que serviu alguém (estado com 0 passageiros é
  descartado).
- No empate exato do draft fica a rota direta, que também é mais barata de
  coordenar: entra nas chaves de conflito com menos pontos e menos pares.
