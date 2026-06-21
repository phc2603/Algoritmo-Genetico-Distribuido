# ──────────────────────────────────────────────────────────────────────────────
# main.py — Ponto de entrada de um único nó
#
# Uso recomendado: python run_all.py
# Uso individual:  python main.py <id_do_no>
# ──────────────────────────────────────────────────────────────────────────────

import sys
import time
import logging
import threading
import grpc
from concurrent import futures

import genetico_pb2
import genetico_pb2_grpc
from no_servidor import NoServidor
from config import NOS, ID_COORDENADOR_INICIAL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)


def aguardar_coordenador(meu_id: int, max_tentativas: int = 20):
    """Espera o coordenador responder antes de iniciar a evolução."""
    if meu_id == ID_COORDENADOR_INICIAL:
        return

    endereco = NOS[ID_COORDENADOR_INICIAL]
    canal    = grpc.insecure_channel(endereco)
    stub     = genetico_pb2_grpc.GeneticoServiceStub(canal)

    logger.info(
        f"[Nó {meu_id}] Aguardando coordenador M{ID_COORDENADOR_INICIAL} ({endereco})..."
    )

    for tentativa in range(1, max_tentativas + 1):
        try:
            stub.ObterStatus(genetico_pb2.Vazio(), timeout=2)
            logger.info(
                f"[Nó {meu_id}] Coordenador disponível "
                f"(tentativa {tentativa}) — iniciando evolução"
            )
            return
        except grpc.RpcError:
            logger.info(
                f"[Nó {meu_id}] Aguardando coordenador... "
                f"({tentativa}/{max_tentativas})"
            )
            time.sleep(1)

    logger.warning(
        f"[Nó {meu_id}] Coordenador não respondeu após {max_tentativas}s "
        "— iniciando sem sincronização"
    )


def iniciar_no(meu_id: int):
    if meu_id not in NOS:
        print(f"[ERRO] ID {meu_id} inválido. Disponíveis: {list(NOS.keys())}")
        sys.exit(1)

    no = NoServidor(meu_id)

    servidor = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    genetico_pb2_grpc.add_GeneticoServiceServicer_to_server(no, servidor)
    servidor.add_insecure_port(NOS[meu_id])
    servidor.start()
    logger.info(f"[Nó {meu_id}] Servidor gRPC ouvindo em {NOS[meu_id]}")

    no.servidor_ref = servidor

    aguardar_coordenador(meu_id)

    # Thread de heartbeat — daemon, morre junto com o processo
    threading.Thread(
        target=no.eleicao.monitorar_lider,
        daemon=True,
        name=f"heartbeat-{meu_id}",
    ).start()

    # Thread de evolução — NÃO daemon para poder usar join()
    t_evolucao = threading.Thread(
        target=no.rodar_evolucao,
        daemon=False,
        name=f"evolucao-{meu_id}",
    )
    t_evolucao.start()

    # Thread monitor: espera evolução terminar e encerra o servidor
    def _monitor():
        t_evolucao.join()#bloqueia até rodar_evolucao retornar
        logger.info(
            f"[Nó {meu_id}] Evolução concluída — "
            "encerrando servidor em 2s..."
        )
        time.sleep(2)       # janela para o dashboard capturar estado final
        servidor.stop(grace=2)

    threading.Thread(target=_monitor, daemon=True).start()

    try:
        servidor.wait_for_termination()  # desbloqueia quando servidor parar
        logger.info(f"[Nó {meu_id}] Processo encerrado.")
    except KeyboardInterrupt:
        logger.info(f"[Nó {meu_id}] Interrompido pelo usuário.")
        servidor.stop(grace=0)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("=" * 52)
        print("Algoritmo Genético Distribuído — TSP")
        print("=" * 52)
        print("\nUso recomendado (inicia tudo de uma vez):")
        print("  python run_all.py")
        print("\nUso individual:")
        print("  python main.py <id_do_no>")
        print("\nNós disponíveis:")
        for nid, addr in NOS.items():
            coord = "← coordenador inicial" if nid == ID_COORDENADOR_INICIAL else ""
            print(f"  {nid} → {addr}{coord}")
        sys.exit(0)

    iniciar_no(int(sys.argv[1]))