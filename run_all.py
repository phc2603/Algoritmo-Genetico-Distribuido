#!/usr/bin/env python3
# ──────────────────────────────────────────────────────────────────────────────
# run_all.py — Orquestrador: inicia todos os nós, exibe logs unificados
#              e mostra tabela de status periódica via gRPC.
#
# Uso:
#   python run_all.py
#   Ctrl+C para encerrar tudo.
# ──────────────────────────────────────────────────────────────────────────────

import subprocess
import threading
import sys
import time
import signal
import grpc

import genetico_pb2
import genetico_pb2_grpc
from config import NOS, ID_COORDENADOR_INICIAL, TIMEOUT_RPC

# ── Cores ANSI por nó ─────────────────────────────────────────────────────────
COR = {
    1: '\033[94m',   # azul
    2: '\033[92m',   # verde  ← coordenador
    3: '\033[93m',   # amarelo
    4: '\033[95m',   # magenta
    5: '\033[96m',   # ciano
}
RESET  = '\033[0m'
BOLD   = '\033[1m'
RED    = '\033[91m'
GRAY   = '\033[90m'
GREEN  = '\033[92m'

# ── Estado global ─────────────────────────────────────────────────────────────
processos   = {}        # {nid: subprocess.Popen}
_print_lock = threading.Lock()


def p(texto):
    """Print thread-safe."""
    with _print_lock:
        print(texto, flush=True)


def prefixo(nid):
    coord = " ★" if nid == ID_COORDENADOR_INICIAL else "  "
    return f"{COR.get(nid, '')}[M{nid}{coord}]{RESET}"


# ── Leitura de saída dos subprocessos ─────────────────────────────────────────
def ler_saida(nid, pipe):
    """Thread contínua que lê stdout do nó e imprime com prefixo colorido."""
    for linha in pipe:
        linha = linha.rstrip()
        if linha:
            p(f"{prefixo(nid)} {linha}")


