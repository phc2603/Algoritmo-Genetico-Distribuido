# Mapa de nós: {id_inteiro: "host:porta"}
# Em produção, substitua "localhost" pelos IPs reais das máquinas.
NOS = {
    1: "localhost:50051",   # M1
    2: "localhost:50052",   # M2 — coordenador inicial
    3: "localhost:50053",   # M3
    4: "localhost:50054",   # M4
    5: "localhost:50055",   # M5
}

# Nó que inicia como coordenador
ID_COORDENADOR_INICIAL = 2

# ── Parâmetros do Algoritmo Genético ──────────────────────────────────────────
TAMANHO_POPULACAO = 200   # indivíduos por nó
NUM_MIGRANTES = 20  # melhores enviados ao coordenador por ciclo
GERACOES_POR_CICLO = 100  # gerações de evolução local antes de migrar
MAX_CICLOS = 100   # máximo de ciclos de migração (Quantidade de reproduções e execuções do AG)
THRESHOLD = 0.80  # fração mínima de nós para o coord. processar (80%)
TAXA_MUTACAO = 0.10  # probabilidade de mutação por indivíduo
TAMANHO_TORNEIO = 3   # participantes por torneio na seleção
SEMENTE_INICIAL = 42 #garante reproducibilidade entre execuções

# Ciclos consecutivos sem melhora para considerar convergência
CICLOS_SEM_MELHORA_MAX = 5 #condição de parada caso não consiga mais convergir
DELTA_CONVERGENCIA = 0.000001 # melhora mínima considerada significativa

# ── Heartbeat / detecção de falha ─────────────────────────────────────────────
TIMEOUT_RPC = 5  # timeout (s) de chamadas gRPC de monitoramento
INTERVALO_HEARTBEAT = 3  #intervalo (s) entre verificações do líder

# ── Cidades do TSP (nome: (x, y)) ─────────────────────────────────────────────
CIDADES = {
    # Bloco A-Z
    "A": (0, 0), "B": (3, 4), "C": (6, 1), "D": (8, 5), "E": (5, 8),
    "F": (2, 7), "G": (9, 2), "H": (1, 5), "I": (7, 9), "J": (4, 3),
    "K": (10, 6), "L": (3, 10), "M": (6, 4), "N": (0, 8), "O": (8, 0),
    "P": (5, 6), "Q": (2, 2), "R": (9, 8), "S": (4, 0), "T": (7, 7),
    "U": (12, 14), "V": (15, 3), "W": (18, 9), "X": (11, 20), "Y": (22, 5),
    "Z": (14, 17),
    
    # Bloco AA-AZ
    "AA": (30, 45), "AB": (35, 12), "AC": (42, 68), "AD": (28, 85), "AE": (50, 50),
    "AF": (62, 15), "AG": (19, 92), "AH": (55, 30), "AI": (78, 42), "AJ": (40, 5),
    "AK": (88, 70), "AL": (65, 88), "AM": (23, 54), "AN": (70, 22), "AO": (82, 10),
    "AP": (15, 75), "AQ": (47, 95), "AR": (95, 40), "AS": (33, 33), "AT": (85, 85),
    "AU": (58, 63), "AV": (25, 28), "AW": (74, 55), "AX": (92, 18), "AY": (10, 40),
    "AZ": (60, 5),
    
    # Bloco BA-BH
    "BA": (5, 95), "BB": (98, 98), "BC": (45, 45), "BD": (12, 60), "BE": (80, 3),
    "BF": (67, 72), "BG": (38, 80), "BH": (90, 52)
}
NOMES_CIDADES = list(CIDADES.keys())
