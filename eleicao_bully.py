# ──────────────────────────────────────────────────────────────────────────────
# eleicao_bully.py — Algoritmo do Valentão (Bully) para eleição de líder
#
# Fluxo:
#  1. Nó detecta falha do coordenador (timeout no heartbeat)
#  2. Envia MensagemEleicao a todos os nós com ID maior
#  3. Se algum responder → ele assume a eleição
#  4. Se nenhum responder → este nó se proclama líder
#  5. Novo líder envia MensagemLider a todos os nós ativos
# ──────────────────────────────────────────────────────────────────────────────

import threading
import time
import logging
import grpc

import genetico_pb2
import genetico_pb2_grpc
from config import NOS, TIMEOUT_RPC, INTERVALO_HEARTBEAT

logger = logging.getLogger(__name__)


class GerenciadorEleicao:

    def __init__(self, meu_id: int, no_ref):
        """
        meu_id  : identificador numérico deste nó
        no_ref  : referência ao NoServidor (para acessar get_stub e ativar_coordenador)
        """
        self.meu_id          = meu_id
        self.no_ref          = no_ref
        self.lider_id        = None
        self.lider_endereco  = None
        self._em_eleicao     = False
        self._lock           = threading.Lock()

    # ── Estado do líder ───────────────────────────────────────────────────────

    def definir_lider(self, id_lider: int, endereco: str):
        with self._lock:
            self.lider_id = id_lider
            self.lider_endereco = endereco
        logger.info(f"[Nó {self.meu_id}] Líder definido: Nó {id_lider} ({endereco})")

    # ── Eleição ───────────────────────────────────────────────────────────────

    def iniciar_eleicao(self):
        """Inicia o processo de eleição pelo Algoritmo do Valentão."""
        with self._lock:
            if self._em_eleicao:
                return # eleição já em andamento
            self._em_eleicao = True

        logger.info(f"[Nó {self.meu_id}] Iniciando eleição...")

        # Envia ELECTION para todos os nós com ID maior
        nos_maiores = {nid: addr for nid, addr in NOS.items() if nid > self.meu_id}
        alguem_respondeu = False

        for nid, addr in nos_maiores.items():
            try:
                stub = self.no_ref.get_stub(addr)
                resp = stub.ReceberEleicao(
                    genetico_pb2.MensagemEleicao(id_origem=self.meu_id),
                    timeout=TIMEOUT_RPC
                )
                if resp.ok:
                    alguem_respondeu = True
                    logger.info(f"[Nó {self.meu_id}] Nó {nid} respondeu à eleição")
            except grpc.RpcError:
                logger.warning(f"[Nó {self.meu_id}] Nó {nid} não respondeu (pode estar inativo)")

        if not alguem_respondeu:
            # Sou o nó com maior ID ativo — assumo como coordenador
            self._proclamar_lider()

        with self._lock:
            self._em_eleicao = False

    def _proclamar_lider(self):
        """Anuncia a todos que este nó é o novo coordenador."""
        meu_endereco = NOS[self.meu_id]
        self.definir_lider(self.meu_id, meu_endereco)
        logger.info(f"[Nó {self.meu_id}] Sou o novo coordenador!")

        for nid, addr in NOS.items():
            if nid == self.meu_id:
                continue
            try:
                stub = self.no_ref.get_stub(addr)
                stub.ReceberLider(
                    genetico_pb2.MensagemLider(
                        id_lider=self.meu_id,
                        endereco=meu_endereco
                    ),
                    timeout=TIMEOUT_RPC
                )
            except grpc.RpcError:
                pass    # nó pode estar inativo

        # Ativa o modo coordenador neste nó
        self.no_ref.ativar_coordenador()

    # ── Monitoramento do líder ────────────────────────────────────────────────

    def monitorar_lider(self):
        """
        Thread contínua que verifica periodicamente se o líder responde.
        Dispara eleição em caso de timeout.
        """
        while True:
            time.sleep(INTERVALO_HEARTBEAT)

            # Não monitora se for o próprio líder ou se líder não definido
            if self.lider_id is None or self.lider_id == self.meu_id:
                continue

            try:
                stub = self.no_ref.get_stub(self.lider_endereco)
                stub.ObterStatus(
                    genetico_pb2.Vazio(),
                    timeout=TIMEOUT_RPC
                )
            except grpc.RpcError:
                logger.warning(
                    f"[Nó {self.meu_id}] Coordenador {self.lider_id} não respondeu! "
                    "Iniciando eleição..."
                )
                threading.Thread(
                    target=self.iniciar_eleicao, daemon=True
                ).start()
