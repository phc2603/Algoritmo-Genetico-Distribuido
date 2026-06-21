"""
eleicao.py — Algoritmo do Valentão (Bully).

Quando o coordenador falha, os nós elegem um novo:
o nó com maior ID entre os ativos assume a liderança.
"""

import threading
import time
import logging

logger = logging.getLogger(__name__)

TIMEOUT_RESPOSTA = 3.0   # segundos para aguardar resposta de eleição
INTERVALO_MONITOR = 5.0  # segundos entre verificações de saúde do líder


class EleicaoBully:

    def __init__(self, meu_id: int, todos_nos: dict, relogio):
        """
        :param meu_id:    ID numérico deste nó (int)
        :param todos_nos: dict {id_int: stub_grpc} dos outros nós
        :param relogio:   instância de RelogioLamport
        """
        self.meu_id         = meu_id
        self.todos_nos      = todos_nos  # {int: stub}
        self.relogio        = relogio
        self.lider_id       = None
        self.lider_endereco = None
        self._em_eleicao    = False
        self._lock          = threading.Lock()

    # ── API pública ───────────────────────────────────────────────────────

    def iniciar_eleicao(self):
        """
        Inicia o processo de eleição.
        Envia ELECTION para todos os nós de ID maior.
        Se nenhum responder, este nó se proclama líder.
        """
        with self._lock:
            if self._em_eleicao:
                return
            self._em_eleicao = True

        logger.info(f"[Nó {self.meu_id}] Iniciando eleição...")

        nos_maiores = {nid: stub for nid, stub in self.todos_nos.items()
                       if nid > self.meu_id}

        alguem_respondeu = False

        for nid, stub in nos_maiores.items():
            try:
                import genetico_pb2
                resp = stub.ReceberEleicao(
                    genetico_pb2.MensagemEleicao(id_origem=self.meu_id),
                    timeout=TIMEOUT_RESPOSTA
                )
                if resp.ok:
                    alguem_respondeu = True
                    logger.info(f"[Nó {self.meu_id}] Nó {nid} respondeu — ele assume")
                    break
            except Exception:
                logger.warning(f"[Nó {self.meu_id}] Nó {nid} não respondeu")

        if not alguem_respondeu:
            self._proclamar_lider()

        with self._lock:
            self._em_eleicao = False

    def ao_receber_eleicao(self, id_origem: int):
        """Chamado quando recebe MensagemEleicao de outro nó."""
        logger.info(f"[Nó {self.meu_id}] Recebeu ELECTION do nó {id_origem}")
        # Inicia própria eleição em thread separada (não bloqueia o gRPC)
        threading.Thread(target=self.iniciar_eleicao, daemon=True).start()

    def ao_receber_lider(self, id_lider: int, endereco_lider: str):
        """Chamado quando recebe MensagemLider com o novo coordenador."""
        self.lider_id       = id_lider
        self.lider_endereco = endereco_lider
        logger.info(
            f"[Nó {self.meu_id}] Novo líder: Nó {id_lider} ({endereco_lider})"
        )

    def monitorar_lider(self, intervalo: float = INTERVALO_MONITOR):
        """
        Thread contínua que verifica se o líder está vivo.
        Se não responder, inicia eleição.
        """
        while True:
            time.sleep(intervalo)

            if self.lider_id is None or self.lider_id == self.meu_id:
                continue  # sou o líder ou ainda não foi eleito nenhum

            stub = self.todos_nos.get(self.lider_id)
            if not stub:
                continue

            try:
                import genetico_pb2
                stub.ObterStatus(genetico_pb2.Vazio(), timeout=2.0)
            except Exception:
                logger.warning(
                    f"[Nó {self.meu_id}] Líder {self.lider_id} não respondeu. "
                    "Iniciando eleição..."
                )
                self.iniciar_eleicao()

    # ── Helpers privados ──────────────────────────────────────────────────

    def _proclamar_lider(self):
        """Este nó se proclama líder e notifica todos."""
        self.lider_id = self.meu_id
        logger.info(f"[Nó {self.meu_id}] SEREI O NOVO LIDER!")

        meu_endereco = f"localhost:{50050 + self.meu_id}"

        import genetico_pb2
        for nid, stub in self.todos_nos.items():
            if nid == self.meu_id:
                continue
            try:
                stub.ReceberLider(
                    genetico_pb2.MensagemLider(
                        id_lider=self.meu_id,
                        endereco_lider=meu_endereco,
                    ),
                    timeout=TIMEOUT_RESPOSTA
                )
            except Exception:
                pass
