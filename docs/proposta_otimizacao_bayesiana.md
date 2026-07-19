# Proposta: Otimização Bayesiana para Calibração de Hiperparâmetros

Este documento propõe e detalha a arquitetura para implementar **Otimização Bayesiana** no projeto de roteamento da UNIVASF. O objetivo é automatizar a descoberta dos melhores valores para o coeficiente espacial $\lambda$ (lambda) e para os pesos das penalidades da função de fitness, substituindo a varredura em grade (*Grid Search*) simples por uma sintonia inteligente e global.

---

## 1. Por que Otimização Bayesiana?

No cenário atual:
- O coeficiente $\lambda$ é tunado via *Grid Search* com 20 passos discretos ($0.1$ a $2.0$).
- Os pesos de penalidade ($W$) são estáticos e definidos manualmente.
- O espaço de busca combinatório para calibrar 5 parâmetros simultaneamente é infinito. Fazer uma varredura em grade combinatória (ex: testar 10 valores para cada um dos 5 parâmetros) exigiria $10^5 = 100.000$ execuções do algoritmo, o que inviabilizaria o tempo de resposta.

A **Otimização Bayesiana** resolve isso:
- Ela trata a execução do algoritmo Clarke-Wright como uma função de caixa-preta cara ($f(x)$).
- Constrói um **modelo probabilístico substituto** (geralmente baseado em *Processos Gaussianos* ou *Parzen Estimators*) para prever o custo de combinações não testadas.
- Usa uma **função de aquisição** (como *Expected Improvement - EI*) para escolher o próximo conjunto de parâmetros a testar, equilibrando exploração (testar áreas incertas) e explotação (refinar áreas promissoras).
- Encontra o ótimo global com apenas **50 a 100 iterações**.

---

## 2. Formulação Matemática do Espaço de Busca

Definimos o vetor de parâmetros $X$ e seus respectivos intervalos de busca contínuos e discretos:

| Parâmetro | Tipo | Intervalo Proposto | Função no Algoritmo |
| :--- | :---: | :---: | :--- |
| $\lambda$ | Real | $[0.1, 3.0]$ | Balanço entre distância do depósito vs. distância entre paradas consecutivas. |
| $W_{\text{OCC\_REWARD}}$ | Real | $[10.0, 500.0]$ | Recompensa para ônibus com boa taxa de ocupação (entre 50% e 100%). |
| $W_{\text{OCC\_PENALTY}}$ | Real | $[500.0, 5000.0]$ | Penalidade exponencial por superlotação ou ônibus vazios. |
| $W_{\text{HETEROGENEITY}}$ | Real | $[10.0, 300.0]$ | Penalidade por misturar destinos dispersos na mesma rota. |
| $W_{\text{TIME\_PENALTY}}$ | Real | $[100.0, 3000.0]$ | Penalidade exponencial por estourar o tempo limite de 90 minutos. |

---

## 3. Estrutura da Função Objetivo (Black-box $f(x)$)

A função objetivo que a Otimização Bayesiana tentará **minimizar** recebe os parâmetros de $X$, executa o algoritmo e avalia o plano de rotas resultante com base em critérios operacionais e logísticos reais.

```python
def objective(X):
    # 1. Desempacota os parâmetros sugeridos pelo otimizador
    lam, w_reward, w_penalty, w_hetero, w_time = X
    
    # 2. Injeta os pesos temporariamente no módulo da heurística
    inject_weights(w_reward, w_penalty, w_hetero, w_time)
    
    # 3. Executa o Clarke-Wright Multi-Objetivo para o turno desejado
    rotas, _ = clarke_wright_multi_ovrp(..., lam=lam)
    
    # 4. Avalia o custo de qualidade real da solução (sem as penalidades artificiais da busca local)
    custo_combustivel = sum(r.custo_brl for r in rotas)
    numero_veiculos = len(rotas)
    
    # Penalidades reais estritas (queremos ZERO violações no mundo real)
    veiculos_superlotados = sum(1 for r in rotas if r.carga_maxima > CAPACIDADE_MAXIMA)
    rotas_atrasadas = sum(1 for r in rotas if r.tempo_min > TEMPO_MAX_ESTRITO)
    
    # Custo de frota: Adicionar um ônibus na rua custa muito mais que combustível (ex: R$ 300 fixo por veículo)
    custo_veiculos_fixo = numero_veiculos * 300.0
    
    # Penalidades massivas para garantir que o otimizador fuja de soluções ilegais
    penalidade_inviabilidade = (veiculos_superlotados * 10000.0) + (rotas_atrasadas * 5000.0)
    
    # Custo total real a ser minimizado
    custo_total_real = custo_combustivel + custo_veiculos_fixo + penalidade_inviabilidade
    
    return custo_total_real
```

