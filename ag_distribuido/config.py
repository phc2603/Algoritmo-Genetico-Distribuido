# ──────────────────────────────────────────────────────────────────────────────
# config.py — Configurações centrais do sistema
# Altere os endereços dos nós conforme a sua rede local.
# ──────────────────────────────────────────────────────────────────────────────

# Mapa de nós: {id_inteiro: "host:porta"}
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
TAMANHO_POPULACAO  = 200   # indivíduos por nó
NUM_MIGRANTES = 30 # melhores enviados ao coordenador por ciclo
GERACOES_POR_CICLO = 50    # gerações de evolução local antes de migrar
MAX_CICLOS = 100   # máximo de ciclos de migração
THRESHOLD = 0.80  # fração mínima de nós para o coord. processar (80%)
TAXA_MUTACAO = 0.10  # probabilidade de mutação por indivíduo
TAMANHO_TORNEIO = 3     # participantes por torneio na seleção

# Ciclos consecutivos sem melhora para considerar convergência
CICLOS_SEM_MELHORA_MAX = 10
DELTA_CONVERGENCIA = 0.001   # melhora mínima considerada significativa

# ── Heartbeat / detecção de falha ─────────────────────────────────────────────
TIMEOUT_RPC = 5    # timeout (s) de chamadas gRPC de monitoramento
INTERVALO_HEARTBEAT = 3   # intervalo (s) entre verificações do líder

# ── Cidades do TSP (nome: (x, y)) ─────────────────────────────────────────────
CIDADES = {
    "A": (0,  0),  "B": (3,  4),  "C": (6,  1),  "D": (8,  5),
    "E": (5,  8),  "F": (2,  7),  "G": (9,  2),  "H": (1,  5),
    "I": (7,  9),  "J": (4,  3),  "K": (10, 6),  "L": (3, 10),
    "M": (6,  4),  "N": (0,  8),  "O": (8,  0),  "P": (5,  6),
    "Q": (2,  2),  "R": (9,  8),  "S": (4,  0),  "T": (7,  7),
}
NOMES_CIDADES = list(CIDADES.keys())
