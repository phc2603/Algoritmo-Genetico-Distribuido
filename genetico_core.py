# ──────────────────────────────────────────────────────────────────────────────
# genetico_core.py — Lógica do Algoritmo Genético para o TSP
# ──────────────────────────────────────────────────────────────────────────────

import math
import random
from config import CIDADES, NOMES_CIDADES, TAXA_MUTACAO, TAMANHO_TORNEIO


# ── Função de avaliação ───────────────────────────────────────────────────────

def distancia(c1: str, c2: str) -> float:
    """Distância euclidiana entre duas cidades."""
    x1, y1 = CIDADES[c1]
    x2, y2 = CIDADES[c2]
    return math.sqrt((x2 - x1) ** 2 + (y2 - y1) ** 2)


def distancia_total(rota: list) -> float:
    """Distância total do ciclo (inclui retorno à cidade de origem)."""
    n = len(rota)
    return sum(distancia(rota[i], rota[(i + 1) % n]) for i in range(n))


def fitness(rota: list) -> float:
    """Aptidão do indivíduo: quanto menor a distância, maior o fitness."""
    return 1.0 / distancia_total(rota)


# ── Criação de população ──────────────────────────────────────────────────────

def criar_individuo() -> list:
    """Cria uma rota aleatória (permutação das cidades)."""
    ind = NOMES_CIDADES[:]
    random.shuffle(ind)
    return ind


def criar_populacao(tamanho: int) -> list:
    """Cria uma população inicial com indivíduos aleatórios."""
    return [criar_individuo() for _ in range(tamanho)]

#divide de forma inteligente a população inicial
def fatia_do_no(meu_id: int) -> list:
    """
    Gera as 1000 rotas globais deterministicamente (mesma semente em
    todos os nós) e retorna apenas a fatia correspondente a este nó.

    M1 → rotas   0-199
    M2 → rotas 200-399
    M3 → rotas 400-599
    M4 → rotas 600-799
    M5 → rotas 800-999
    """
    from config import NOS, TAMANHO_POPULACAO, SEMENTE_INICIAL

    total = TAMANHO_POPULACAO * len(NOS)  # 1000

    # Semente fixa garante que todos os nós geram as mesmas 1000 rotas
    random.seed(SEMENTE_INICIAL)
    populacao_global = [criar_individuo() for _ in range(total)]

    # Cada nó pega sua fatia baseado na posição do seu ID na lista ordenada
    ids_ordenados  = sorted(NOS.keys())          # [1, 2, 3, 4, 5]
    idx  = ids_ordenados.index(meu_id) # M1→0, M2→1, M3→2...
    tamanho_fatia  = total // len(NOS)           # 200
    inicio  = idx * tamanho_fatia
    fim = inicio + tamanho_fatia

    return populacao_global[inicio:fim]


# ── Operadores genéticos ──────────────────────────────────────────────────────

def selecionar(populacao: list) -> list:
    """
    Seleção por torneio:
    Escolhe TAMANHO_TORNEIO indivíduos aleatórios e retorna o mais apto.
    """
    candidatos = random.sample(populacao, min(TAMANHO_TORNEIO, len(populacao)))
    return max(candidatos, key=fitness)


def crossover_ox(pai1: list, pai2: list) -> list:
    """
    Order Crossover (OX):
    Preserva a ordem relativa das cidades do pai1 num segmento aleatório
    e preenche o restante com as cidades do pai2 na ordem em que aparecem.
    Garante que cada cidade aparece exatamente uma vez.
    """
    n = len(pai1)
    a, b = sorted(random.sample(range(n), 2))

    filho = [None] * n
    filho[a : b + 1] = pai1[a : b + 1]

    restantes = [g for g in pai2 if g not in filho]
    j = 0
    for i in range(n):
        if filho[i] is None:
            filho[i] = restantes[j]
            j += 1
    return filho


def mutar(individuo: list) -> list:
    """
    Swap mutation:
    Com probabilidade TAXA_MUTACAO, troca duas cidades aleatórias de posição.
    """
    ind = individuo[:]
    if random.random() < TAXA_MUTACAO:
        i, j = random.sample(range(len(ind)), 2)
        ind[i], ind[j] = ind[j], ind[i]
    return ind


# ── Uma geração ───────────────────────────────────────────────────────────────

def evoluir(populacao: list) -> list:
    """
    Executa uma geração:
    1. Preserva o melhor indivíduo (elitismo puro)
    2. Gera filhos por torneio + OX + mutação até completar o tamanho
    """
    melhor = max(populacao, key=fitness)
    nova = [melhor[:]]  # elitismo: melhor sempre sobrevive

    while len(nova) < len(populacao):
        pai1 = selecionar(populacao)
        pai2 = selecionar(populacao)
        filho = crossover_ox(pai1, pai2)
        filho = mutar(filho)
        nova.append(filho)

    return nova


# ── Utilitários ───────────────────────────────────────────────────────────────

def melhores(populacao: list, n: int) -> list:
    """Retorna os N melhores indivíduos da população."""
    return sorted(populacao, key=fitness, reverse=True)[:n]


def melhor_individuo(populacao: list) -> list:
    """Retorna o indivíduo mais apto da população."""
    return max(populacao, key=fitness)


def evoluir_n(populacao: list, n: int) -> list:
    """Evolui a população por N gerações consecutivas."""
    for _ in range(n):
        populacao = evoluir(populacao)
    return populacao


