# ──────────────────────────────────────────────────────────────────────────────
# benchmark.py — Comparação: versão distribuída (simulada) vs versão local
#
# Ambas as versões usam a mesma população total e os mesmos parâmetros,
# permitindo uma comparação justa em termos de esforço computacional.
#
# Métricas coletadas:
#   - Evolução do fitness (melhor solução) a cada ciclo
#   - Evolução da distância total da melhor rota
#   - Tempo de execução acumulado
#   - Tempo até atingir uma qualidade alvo
#   - Speedup teórico da versão distribuída
#
# Uso:
#   python benchmark.py
# ──────────────────────────────────────────────────────────────────────────────

import time
import json
import random
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import genetico_core as ga
import versao_local
from config import (
    TAMANHO_POPULACAO, NUM_MIGRANTES, GERACOES_POR_CICLO, MAX_CICLOS,
    CICLOS_SEM_MELHORA_MAX, DELTA_CONVERGENCIA,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

NUM_NOS   = 5
SEMENTE   = 42


# ── Versão distribuída simulada ───────────────────────────────────────────────

def _evoluir_ilha(args):
    """Evolui uma ilha localmente (executada em thread separada)."""
    ilha, n_geracoes, semente_ilha = args
    random.seed(semente_ilha)
    return ga.evoluir_n(ilha, n_geracoes)


def migrar(ilhas: list) -> list:
    """
    Realiza a migração em estrela:
    - Coleta os N melhores de cada ilha (com rótulo de origem)
    - Redistribui para cada ilha, excluindo os próprios indivíduos
    """
    # Coleta melhores de cada ilha com índice de origem
    pool = []
    for idx, ilha in enumerate(ilhas):
        for ind in ga.melhores(ilha, NUM_MIGRANTES):
            pool.append((idx, ind))

    # Ordena por aptidão
    pool.sort(key=lambda x: ga.fitness(x[1]), reverse=True)

    novas_ilhas = []
    for idx, ilha in enumerate(ilhas):
        # Migrantes externos: não vieram desta ilha
        externos = [ind for (origem, ind) in pool if origem != idx][:NUM_MIGRANTES]

        if externos:
            # Substitui os piores pelos migrantes
            nova = sorted(ilha, key=ga.fitness, reverse=True)
            nova = nova[:-len(externos)] + externos
        else:
            nova = ilha[:]

        novas_ilhas.append(nova)

    return novas_ilhas


def rodar_distribuido_simulado(semente: int = SEMENTE, verbose: bool = True) -> dict:
    """
    Simula o AG distribuído em processo único usando ThreadPoolExecutor.

    Cada 'ciclo' representa:
      1. Todas as ilhas evoluindo em paralelo (ThreadPoolExecutor)
      2. Migração em estrela entre as ilhas
      3. Critério de convergência global

    O tempo de parede (wall-clock) de cada ciclo é ~igual ao tempo de UMA ilha,
    pois as outras rodam em paralelo — isso reflete o ganho real da distribuição.
    """
    random.seed(semente)
    ilhas = [ga.criar_populacao(TAMANHO_POPULACAO) for _ in range(NUM_NOS)]

    historico_fitness    = []
    historico_distancia  = []
    historico_tempo      = []
    historico_tempo_seq  = []   # tempo equivalente se fosse sequencial

    melhor_fit_anterior = 0.0
    ciclos_sem_melhora  = 0
    t0                  = time.perf_counter()
    t0_seq              = 0.0   # acumula tempo sequencial estimado

    for ciclo in range(MAX_CICLOS):
        t_ciclo_inicio = time.perf_counter()

        # Evolui todas as ilhas em paralelo
        sementes = [semente + ciclo * NUM_NOS + i for i in range(NUM_NOS)]
        args = [(ilhas[i], GERACOES_POR_CICLO, sementes[i]) for i in range(NUM_NOS)]

        with ThreadPoolExecutor(max_workers=NUM_NOS) as ex:
            ilhas = list(ex.map(_evoluir_ilha, args))

        t_ciclo_paralelo = time.perf_counter() - t_ciclo_inicio
        # Tempo sequencial equivalente: se cada ilha rodasse uma após a outra
        t0_seq += t_ciclo_paralelo * NUM_NOS

        # Migração
        ilhas = migrar(ilhas)

        # Melhor global entre todas as ilhas
        todos       = [ind for ilha in ilhas for ind in ilha]
        melhor      = ga.melhor_individuo(todos)
        melhor_fit  = ga.fitness(melhor)
        melhor_dist = ga.distancia_total(melhor)
        t_acum      = time.perf_counter() - t0

        historico_fitness.append(melhor_fit)
        historico_distancia.append(melhor_dist)
        historico_tempo.append(t_acum)
        historico_tempo_seq.append(t0_seq)

        if verbose:
            logger.info(
                f"[Distribuído] Ciclo {ciclo+1:3d} | "
                f"Distância: {melhor_dist:.2f} | "
                f"Fitness: {melhor_fit:.5f} | "
                f"Tempo paralelo: {t_acum:.2f}s"
            )

        # Convergência
        if abs(melhor_fit - melhor_fit_anterior) < DELTA_CONVERGENCIA:
            ciclos_sem_melhora += 1
            if ciclos_sem_melhora >= CICLOS_SEM_MELHORA_MAX:
                if verbose:
                    logger.info(f"[Distribuído] Convergiu no ciclo {ciclo+1}.")
                break
        else:
            ciclos_sem_melhora = 0
        melhor_fit_anterior = melhor_fit

    todos       = [ind for ilha in ilhas for ind in ilha]
    melhor      = ga.melhor_individuo(todos)
    tempo_total = time.perf_counter() - t0

    if verbose:
        logger.info(
            f"\n{'='*60}\n"
            f"[Distribuído] CONCLUÍDO\n"
            f"  Melhor rota:     {' -> '.join(melhor)}\n"
            f"  Distância total: {ga.distancia_total(melhor):.4f}\n"
            f"  Fitness:         {ga.fitness(melhor):.6f}\n"
            f"  Tempo total:     {tempo_total:.2f}s\n"
            f"{'='*60}"
        )

    return {
        "historico_fitness"    : historico_fitness,
        "historico_distancia"  : historico_distancia,
        "historico_tempo"      : historico_tempo,
        "historico_tempo_seq"  : historico_tempo_seq,
        "melhor_rota"          : melhor,
        "melhor_distancia"     : ga.distancia_total(melhor),
        "melhor_fitness"       : ga.fitness(melhor),
        "tempo_total"          : tempo_total,
        "ciclos"               : len(historico_fitness),
        "geracoes"             : len(historico_fitness) * GERACOES_POR_CICLO,
    }


# ── Análise comparativa ───────────────────────────────────────────────────────

def calcular_ciclos_para_qualidade(historico_fitness: list, alvo: float):
    """Retorna quantos ciclos foram necessários para atingir um fitness alvo."""
    for i, f in enumerate(historico_fitness):
        if f >= alvo:
            return i + 1
    return None   # não atingiu


def imprimir_relatorio(res_local: dict, res_dist: dict):
    """Imprime um relatório comparativo formatado."""
    sep = "=" * 65

    print(f"\n{sep}")
    print("RELATÓRIO COMPARATIVO: LOCAL vs DISTRIBUÍDO")
    print(sep)

    # Qualidade da solução
    print(f"\n{'QUALIDADE DA SOLUÇÃO FINAL':^65}")
    print(f"  {'Métrica':<35} {'Local':>12} {'Distribuído':>12}")
    print(f"  {'-'*35} {'-'*12} {'-'*12}")
    print(f"  {'Melhor distância (menor = melhor)':<35} "
          f"{res_local['melhor_distancia']:>12.4f} "
          f"{res_dist['melhor_distancia']:>12.4f}")
    print(f"  {'Melhor fitness (maior = melhor)':<35} "
          f"{res_local['melhor_fitness']:>12.6f} "
          f"{res_dist['melhor_fitness']:>12.6f}")
    print(f"  {'Ciclos até convergir':<35} "
          f"{res_local['ciclos']:>12} "
          f"{res_dist['ciclos']:>12}")

    # Tempo de execução
    print(f"\n{'DESEMPENHO DE EXECUÇÃO':^65}")
    print(f"  {'Métrica':<35} {'Local':>12} {'Distribuído':>12}")
    print(f"  {'-'*35} {'-'*12} {'-'*12}")
    print(f"  {'Tempo total (s)':<35} "
          f"{res_local['tempo_total']:>12.2f} "
          f"{res_dist['tempo_total']:>12.2f}")

    speedup = res_local['tempo_total'] / max(res_dist['tempo_total'], 0.001)
    print(f"  {'Speedup observado (local/dist.)':<35} "
          f"{'—':>12} "
          f"{speedup:>11.2f}x")
    print(f"  {'Speedup teórico ({NUM_NOS} nós)':<35} "
          f"{'—':>12} "
          f"{NUM_NOS:>11}x")

    # Qualidade por ciclo (convergência)
    alvo = min(
        max(res_local["historico_fitness"]),
        max(res_dist["historico_fitness"])
    ) * 0.90   # 90% da melhor solução

    c_local = calcular_ciclos_para_qualidade(res_local["historico_fitness"], alvo)
    c_dist  = calcular_ciclos_para_qualidade(res_dist["historico_fitness"], alvo)

    print(f"\n{'VELOCIDADE DE CONVERGÊNCIA (90% da melhor solução)':^65}")
    print(f"  {'Fitness alvo':<35} {alvo:>12.6f} {alvo:>12.6f}")
    c_local_str = str(c_local) if c_local else "não atingiu"
    c_dist_str  = str(c_dist)  if c_dist  else "não atingiu"
    print(f"  {'Ciclos necessários':<35} {c_local_str:>12} {c_dist_str:>12}")

    # Melhoria de qualidade
    melhoria = (
        (res_local["melhor_distancia"] - res_dist["melhor_distancia"])
        / res_local["melhor_distancia"] * 100
    )
    print(f"\n  → Distribuído encontrou rota {abs(melhoria):.1f}% "
          + ("melhor" if melhoria > 0 else "pior") + " que o local.")

    print(f"\n{sep}\n")


# ── Geração de gráficos ───────────────────────────────────────────────────────

def gerar_graficos(res_local: dict, res_dist: dict, salvar_em: str = "benchmark_graficos.png"):
    """Gera 4 gráficos comparativos e salva como PNG."""
    try:
        import matplotlib.pyplot as plt
        import matplotlib.gridspec as gridspec
    except ImportError:
        logger.warning("matplotlib não disponível — gráficos não gerados.")
        return

    ciclos_local = list(range(1, res_local["ciclos"] + 1))
    ciclos_dist  = list(range(1, res_dist["ciclos"] + 1))

    fig = plt.figure(figsize=(14, 10))
    fig.suptitle(
        "Comparação: AG Local vs AG Distribuído — TSP com 20 cidades",
        fontsize=14, fontweight="bold", y=0.98
    )
    gs = gridspec.GridSpec(2, 2, hspace=0.4, wspace=0.35)

    # ── Gráfico 1: Evolução do fitness por ciclo ──────────────────────────────
    ax1 = fig.add_subplot(gs[0, 0])
    ax1.plot(ciclos_local, res_local["historico_fitness"],
             color="#2196F3", linewidth=1.8, label="Local (1000 ind.)")
    ax1.plot(ciclos_dist,  res_dist["historico_fitness"],
             color="#FF5722", linewidth=1.8, linestyle="--", label="Distribuído (5×200)")
    ax1.set_title("Evolução do Fitness por Ciclo", fontsize=11, fontweight="bold")
    ax1.set_xlabel("Ciclo de migração")
    ax1.set_ylabel("Melhor fitness (1/distância)")
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.3)

    # ── Gráfico 2: Evolução da distância por ciclo ────────────────────────────
    ax2 = fig.add_subplot(gs[0, 1])
    ax2.plot(ciclos_local, res_local["historico_distancia"],
             color="#2196F3", linewidth=1.8, label="Local")
    ax2.plot(ciclos_dist,  res_dist["historico_distancia"],
             color="#FF5722", linewidth=1.8, linestyle="--", label="Distribuído")
    ax2.set_title("Distância da Melhor Rota por Ciclo", fontsize=11, fontweight="bold")
    ax2.set_xlabel("Ciclo de migração")
    ax2.set_ylabel("Distância total (menor = melhor)")
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.3)

    # ── Gráfico 3: Fitness em função do tempo real ────────────────────────────
    ax3 = fig.add_subplot(gs[1, 0])
    ax3.plot(res_local["historico_tempo"], res_local["historico_fitness"],
             color="#2196F3", linewidth=1.8, label="Local")
    ax3.plot(res_dist["historico_tempo"],  res_dist["historico_fitness"],
             color="#FF5722", linewidth=1.8, linestyle="--", label="Distribuído (paralelo)")
    ax3.set_title("Fitness × Tempo de Execução (parede)", fontsize=11, fontweight="bold")
    ax3.set_xlabel("Tempo acumulado (s)")
    ax3.set_ylabel("Melhor fitness")
    ax3.legend(fontsize=9)
    ax3.grid(True, alpha=0.3)

    # ── Gráfico 4: Barras de comparação final ─────────────────────────────────
    ax4 = fig.add_subplot(gs[1, 1])
    metricas = ["Distância\nfinal", "Ciclos até\nconvergir", "Tempo total (s)"]
    vals_local = [
        res_local["melhor_distancia"],
        res_local["ciclos"],
        res_local["tempo_total"],
    ]
    vals_dist = [
        res_dist["melhor_distancia"],
        res_dist["ciclos"],
        res_dist["tempo_total"],
    ]

    # Normaliza para comparação visual
    maximos = [max(a, b) for a, b in zip(vals_local, vals_dist)]
    n_local = [v / m for v, m in zip(vals_local, maximos)]
    n_dist  = [v / m for v, m in zip(vals_dist,  maximos)]

    x = range(len(metricas))
    width = 0.35
    bars1 = ax4.bar([i - width/2 for i in x], n_local, width,
                    label="Local", color="#2196F3", alpha=0.85)
    bars2 = ax4.bar([i + width/2 for i in x], n_dist, width,
                    label="Distribuído", color="#FF5722", alpha=0.85)

    # Valores reais acima das barras
    for bar, val in zip(bars1, vals_local):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                 f"{val:.1f}", ha="center", va="bottom", fontsize=7.5)
    for bar, val in zip(bars2, vals_dist):
        ax4.text(bar.get_x() + bar.get_width()/2, bar.get_height() + 0.01,
                 f"{val:.1f}", ha="center", va="bottom", fontsize=7.5)

    ax4.set_title("Comparação Final (normalizado)", fontsize=11, fontweight="bold")
    ax4.set_xticks(list(x))
    ax4.set_xticklabels(metricas, fontsize=9)
    ax4.set_ylabel("Valor relativo ao máximo")
    ax4.set_ylim(0, 1.25)
    ax4.legend(fontsize=9)
    ax4.grid(True, alpha=0.3, axis="y")

    plt.savefig(salvar_em, dpi=150, bbox_inches="tight")
    logger.info(f"Gráficos salvos em '{salvar_em}'")
    return salvar_em


