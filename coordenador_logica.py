# ──────────────────────────────────────────────────────────────────────────────
# coordenador_logica.py — Lógica do Coordenador Central
# ──────────────────────────────────────────────────────────────────────────────

import threading
import logging
import grpc

import genetico_pb2
import genetico_pb2_grpc
from config import NOS, THRESHOLD, NUM_MIGRANTES
from relogio_lamport import RelogioLamport

logger = logging.getLogger(__name__)


class CoordenadarLogica:

    def __init__(self, meu_id: int):
        self.meu_id  = meu_id
        self.relogio = RelogioLamport()

        self._pool = {}
        self._pool_lock = threading.Lock()

        self._stubs = {}
        self._stubs_lock = threading.Lock()

        # M2 é trabalhador E coordenador — conta nos 5
        total_nos = len(NOS)
        self._min_nos = max(1, int(total_nos * THRESHOLD))  # 80% de 5 = 4

        logger.info(
            f"[Coordenador M{meu_id}] Aguarda {self._min_nos}/{total_nos} nós "
            f"(threshold {THRESHOLD*100:.0f}%) — M{meu_id} também envia como trabalhador"
        )

    # ── Recepção ──────────────────────────────────────────────────────────────

    def receber_migracao(self, request) -> bool:
        origem = request.origem
        ts = request.lamport_ts

        self.relogio.ao_receber(ts)

        snapshot = None   # será preenchido se threshold for atingido

        with self._pool_lock:
            # Descarta dados obsoletos via Lamport
            if origem in self._pool:
                ts_existente = self._pool[origem]["lamport_ts"]
                if ts <= ts_existente:
                    logger.info(
                        f"[Coordenador] {origem}: ts={ts} <= {ts_existente} "
                        "(obsoleto, descartando)"
                    ) #tratativas para evitar problema de enviar gerações anteriores, o que causaria atraso na população
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

            if nos_recebidos >= self._min_nos:
                # ── CRÍTICO: faz snapshot e limpa o pool DENTRO do lock ──────
                # Assim novos envios já começam a entrar no pool do próximo
                # ciclo enquanto a redistribuição acontece FORA do lock.
                snapshot = dict(self._pool)
                self._pool  = {}

        # ── Redistribui FORA do lock (não bloqueia novos envios) ─────────────
        if snapshot is not None:
            self._redistribuir(snapshot)
            return True

        return False

    # ── Redistribuição ────────────────────────────────────────────────────────

    def _redistribuir(self, pool_snapshot: dict):
        """
        Seleciona os melhores do snapshot e redistribui para cada nó.
        Executado fora do pool_lock para não bloquear novos envios.
        """
        logger.info(
            f"[Coordenador] Threshold atingido com {len(pool_snapshot)} nós. "
            "Redistribuindo..."
        )

        todos = []
        for origem, dados in pool_snapshot.items():
            for ind in dados["individuos"]:
                todos.append({**ind, "origem": origem})

        todos.sort(key=lambda x: x["aptidao"], reverse=True)

        ts_envio = self.relogio.antes_de_enviar()

        for nid, endereco in NOS.items():
            nome_no = f"M{nid}"
            '''
            if nome_no == f"M{self.meu_id}":
                continue
            '''

            migrantes = [
                ind for ind in todos if ind["origem"] != nome_no
            ][:NUM_MIGRANTES]

            if not migrantes:
                logger.warning(f"[Coordenador] Sem migrantes externos para {nome_no}")
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
