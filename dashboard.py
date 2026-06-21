import grpc
import logging
from typing import Optional

import genetico_pb2
import genetico_pb2_grpc
from config import NOS, TIMEOUT_RPC

try:
    from fastapi import FastAPI
    from fastapi.responses import HTMLResponse, JSONResponse
    import uvicorn
except ImportError:
    print("[ERRO] FastAPI não instalado. Execute: pip install fastapi uvicorn")
    raise

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Dashboard AG Distribuído", version="1.0")


# ── Cliente gRPC para cada nó ─────────────────────────────────────────────────

def consultar_no(nid: int, endereco: str) -> Optional[dict]:
    """Consulta o status de um nó via gRPC. Retorna None se indisponível."""
    try:
        canal = grpc.insecure_channel(endereco)
        stub  = genetico_pb2_grpc.GeneticoServiceStub(canal)
        status = stub.ObterStatus(genetico_pb2.Vazio(), timeout=TIMEOUT_RPC)
        return {
            "id"            : nid,
            "endereco"      : endereco,
            "online"        : True,
            "ciclo_atual"   : status.ciclo_atual,
            "geracao_atual" : status.geracao_atual,
            "melhor_aptidao": round(status.melhor_aptidao, 6),
            "melhor_dist"   : round(1 / max(status.melhor_aptidao, 1e-9), 4),
            "melhor_rota"   : status.melhor_rota,
        }
    except grpc.RpcError:
        return {
            "id"            : nid,
            "endereco"      : endereco,
            "online"        : False,
            "ciclo_atual"   : 0,
            "geracao_atual" : 0,
            "melhor_aptidao": 0.0,
            "melhor_dist"   : 0.0,
            "melhor_rota"   : "—",
        }


# ── Endpoints da API ──────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    """Retorna o status de todos os nós."""
    nos_status = [consultar_no(nid, addr) for nid, addr in NOS.items()]
    
    nos_online = [n for n in nos_status if n["online"]]
    melhor_global = None
    if nos_online:
        melhor_no = max(nos_online, key=lambda n: n["melhor_aptidao"])
        melhor_global = {
            "no_id"     : melhor_no["id"],
            "distancia" : melhor_no["melhor_dist"],
            "aptidao"   : melhor_no["melhor_aptidao"],
            "rota"      : melhor_no["melhor_rota"],
        }
    
    return JSONResponse({
        "nos"           : nos_status,
        "total_online"  : len(nos_online),
        "total_nos"     : len(NOS),
        "melhor_global" : melhor_global,
    })


