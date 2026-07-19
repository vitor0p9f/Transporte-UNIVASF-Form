Com base no código atual, na implementação atual, você vai fazer uma cópia implementando um novo modelo de savings multi-objetivo para o CW.

A função de savings agora deve levar em consideração os seguintes aspectos:

- Ocupação: O algoritmo vai olhar qual a capacidade máxima do modelo de ônibus, entre esse valor e metade dele, o savings tem que ser liner e positivo. Fora desse intervalo deve haver uma penalização exponencial e massiva.
- Heterogeneidade: As rotas devem ser construidas com base na similaridade dos destinos, quanto mais destinos diferentes numa mesma rota, maior a penalidade.
- Horário de funcionamento: O algoritmo deve levar em consideração o tempo máximo estipulado para a realização da rota, ao passar desse tempo, o saving é exponencialmente penalizado


Depois que o CW gerar os pontos da rota, vãoser inseridos os pontos de desembarque que fazem parte daquela rota. Para isso, o algoritmo vai usar uma estratégia gulosa, exemplo, vou tentar organizar todos os pontos que tem embarque em A e depois fazer o desembarque lá, pra liberar mais espaço e voltar a aplicar o CW para gerar mais pontos de embarque. A inserção dos desembarques é de forma gulosa, e um ponto de embarque nunca pode vir antes de um ponto que há desembarque nesse ponto.

Faça uma comparação entre as duas modalidades, plote as rotas, quantos passageiros a rota atente no total e me permita passar o mouse em cima de cada trecho da rota para ver quantos foram atendiso naquele trecho (CW modificado)