# ── Ponto de entrada ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n" + "="*65)
    print("BENCHMARK — Algoritmo Genético: Local vs Distribuído")
    print(f"  Cidades    : 20")
    print(f"  Pop. total : {NUM_NOS} × {TAMANHO_POPULACAO} = {NUM_NOS*TAMANHO_POPULACAO}")
    print(f"  Ger./ciclo : {GERACOES_POR_CICLO}")
    print(f"  Semente    : {SEMENTE}")
    print("="*65 + "\n")

    print("► Rodando versão LOCAL...")
    t0 = time.perf_counter()
    res_local = versao_local.rodar(semente=SEMENTE, verbose=True)
    print(f"  Concluído em {time.perf_counter()-t0:.2f}s\n")

    print("► Rodando versão DISTRIBUÍDA (simulada com threads)...")
    t0 = time.perf_counter()
    res_dist = rodar_distribuido_simulado(semente=SEMENTE, verbose=True)
    print(f"  Concluído em {time.perf_counter()-t0:.2f}s\n")

    # Relatório
    imprimir_relatorio(res_local, res_dist)

    # Salva resultados em JSON
    resultados = {
        "local"      : {k: v if not isinstance(v, list) or not v or not isinstance(v[0], str)
                          else v
                          for k, v in res_local.items()},
        "distribuido": {k: v if not isinstance(v, list) or not v or not isinstance(v[0], str)
                          else v
                          for k, v in res_dist.items()},
    }
    with open("benchmark_resultados.json", "w") as f:
        json.dump(resultados, f, indent=2, default=str)
    logger.info("Resultados salvos em 'benchmark_resultados.json'")

    # Gráficos
    gerar_graficos(res_local, res_dist, "benchmark_graficos.png")