@app.get("/api/no/{nid}")
async def get_no(nid: int):
    """Retorna o status de um nó específico."""
    if nid not in NOS:
        return JSONResponse({"erro": f"Nó {nid} não existe"}, status_code=404)
    return JSONResponse(consultar_no(nid, NOS[nid]))


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve o dashboard HTML com atualização automática."""
    return HTML_DASHBOARD


# ── Interface HTML ────────────────────────────────────────────────────────────

HTML_DASHBOARD = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <title>Dashboard — AG Distribuído</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }
    h1 { font-size: 1.5rem; font-weight: 700; margin-bottom: 6px; color: #f8fafc; }
    .subtitle { color: #94a3b8; font-size: 0.875rem; margin-bottom: 24px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 16px; }
    .card { background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }
    .card.offline { border-color: #dc2626; opacity: 0.6; }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 14px; }
    .card-title { font-size: 1.1rem; font-weight: 600; color: #f1f5f9; }
    .badge { padding: 3px 10px; border-radius: 99px; font-size: 0.75rem; font-weight: 600; }
    .badge.online { background: #166534; color: #4ade80; }
    .badge.offline { background: #7f1d1d; color: #f87171; }
    .badge.coord { background: #1e3a5f; color: #60a5fa; margin-left: 6px; }
    .metric { display: flex; justify-content: space-between; margin: 6px 0; font-size: 0.875rem; }
    .metric-label { color: #94a3b8; }
    .metric-value { color: #f1f5f9; font-weight: 500; font-family: monospace; }
    .rota { font-family: monospace; font-size: 0.75rem; color: #94a3b8;
            margin-top: 10px; word-break: break-all; line-height: 1.4; }
    .global { background: #1e293b; border: 1px solid #3b82f6; border-radius: 12px;
              padding: 20px; margin-bottom: 24px; }
    .global h2 { font-size: 1rem; font-weight: 600; color: #60a5fa; margin-bottom: 12px; }
    .global-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; }
    .gm { text-align: center; }
    .gm-val { font-size: 1.4rem; font-weight: 700; color: #f1f5f9; font-family: monospace; }
    .gm-label { font-size: 0.75rem; color: #94a3b8; margin-top: 2px; }
    .status-bar { display: flex; gap: 8px; align-items: center; margin-bottom: 20px; }
    .dot { width: 8px; height: 8px; border-radius: 50%; background: #4ade80; animation: pulse 2s infinite; }
    .dot.updating { background: #facc15; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
    .ts { color: #64748b; font-size: 0.75rem; }
  </style>
</head>
<body>
  <h1>Algoritmo Genético Distribuído — TSP</h1>
  <p class="subtitle">Dashboard de monitoramento em tempo real · Atualização a cada 3s</p>

  <div class="status-bar">
    <div class="dot" id="dot"></div>
    <span class="ts" id="ts">Aguardando dados...</span>
  </div>

  <div class="global" id="global">
    <h2>Melhor solução global</h2>
    <div class="global-metrics">
      <div class="gm"><div class="gm-val" id="g-dist">—</div><div class="gm-label">Distância total</div></div>
      <div class="gm"><div class="gm-val" id="g-fit">—</div><div class="gm-label">Fitness</div></div>
      <div class="gm"><div class="gm-val" id="g-online">—</div><div class="gm-label">Nós online</div></div>
    </div>
    <div class="rota" id="g-rota"></div>
  </div>

  <div class="grid" id="grid"></div>

  <script>
    const COORD_ID = 2;

    async function atualizar() {
      const dot = document.getElementById('dot');
      dot.classList.add('updating');
      try {
        const res  = await fetch('/api/status');
        const data = await res.json();

        // Global
        if (data.melhor_global) {
          const mg = data.melhor_global;
          document.getElementById('g-dist').textContent   = mg.distancia.toFixed(4);
          document.getElementById('g-fit').textContent    = mg.aptidao.toFixed(6);
          document.getElementById('g-online').textContent = `${data.total_online}/${data.total_nos}`;
          document.getElementById('g-rota').textContent   = 'Melhor rota (nó M' + mg.no_id + '): ' + mg.rota;
        }

        // Nós
        const grid = document.getElementById('grid');
        grid.innerHTML = data.nos.map(no => `
          <div class="card ${no.online ? '' : 'offline'}">
            <div class="card-header">
              <span class="card-title">Nó M${no.id}</span>
              <span>
                <span class="badge ${no.online ? 'online' : 'offline'}">${no.online ? 'online' : 'offline'}</span>
                ${no.id === COORD_ID ? '<span class="badge coord">coordenador</span>' : ''}
              </span>
            </div>
            <div class="metric"><span class="metric-label">Ciclo atual</span><span class="metric-value">${no.ciclo_atual}</span></div>
            <div class="metric"><span class="metric-label">Geração atual</span><span class="metric-value">${no.geracao_atual}</span></div>
            <div class="metric"><span class="metric-label">Melhor fitness</span><span class="metric-value">${no.melhor_aptidao}</span></div>
            <div class="metric"><span class="metric-label">Melhor distância</span><span class="metric-value">${no.melhor_dist}</span></div>
            <div class="rota">${no.melhor_rota || '—'}</div>
          </div>
        `).join('');

        document.getElementById('ts').textContent = 'Última atualização: ' + new Date().toLocaleTimeString('pt-BR');
      } catch (e) {
        document.getElementById('ts').textContent = 'Erro ao conectar — verifique se os nós estão rodando';
      } finally {
        dot.classList.remove('updating');
      }
    }

    atualizar();
    setInterval(atualizar, 3000);
  </script>
</body>
</html>
"""


# ── Ponto de entrada ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("Dashboard rodando em: http://localhost:8080")
    print("Consulte a API em: http://localhost:8080/api/status")
    uvicorn.run(app, host="0.0.0.0", port=8080, log_level="warning")
