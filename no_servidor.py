# ──────────────────────────────────────────────────────────────────────────────
# no_servidor.py — Servidor gRPC de cada nó
# ──────────────────────────────────────────────────────────────────────────────

import grpc
import threading
import logging
import time

import genetico_pb2
import genetico_pb2_grpc
import genetico_core as ga
from config import (
    NOS, ID_COORDENADOR_INICIAL,
    TAMANHO_POPULACAO, NUM_MIGRANTES, GERACOES_POR_CICLO,
    MAX_CICLOS, CICLOS_SEM_MELHORA_MAX, DELTA_CONVERGENCIA,
)
from relogio_lamport import RelogioLamport
from eleicao_bully import GerenciadorEleicao
from coordenador_logica import CoordenadarLogica

logger = logging.getLogger(__name__)

# Timeout de espera por migrantes — reduzido para não bloquear muito
TIMEOUT_MIGRANTES = 10   # segundos


class NoServidor(genetico_pb2_grpc.GeneticoServiceServicer):

    def __init__(self, meu_id: int):
        self.t_inicio = time.time()
        self.meu_id = meu_id
        self.meu_nome = f"M{meu_id}"
        self.meu_endereco = NOS[meu_id]

        self.populacao = ga.fatia_do_no(meu_id) 
        self.geracao_atual = 0
        self.ciclo_atual = 0
        self._pop_lock = threading.Lock() #protege de ser lida e escrita ao mesmo tempo

        self.relogio = RelogioLamport() 

        '''
        Define o líder, caso seja instanciado M2, mas cada nó aponta para o coordenador inicial (M2)
        '''
        self.eleicao = GerenciadorEleicao(meu_id, self)
        self.eleicao.definir_lider(
            ID_COORDENADOR_INICIAL,
            NOS[ID_COORDENADOR_INICIAL]
        )

        self.coordenador = None
        if meu_id == ID_COORDENADOR_INICIAL:
            self.ativar_coordenador()

        self._stubs = {}
        self._stubs_lock = threading.Lock()

        self._evento_migrantes = threading.Event() #suspende a thread até que toda a população seja enviada ao coordenador

        # Referência ao servidor gRPC — preenchida por main.py após start()
        # Permite que rodar_evolucao() encerre o servidor quando convergir
        self.servidor_ref = None

        logger.info(
            f"[Nó {meu_id}] Inicializado | "
            f"população: {TAMANHO_POPULACAO} | "
            f"coordenador inicial: M{ID_COORDENADOR_INICIAL}"
        )

    # ── Coordenador ───────────────────────────────────────────────────────────

    def ativar_coordenador(self):
        if self.coordenador is None:
            logger.info(f"[Nó {self.meu_id}] Ativando modo coordenador")
            self.coordenador = CoordenadarLogica(self.meu_id)

    # ── Stubs gRPC ────────────────────────────────────────────────────────────
    #retorna a conexão já existente para um certo endereço, ou cria uma nova, caso seja a primeira vez
    def get_stub(self, endereco: str):
        with self._stubs_lock:
            if endereco not in self._stubs:
                canal = grpc.insecure_channel(endereco)
                self._stubs[endereco] = genetico_pb2_grpc.GeneticoServiceStub(canal)
            return self._stubs[endereco]

    # ── Métodos gRPC ──────────────────────────────────────────────────────────

    def EnviarMelhores(self, request, context):
        if self.coordenador is None:
            return genetico_pb2.Confirmacao(
                ok=False, mensagem="Não sou o coordenador"
            )
        self.coordenador.receber_migracao(request)
        return genetico_pb2.Confirmacao(ok=True, mensagem="Migração recebida")

    def ReceberMigrantes(self, request, context):
        self.relogio.ao_receber(request.lamport_ts)
        migrantes = [list(ind.genes) for ind in request.individuos]
        with self._pop_lock:
            self.populacao.sort(key=ga.fitness)
            self.populacao[: len(migrantes)] = migrantes
        logger.info(
            f"[Nó {self.meu_id}] Recebeu {len(migrantes)} migrantes do coordenador"
        )
        self._evento_migrantes.set()
        return genetico_pb2.Confirmacao(ok=True, mensagem="Migrantes integrados")

    def ReceberEleicao(self, request, context):
        logger.info(
            f"[Nó {self.meu_id}] Recebeu eleição do Nó {request.id_origem}"
        )
        threading.Thread(
            target=self.eleicao.iniciar_eleicao, daemon=True
        ).start()
        return genetico_pb2.Confirmacao(ok=True, mensagem="Eleição aceita")

    def ReceberLider(self, request, context):
        self.eleicao.definir_lider(request.id_lider, request.endereco)
        if request.id_lider == self.meu_id:
            self.ativar_coordenador()
        return genetico_pb2.Confirmacao(ok=True, mensagem="Líder registrado")

    def ObterStatus(self, request, context):
        with self._pop_lock:
            melhor = ga.melhor_individuo(self.populacao)
        return genetico_pb2.Status(
            no_id=self.meu_id,
            ciclo_atual=self.ciclo_atual,
            geracao_atual=self.geracao_atual,
            melhor_aptidao=ga.fitness(melhor),
            melhor_rota=" -> ".join(melhor),
        )

    # ── Loop de evolução ──────────────────────────────────────────────────────

    def _enviar_ao_coordenador(self):
        with self._pop_lock:
            top = ga.melhores(self.populacao, NUM_MIGRANTES)

        ts = self.relogio.antes_de_enviar()

        try:
            stub = self.get_stub(self.eleicao.lider_endereco)
            stub.EnviarMelhores(
                genetico_pb2.MensagemMigracao(
                    individuos=[
                        genetico_pb2.Individuo(
                            genes=ind,
                            aptidao=ga.fitness(ind),
                            geracao=self.geracao_atual,
                        )
                        for ind in top
                    ],
                    lamport_ts=ts,
                    origem=self.meu_nome,
                    ciclo=self.ciclo_atual,
                ),
                timeout=10,
            )
            logger.info(
                f"[Nó {self.meu_id}] Enviou {len(top)} indivíduos ao coordenador "
                f"(ciclo {self.ciclo_atual}, ts={ts})"
            )
        except grpc.RpcError as e:
            logger.error(
                f"[Nó {self.meu_id}] Erro ao enviar ao coordenador: {e.code()}"
            )

    def rodar_evolucao(self):
        logger.info(f"[Nó {self.meu_id}] Iniciando evolução local...")

        melhor_fit_anterior = 0.0
        ciclos_sem_melhora  = 0

        for ciclo in range(MAX_CICLOS):
            self.ciclo_atual = ciclo
            self._evento_migrantes.clear()

            # Evolução local
            for _ in range(GERACOES_POR_CICLO):
                with self._pop_lock:
                    self.populacao = ga.evoluir(self.populacao)
                    self.geracao_atual += 1
                self.relogio.evento_local()

            with self._pop_lock:
                melhor = ga.melhor_individuo(self.populacao)
            melhor_fit = ga.fitness(melhor)

            logger.info(
                f"[Nó {self.meu_id}] Ciclo {ciclo+1:3d} | "
                f"Geração {self.geracao_atual:4d} | "
                f"Fitness: {melhor_fit:.5f} | "
                f"Distância: {ga.distancia_total(melhor):.2f} | "
                f"Rota: {' '.join(melhor[:5])}..."
            )

            # Envia ao coordenador
            self._enviar_ao_coordenador()

            # Aguarda migrantes — timeout reduzido para 10s
            recebeu = self._evento_migrantes.wait(timeout=TIMEOUT_MIGRANTES)
            if not recebeu:
                logger.warning(
                    f"[Nó {self.meu_id}] Timeout aguardando migrantes "
                    f"no ciclo {ciclo+1} — continuando sem eles"
                )

            # Critério de convergência (conta mesmo quando migrantes não chegam)
            if abs(melhor_fit - melhor_fit_anterior) < DELTA_CONVERGENCIA:
                ciclos_sem_melhora += 1
                if ciclos_sem_melhora >= CICLOS_SEM_MELHORA_MAX:
                    logger.info(
                        f"[Nó {self.meu_id}] Sem melhora por {ciclos_sem_melhora} "
                        f"ciclos → convergiu no ciclo {ciclo+1}!"
                    )
                    break
            else:
                ciclos_sem_melhora = 0

            melhor_fit_anterior = melhor_fit
        

        # ── Resultado final ────────────────────────────────────────────────────
        with self._pop_lock:
            melhor = ga.melhor_individuo(self.populacao)
        
        tempo_total = time.time() - self.t_inicio

        logger.info(
            f"\n{'='*60}\n"
            f"[Nó {self.meu_id}] EVOLUÇÃO CONCLUÍDA\n"
            f" Melhor rota: {' -> '.join(melhor)}\n"
            f" Distância total: {ga.distancia_total(melhor):.4f}\n"
            f" Fitness: {ga.fitness(melhor):.6f}\n"
            f"Tempo total:{tempo_total:.2f}s\n"
            f"{'='*60}"
        )