# Algoritmo Genético Distribuído para o Problema do Caixeiro Viajante

Este projeto implementa uma solução distribuída para o Problema do Caixeiro
Viajante (TSP) utilizando o Modelo de Ilhas com Algoritmo Genético. O sistema
é desenvolvido em Python com comunicação entre nós via gRPC, sincronização
lógica por Relógio de Lamport e eleição de coordenador pelo Algoritmo do
Valentão (Bully). O trabalho foi desenvolvido como projeto prático da
disciplina de Computação Distribuída, curso de Engenharia de Computação
da PUC Minas.

---

## Visão geral do sistema

O problema consiste em encontrar a rota de menor distância que visita
todas as cidades exatamente uma vez e retorna ao ponto de partida. Com
62 cidades, o espaço de busca é da ordem de (61)!/2, tornando qualquer
abordagem de força bruta inviável. O Algoritmo Genético explora esse
espaço de forma heurística, e a distribuição em múltiplos nós amplia
a diversidade de soluções exploradas simultaneamente.

O sistema organiza 5 nós em uma topologia estrela, onde um nó central
(coordenador) gerencia a troca de indivíduos entre as ilhas. Cada nó
mantém uma população local de 200 rotas e as evolui independentemente
por ciclos de gerações. Ao final de cada ciclo, cada nó envia seus
melhores indivíduos ao coordenador. Quando ao menos 80% dos nós enviaram
(threshold de 4 em 5), o coordenador seleciona os melhores do pool
global e redistribui para cada nó, excluindo os indivíduos que já
pertenciam ao destinatário. Este filtro de origem é o que preserva a
diversidade genética entre as ilhas.

O sistema encerra automaticamente quando todos os nós convergem, ou seja,
quando a melhora entre ciclos consecutivos é menor que o delta configurado
por um número mínimo de ciclos.

---

## Conceitos de sistemas distribuídos implementados

**Relógio Lógico de Lamport.** Cada nó mantém um contador lógico que
é incrementado a cada evento local e atualizado ao receber mensagens
pela regra max(local, recebido) + 1. O coordenador utiliza os timestamps
para descartar dados obsoletos: se um nó enviar dados de um ciclo
anterior após o coordenador já ter recebido dados mais recentes daquele
mesmo nó, a mensagem atrasada é ignorada, evitando que o pool regrida
em qualidade.

**Algoritmo do Valentão (Bully).** Cada nó mantém uma thread de heartbeat
que verifica periodicamente se o coordenador ainda está respondendo. Em
caso de falha, o nó inicia uma eleição enviando mensagens ELECTION para
todos os nós de ID maior. Se nenhum responder dentro do timeout, o nó
se proclama líder e anuncia a todos via mensagem COORDINATOR. O nó de
maior ID ativo sempre vence.

**Threshold assíncrono.** O coordenador não aguarda todos os nós enviarem
antes de redistribuir. Ao receber de 80% dos nós (4 em 5), aguarda uma
janela adicional de 2 segundos para dar chance ao último nó e então
redistribui com quem chegou a tempo. Isso garante que um único nó lento
ou com falha não bloqueie o restante do sistema.

**Exclusão mútua local.** O pool de indivíduos no coordenador é protegido
por um lock de threading, pois múltiplas requisições gRPC chegam
simultaneamente em threads paralelas. O padrão snapshot garante que
o lock seja liberado rapidamente: o pool é copiado e limpo dentro do
lock, e a redistribuição ocorre fora dele.

---

## Estrutura de arquivos

```
ag_distribuido/
├── proto/
│   └── genetico.proto          # Contrato gRPC: mensagens e métodos do serviço
├── genetico_pb2.py             # Classes das mensagens (gerado pelo protoc)
├── genetico_pb2_grpc.py        # Stub e Servicer do serviço (gerado pelo protoc)
├── config.py                   # Configurações centrais: nós, portas, parâmetros do AG e cidades
├── genetico_core.py            # Lógica pura do AG: fitness, crossover OX, mutação, seleção
├── relogio_lamport.py          # Relógio Lógico de Lamport
├── eleicao_bully.py            # Algoritmo do Valentão e heartbeat de monitoramento
├── coordenador_logica.py       # Gerenciamento do pool global e redistribuição
├── no_servidor.py              # Servidor gRPC e loop de evolução de cada nó
├── main.py                     # Ponto de entrada de um nó individual
├── run_all.py                  # Orquestrador: inicia todos os nós e exibe logs unificados
├── versao_local.py             # Versão single-machine para comparação no benchmark
├── benchmark.py                # Comparação de desempenho: local vs distribuído
├── dashboard.py                # API de monitoramento em tempo real (FastAPI)
├── cenarios_falha.py           # Estudo e testes de tolerância a falhas
└── requirements.txt
```

