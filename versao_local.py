import time
import logging
import genetico_core as ga
from config import (
    TAMANHO_POPULACAO, GERACOES_POR_CICLO, MAX_CICLOS,
    CICLOS_SEM_MELHORA_MAX, DELTA_CONVERGENCIA,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

# Número de nós simulados para manter o mesmo tamanho de população total
NUM_NOS       = 5
POP_TOTAL     = NUM_NOS * TAMANHO_POPULACAO   # 1000 indivíduos


def rodar(semente: int = 42, verbose: bool = True) -> dict:
    """
    Executa o AG local e retorna um dicionário com os resultados:
      - historico_fitness : [float]  melhor fitness a cada ciclo equivalente
      - historico_distancia: [float] melhor distância a cada ciclo equivalente
      - historico_tempo   : [float]  tempo acumulado (s) a cada ciclo
      - melhor_rota       : [str]    melhor rota encontrada
      - melhor_distancia  : float
      - tempo_total       : float
      - ciclos            : int
      - geracoes          : int
    """
    import random
    random.seed(semente)

    populacao = ga.criar_populacao(POP_TOTAL)
    geracao   = 0

    historico_fitness   = []
    historico_distancia = []
    historico_tempo     = []

    melhor_fit_anterior = 0.0
    ciclos_sem_melhora  = 0
    t0                  = time.perf_counter()

    for ciclo in range(MAX_CICLOS):
        # Evolui por GERACOES_POR_CICLO gerações (mesmo intervalo da versão distribuída)
        populacao = ga.evoluir_n(populacao, GERACOES_POR_CICLO)
        geracao  += GERACOES_POR_CICLO

        melhor = ga.melhor_individuo(populacao)
        melhor_fit  = ga.fitness(melhor)
        melhor_dist = ga.distancia_total(melhor)
        t_acum = time.perf_counter() - t0

        historico_fitness.append(melhor_fit)
        historico_distancia.append(melhor_dist)
        historico_tempo.append(t_acum)

        if verbose:
            logger.info(
                f"[Local] Ciclo {ciclo+1:3d} | Geração {geracao:5d} | "
                f"Distância: {melhor_dist:.2f} | Fitness: {melhor_fit:.5f}"
            )

        # Critério de convergência
        if abs(melhor_fit - melhor_fit_anterior) < DELTA_CONVERGENCIA:
            ciclos_sem_melhora += 1
            if ciclos_sem_melhora >= CICLOS_SEM_MELHORA_MAX:
                if verbose:
                    logger.info(f"[Local] Convergiu no ciclo {ciclo+1}.")
                break
        else:
            ciclos_sem_melhora = 0
        melhor_fit_anterior = melhor_fit

    melhor = ga.melhor_individuo(populacao)
    tempo_total = time.perf_counter() - t0

    if verbose:
        logger.info(
            f"\n{'='*60}\n"
            f"[Local] CONCLUÍDO\n"
            f"  Melhor rota: {' -> '.join(melhor)}\n"
            f"  Distância total: {ga.distancia_total(melhor):.4f}\n"
            f"  Fitness: {ga.fitness(melhor):.6f}\n"
            f"  Tempo total: {tempo_total:.2f}s\n"
            f"{'='*60}"
        )

    return {
        "historico_fitness": historico_fitness,
        "historico_distancia": historico_distancia,
        "historico_tempo": historico_tempo,
        "melhor_rota": melhor,
        "melhor_distancia": ga.distancia_total(melhor),
        "melhor_fitness": ga.fitness(melhor),
        "tempo_total": tempo_total,
        "ciclos": len(historico_fitness),
        "geracoes": geracao,
    }


if __name__ == "__main__":
    resultado = rodar(semente=42)
    print(f"\nMelhor distância encontrada: {resultado['melhor_distancia']:.4f}")
    print(f"Tempo total: {resultado['tempo_total']:.2f}s")
    print(f"Ciclos: {resultado['ciclos']}")
