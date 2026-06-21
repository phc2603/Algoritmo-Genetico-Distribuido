# ──────────────────────────────────────────────────────────────────────────────
# coordenador_logica.py — Lógica do Coordenador Central
# ──────────────────────────────────────────────────────────────────────────────

import threading
import logging
import time
import grpc

import genetico_pb2
import genetico_pb2_grpc
from config import NOS, THRESHOLD, NUM_MIGRANTES
from relogio_lamport import RelogioLamport

logger = logging.getLogger(__name__)

# Após atingir o threshold, aguarda este tempo para dar chance ao último nó
JANELA_ESPERA = 2.0   # segundos


class CoordenadarLogica:

    def __init__(self, meu_id: int):
        self.meu_id = meu_id
        self.relogio = RelogioLamport()

        self._pool = {}
        self._pool_lock = threading.Lock()

        self._stubs = {}
        self._stubs_lock = threading.Lock()

        # Threshold estático: 80% de 5 nós = 4
        total_nos = len(NOS)
        self._min_nos = max(1, int(total_nos * THRESHOLD))

        # Controla a janela de espera — evita disparar redistribuição duplicada
        self._aguardando_janela = False

        logger.info(
            f"[Coordenador M{meu_id}] Aguarda {self._min_nos}/{total_nos} nós "
            f"({THRESHOLD*100:.0f}%) + janela de {JANELA_ESPERA}s para o último nó"
        )

    # ── Recepção ──────────────────────────────────────────────────────────────

    def receber_migracao(self, request) -> bool:
        origem = request.origem
        ts     = request.lamport_ts

        self.relogio.ao_receber(ts)

        with self._pool_lock:
            # Descarta dados obsoletos via Lamport
            if origem in self._pool:
                ts_existente = self._pool[origem]["lamport_ts"]
                if ts <= ts_existente:
                    logger.info(
                        f"[Coordenador] {origem}: ts={ts} <= {ts_existente} "
                        "(obsoleto, descartando)"
                    )
                    return False

            self._pool[origem] = {
                "individuos": [
                    {
                        "genes": list(ind.genes),
                        "aptidao": ind.aptidao,
                        "geracao": ind.geracao,
                    }
                    for ind in request.individuos
                ],
                "lamport_ts": ts,
            }

            nos_recebidos = len(self._pool)
            logger.info(
                f"[Coordenador] Recebido de {origem} | ciclo {request.ciclo} | "
                f"{nos_recebidos}/{self._min_nos} necessários"
            )

            # Threshold atingido — dispara janela de espera em thread separada
            # _aguardando_janela evita disparar múltiplas janelas simultâneas
            if nos_recebidos >= self._min_nos and not self._aguardando_janela:
                self._aguardando_janela = True
                threading.Thread(
                    target=self._aguardar_e_redistribuir,
                    daemon=True,
                ).start()

        return False

    # ── Janela de espera ──────────────────────────────────────────────────────

    def _aguardar_e_redistribuir(self):
        """
        Chamado em thread separada quando o threshold é atingido.
        Aguarda JANELA_ESPERA segundos para dar chance ao último nó enviar,
        depois captura o pool e redistribui com quem chegou a tempo.
        """
        nos_no_threshold = len(self._pool)
        logger.info(
            f"[Coordenador] Threshold atingido com {nos_no_threshold} nós — "
            f"aguardando {JANELA_ESPERA}s para o último nó..."
        )

        time.sleep(JANELA_ESPERA)

        with self._pool_lock:
            nos_final = len(self._pool)
            if nos_final > nos_no_threshold:
                logger.info(
                    f"[Coordenador] {nos_final - nos_no_threshold} nó(s) adicional(is) "
                    f"chegaram na janela → redistribuindo com {nos_final} nós"
                )
            else:
                logger.info(
                    f"[Coordenador] Nenhum nó adicional na janela → "
                    f"redistribuindo com {nos_final} nós"
                )

            snapshot = dict(self._pool)
            self._pool = {}
            self._aguardando_janela = False

        self._redistribuir(snapshot)

    # ── Redistribuição ────────────────────────────────────────────────────────

    def _redistribuir(self, pool_snapshot: dict):
        logger.info(
            f"[Coordenador] Redistribuindo {len(pool_snapshot)} nós..."
        )

        todos = []
        for origem, dados in pool_snapshot.items():
            for ind in dados["individuos"]:
                todos.append({**ind, "origem": origem})

        todos.sort(key=lambda x: x["aptidao"], reverse=True)

        ts_envio = self.relogio.antes_de_enviar()

        for nid, endereco in NOS.items():
            nome_no = f"M{nid}"

            migrantes = [
                ind for ind in todos if ind["origem"] != nome_no
            ][:NUM_MIGRANTES]

            if not migrantes:
                logger.warning(
                    f"[Coordenador] Sem migrantes externos para {nome_no}"
                )
                continue

            try:
                stub = self._get_stub(endereco)
                stub.ReceberMigrantes(
                    genetico_pb2.MensagemRedistribuicao(
                        individuos=[
                            genetico_pb2.Individuo(
                                genes=m["genes"],
                                aptidao=m["aptidao"],
                                geracao=m["geracao"],
                            )
                            for m in migrantes
                        ],
                        lamport_ts=ts_envio,
                    ),
                    timeout=10,
                )
                logger.info(
                    f"[Coordenador] Enviou {len(migrantes)} migrantes para {nome_no} "
                    f"(melhor aptidão: {migrantes[0]['aptidao']:.4f})"
                )
            except grpc.RpcError as e:
                logger.error(
                    f"[Coordenador] Erro ao enviar para {nome_no}: {e.code()}"
                )

        logger.info("[Coordenador] Pool limpo. Aguardando próximo ciclo.")

    # ── Utilitários ───────────────────────────────────────────────────────────

    def _get_stub(self, endereco: str):
        with self._stubs_lock:
            if endereco not in self._stubs:
                canal = grpc.insecure_channel(endereco)
                self._stubs[endereco] = genetico_pb2_grpc.GeneticoServiceStub(canal)
            return self._stubs[endereco]