---

## Papel de cada arquivo

**config.py** é o ponto central de configuração importado por todos os
módulos. Define os endereços e portas dos nós, os parâmetros do algoritmo
genético (tamanho de população, taxa de mutação, número de migrantes,
critério de convergência) e as 62 cidades brasileiras com suas coordenadas
geográficas aproximadas.

**genetico_core.py** contém toda a lógica do algoritmo genético sem
nenhuma dependência de rede. Implementa a função de fitness (inverso da
distância total da rota), o operador de cruzamento Order Crossover (OX),
a mutação por troca de posição, a seleção por torneio e o elitismo.
Por estar isolado, pode ser importado tanto pelo nó distribuído quanto
pela versão local do benchmark.

**relogio_lamport.py** implementa as três operações do relógio lógico:
incremento por evento local, incremento antes de enviar (retornando o
timestamp para inclusão na mensagem) e atualização ao receber seguindo
a regra max(local, recebido) + 1. É thread-safe por lock interno.

**eleicao_bully.py** gerencia a eleição de líder. Mantém uma thread de
heartbeat que chama ObterStatus no coordenador a cada intervalo configurado.
Em caso de timeout, inicia o processo de eleição pelo Algoritmo do
Valentão, enviando mensagens ELECTION para nós de ID maior e proclamando-se
líder caso nenhum responda. Também processa os anúncios de novo líder
recebidos de outros nós.

**coordenador_logica.py** implementa a lógica exclusiva do nó coordenador.
Mantém o pool global de indivíduos indexado por nó de origem, verifica
o threshold de 80%, descarta dados obsoletos via Lamport, aguarda uma
janela de tempo após o threshold para incluir eventuais nós tardios e
redistribui os melhores indivíduos externos para cada nó.

**no_servidor.py** é a classe central do sistema. Cada processo instancia
um objeto desta classe, que acumula dois papéis: servidor gRPC (implementa
os 5 métodos do contrato: EnviarMelhores, ReceberMigrantes, ReceberEleicao,
ReceberLider e ObterStatus) e trabalhador (executa o loop de evolução
local, envia migrantes ao coordenador e aguarda o retorno a cada ciclo).
O nó M2 acumula ainda o papel de coordenador ao instanciar CoordenadarLogica.

**main.py** é o ponto de entrada de um nó individual. Recebe o ID do nó
por argumento, inicia o servidor gRPC, aguarda o coordenador estar disponível
antes de começar a evoluir e monitora o encerramento da evolução para
parar o servidor automaticamente.

**run_all.py** é o orquestrador recomendado para execução. Inicia todos
os 5 nós como subprocessos, exibe os logs de cada um com cores distintas
no terminal e apresenta uma tabela de status atualizada a cada 15 segundos
consultando os nós via gRPC. Ao detectar que todos os processos encerraram,
finaliza automaticamente.

**versao_local.py** implementa o mesmo algoritmo genético sem distribuição,
usando a população total de 1000 indivíduos em um único processo. Serve
como baseline para o benchmark comparativo.

**benchmark.py** executa as duas versões com a mesma semente aleatória,
garantindo comparação justa, e produz um relatório com métricas de qualidade
de solução, velocidade de convergência e speedup da versão distribuída.
Gera também um gráfico PNG com a evolução do fitness ao longo dos ciclos.

**dashboard.py** expõe uma API REST via FastAPI que consulta o status de
todos os nós em tempo real e serve uma interface HTML com atualização
automática a cada 3 segundos. Acesse em http://localhost:8080 enquanto
o sistema estiver rodando.

**cenarios_falha.py** documenta e testa os principais cenários de falha
do sistema: queda do coordenador com eleição automática, ausência de nó
trabalhador absorvida pelo threshold, descarte de dados obsoletos via
Lamport e redistribuição parcial com recuperação por timeout. Os testes
usam mocks e não exigem o sistema rodando.