---

## 4. Exemplo Prático de Implementação com Optuna

O [Optuna](https://optuna.org/) é o framework mais prático e moderno em Python para implementar essa otimização. Veja um esboço de código de como seria a calibração automática:

```python
import optuna
from clarke_wright_multi import clarke_wright_multi_ovrp
import clarke_wright_multi  # Para alterar os pesos globais se necessário

def otimizar_parametros_turno(nos, matriz_dist, matriz_tempo, viagens, deposito, capacidade):
    
    def objective(trial):
        # Sugere valores para os hiperparâmetros dentro dos intervalos definidos
        lam = trial.suggest_float("lam", 0.1, 3.0)
        w_reward = trial.suggest_float("w_reward", 10.0, 500.0)
        w_penalty = trial.suggest_float("w_penalty", 500.0, 5000.0)
        w_hetero = trial.suggest_float("w_hetero", 10.0, 300.0)
        w_time = trial.suggest_float("w_time", 100.0, 3000.0)
        
        # Sobrescreve temporariamente os pesos globais no algoritmo
        clarke_wright_multi.W_OCC_REWARD = w_reward
        clarke_wright_multi.W_OCC_PENALTY = w_penalty
        clarke_wright_multi.W_HETEROGENEITY = w_hetero
        clarke_wright_multi.W_TIME_PENALTY = w_time
        
        # Executa a geração de rotas com o lambda sugerido
        rotas, _ = clarke_wright_multi_ovrp(
            nos=nos,
            matriz_dist=matriz_dist,
            matriz_tempo=matriz_tempo,
            viagens=viagens,
            deposito=deposito,
            capacidade=capacidade,
            lam=lam,
            verbose=False
        )
        
        if not rotas:
            return 999999.0  # Penalidade extrema se falhar em gerar rotas
            
        # Calcula as métricas reais do plano resultante
        combustivel = sum(r.custo_brl for r in rotas)
        frota = len(rotas)
        superlotados = sum(1 for r in rotas if r.carga_maxima > capacidade)
        atrasados = sum(1 for r in rotas if r.tempo_min > 90.0)
        
        # Função de Custo Real Combinado
        custo_real = combustivel + (frota * 350.0) + (superlotados * 15000.0) + (atrasados * 10000.0)
        return custo_real

    # Cria o estudo de minimização do Optuna
    study = optuna.create_study(direction="minimize")
    
    # Executa a otimização por 80 tentativas (geralmente leva menos de 1 minuto)
    study.optimize(objective, n_trials=80)
    
    print("\n=== MELHORES PARÂMETROS ENCONTRADOS ===")
    print(study.best_params)
    print(f"Melhor Custo Estimado: R${study.best_value:.2f}")
    
    return study.best_params
```

---

## 5. Benefícios Esperados

1. **Auto-Ajuste por Turno:** Cada turno possui demandas e trânsitos específicos. A otimização bayesiana permite calibrar um conjunto de pesos sob medida para cada período (ex: manha_1 terá pesos diferentes de noite_1).
2. **Robustez a Mudanças:** Se a frota da UNIVASF mudar (ex: ônibus menores com capacidade de 30 pass.), o calibrador bayesiano se adaptará sem necessidade de intervenção de código humana.
3. **Equilíbrio Ótimo:** Reduz a necessidade de discussões arbitrárias sobre qual o "peso ideal" de cada restrição, descobrindo o equilíbrio matematicamente provado entre economia financeira e qualidade de transporte.