# ── Inicialização dos nós ──────────────────────────────────────────────────────
def iniciar_no(nid):
    proc = subprocess.Popen(
        [sys.executable, "main.py", str(nid)],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    processos[nid] = proc
    threading.Thread(
        target=ler_saida, args=(nid, proc.stdout), daemon=True
    ).start()
    return proc


# ── Tabela de status via gRPC ─────────────────────────────────────────────────

def consultar_no(nid):
    """Consulta ObterStatus de um nó. Retorna None se offline."""
    try:
        canal = grpc.insecure_channel(NOS[nid])
        stub  = genetico_pb2_grpc.GeneticoServiceStub(canal)
        return stub.ObterStatus(genetico_pb2.Vazio(), timeout=TIMEOUT_RPC)
    except grpc.RpcError:
        return None


def exibir_status():
    """Consulta todos os nós e imprime tabela formatada."""
    statuses = {nid: consultar_no(nid) for nid in sorted(NOS)}

    sep = "+---------+---------+----------+--------------+------------+"
    cab = "| {:^7} | {:^7} | {:^8} | {:^12} | {:<10} |".format(
        "No", "Ciclo", "Geracao", "Melhor dist.", "Status"
    )

    linhas = [
        "",
        f"{BOLD}{'─'*58}{RESET}",
        f"{BOLD}  Status do sistema — {time.strftime('%H:%M:%S')}{RESET}",
        f"{BOLD}{'─'*58}{RESET}",
        sep, cab, sep,
    ]

    melhor_global = None

    for nid in sorted(NOS):
        s = statuses[nid]
        cor = COR.get(nid, '')
        tag = " (coord)" if nid == ID_COORDENADOR_INICIAL else ""
        nome = f"M{nid}{tag}"

        if s:
            dist = round(1 / max(s.melhor_aptidao, 1e-9), 4)
            linha = "| {}{:<7}{} | {:>7} | {:>8} | {:>12.4f} | {}online{:<4}{} |".format(
                cor, nome, RESET,
                s.ciclo_atual,
                s.geracao_atual,
                dist,
                GREEN, "", RESET,
            )
            if melhor_global is None or s.melhor_aptidao > melhor_global[1]:
                melhor_global = (nid, s.melhor_aptidao, dist, s.melhor_rota)
        else:
            linha = "| {}{:<7}{} | {:>7} | {:>8} | {:>12} | {}offline{:<3}{} |".format(
                RED, nome, RESET,
                "—", "—", "—",
                RED, "", RESET,
            )

        linhas.append(linha)

    linhas.append(sep)

    if melhor_global:
        nid, _, dist, rota = melhor_global
        rota_c = (rota[:40] + "...") if len(rota) > 40 else rota
        linhas.append(
            f"  {BOLD}Melhor global:{RESET} "
            f"{COR.get(nid,'')}M{nid}{RESET} — distância {dist:.4f}"
        )
        linhas.append(f"  {GRAY}Rota: {rota_c}{RESET}")

    linhas.append(f"{BOLD}{'─'*58}{RESET}\n")

    with _print_lock:
        print('\n'.join(linhas), flush=True)


def loop_status(intervalo=15):
    """Thread que exibe a tabela de status periodicamente."""
    time.sleep(intervalo)   # aguarda sistema estabilizar
    while True:
        exibir_status()
        time.sleep(intervalo)


# ── Monitoramento de processos ────────────────────────────────────────────────

def monitorar_processos():
    reportados = set()
    while True:
        time.sleep(3)
        ativos = []
        for nid, proc in list(processos.items()):
            ret = proc.poll()
            if ret is None:
                ativos.append(nid)
            elif nid not in reportados:
                reportados.add(nid)
                cor = GREEN if ret == 0 else RED
                msg = "concluiu com sucesso" if ret == 0 else f"encerrou com erro (código {ret})"
                p(f"{cor}[Sistema] Nó M{nid} {msg}{RESET}")

        if not ativos and len(reportados) == len(processos):
            p(f"\n{BOLD}[Sistema] Todos os nós concluíram. Encerrando...{RESET}")
            sys.exit(0)

# ── Encerramento ──────────────────────────────────────────────────────────────

def encerrar(sig=None, frame=None):
    p(f"\n{RED}{BOLD}[Sistema] Encerrando todos os nós...{RESET}")
    for nid, proc in list(processos.items()):
        proc.terminate()
        p(f"{GRAY}[Sistema] Nó M{nid} encerrado{RESET}")
    sys.exit(0)




# ── Ponto de entrada ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    signal.signal(signal.SIGINT,  encerrar)
    signal.signal(signal.SIGTERM, encerrar)

    print(f"\n{BOLD}{'═'*58}{RESET}")
    print(f"{BOLD}  Algoritmo Genético Distribuído — TSP{RESET}")
    print(f"{BOLD}  {len(NOS)} nós  ·  população {len(NOS)*200}  ·  threshold 80%{RESET}")
    print(f"{BOLD}{'═'*58}{RESET}\n")

    # 1. Inicia o coordenador primeiro
    p(f"[Sistema] Iniciando coordenador {prefixo(ID_COORDENADOR_INICIAL)} ...")
    iniciar_no(ID_COORDENADOR_INICIAL)
    time.sleep(1.5)     # pequena espera para o coordenador subir

    # 2. Inicia os nós trabalhadores
    for nid in sorted(NOS):
        if nid == ID_COORDENADOR_INICIAL:
            continue
        p(f"[Sistema] Iniciando {prefixo(nid)} ...")
        iniciar_no(nid)
        time.sleep(0.4)

    p(f"\n{BOLD}[Sistema] Todos os nós iniciados. "
      f"Status a cada 15s. Ctrl+C para encerrar.{RESET}\n")

    # 3. Thread de status periódico
    threading.Thread(target=loop_status, args=(15,), daemon=True).start()

    # 4. Thread de vigilância de processos
    threading.Thread(target=monitorar_processos, daemon=True).start()

    # 5. Loop principal — aguarda Ctrl+C
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        encerrar()