**proto/genetico.proto** define o contrato do serviço gRPC com 5 métodos
e 8 tipos de mensagens. Os arquivos genetico_pb2.py e genetico_pb2_grpc.py
são gerados automaticamente a partir dele e nunca devem ser editados
manualmente.

---

## Instalação

```bash
pip install -r requirements.txt
```

Para regenerar os arquivos gRPC após alterar o .proto:

```bash
python -m grpc_tools.protoc \
    -I./proto \
    --python_out=. \
    --grpc_python_out=. \
    proto/genetico.proto
```

---

## Execução

A forma recomendada é pelo orquestrador, que cuida de iniciar os nós
na ordem correta e unifica os logs:

```bash
python run_all.py
```

Para iniciar os nós manualmente (5 terminais separados), sempre inicie
o coordenador primeiro:

```bash
python main.py 2   # coordenador — iniciar primeiro
python main.py 1
python main.py 3
python main.py 4
python main.py 5
```

Para executar o benchmark comparativo:

```bash
python benchmark.py
```

Para executar os testes de tolerância a falhas:

```bash
python cenarios_falha.py
```

Para monitorar o sistema em tempo real (enquanto run_all.py estiver rodando):

```bash
python dashboard.py
# acesse http://localhost:8080
```

---

## Execução em rede local (máquinas distintas)

Edite config.py substituindo localhost pelo IP de cada máquina:

```python
NOS = {
    1: "192.168.1.10:50051",
    2: "192.168.1.11:50052",
    3: "192.168.1.12:50053",
    4: "192.168.1.13:50054",
    5: "192.168.1.14:50055",
}
```

Copie o projeto para cada máquina, execute pip install -r requirements.txt
em cada uma e inicie com python main.py seguido do ID correspondente.
Neste caso, o run_all.py não pode ser usado pois ele inicia subprocessos
locais.

---

## Parâmetros principais

| Parâmetro             | Padrão    | Descrição                                          |
|-----------------------|-----------|----------------------------------------------------|
| TAMANHO_POPULACAO     | 200       | Indivíduos por nó (1000 no total)                  |
| NUM_MIGRANTES         | 20        | Melhores enviados ao coordenador por ciclo         |
| GERACOES_POR_CICLO    | 50        | Gerações de evolução local antes de migrar         |
| MAX_CICLOS            | 100       | Limite máximo de ciclos de migração                |
| THRESHOLD             | 0.80      | Fração mínima de nós para redistribuir (4 em 5)   |
| TAXA_MUTACAO          | 0.10      | Probabilidade de mutação por indivíduo             |
| CICLOS_SEM_MELHORA_MAX| 10        | Ciclos sem melhora para declarar convergência      |
| DELTA_CONVERGENCIA    | 0.000001  | Melhora mínima considerada significativa           |
| TIMEOUT_RPC           | 5         | Timeout em segundos para chamadas gRPC             |
| INTERVALO_HEARTBEAT   | 3         | Intervalo em segundos entre verificações do líder  |
| SEMENTE_INICIAL       | 42        | Semente para reproducibilidade entre execuções     |

---

## Fluxo de um ciclo de migração

```
1. Cada nó evolui sua população local por GERACOES_POR_CICLO gerações

2. Cada nó envia seus NUM_MIGRANTES melhores ao coordenador
   junto com o timestamp de Lamport e o identificador de origem

3. O coordenador acumula os envios no pool global.
   Ao receber de 80% dos nós, aguarda uma janela de 2 segundos
   e redistribui com todos que chegaram a tempo

4. Para cada nó destinatário, o coordenador seleciona os melhores
   indivíduos do pool que não vieram daquele nó (filtro de origem)
   e os envia via ReceberMigrantes

5. Cada nó substitui seus piores indivíduos pelos migrantes recebidos
   e inicia o próximo ciclo

6. O processo se repete até que todos os nós atinjam o critério
   de convergência ou o limite de MAX_CICLOS
```

---

## Tolerância a falhas

| Tipo de falha               | Solução implementada                              |
|-----------------------------|---------------------------------------------------|
| Coordenador offline         | Eleição automática pelo Algoritmo do Valentão     |
| Nó trabalhador offline      | Threshold de 80% absorve a ausência               |
| Dados chegam fora de ordem  | Descarte via timestamp de Lamport                 |
| Redistribuição incompleta   | Timeout de 10s + reinício do ciclo seguinte       |
| Rede lenta vs nó morto      | Timeout calibrado de 5s no heartbeat              |
