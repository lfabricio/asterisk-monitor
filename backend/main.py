import os
import time
from datetime import datetime
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
import httpx
from dotenv import load_dotenv
import asyncio
from database import init_db, log_status_if_changed, get_status_history, get_current_statuses, log_asterisk_connectivity, get_asterisk_connectivity_history, get_asterisk_current_connectivity
from webex_notifier import send_webex_alert, send_webex_connectivity_alert

load_dotenv()

ARI_BASE = os.environ["ARI_BASE"]
ARI_USER = os.environ["ARI_USER"]
ARI_PASS = os.environ["ARI_PASS"]

TIMEOUT = 5.0

last_frontend_activity = time.time()

# Cliente HTTP compartilhado para reuso de conexões (boa prática no httpx)
http_client = httpx.AsyncClient(auth=(ARI_USER, ARI_PASS), timeout=TIMEOUT)

def should_send_webex_alert(
    previous_status: str | None,
    current_status: str,
    previous_notifiable_status: str | None = None,
) -> bool:
    previous = previous_status.lower() if previous_status else None
    current = current_status.lower()

    if (previous, current) in {
        ("online", "offline"),
        ("offline", "online"),
    }:
        return True

    if previous == "unknown":
        last_notifiable = previous_notifiable_status.lower() if previous_notifiable_status else None
        return (last_notifiable, current) in {
            ("online", "offline"),
            ("offline", "online"),
        }

    return False

async def background_monitor_task():
    global last_frontend_activity
    last_asterisk_query = 0
    
    while True:
        now = time.time()
        time_since_activity = now - last_frontend_activity
        time_since_query = now - last_asterisk_query
        
        # Se a última atividade ocorreu há menos de 30 segundos, consideramos "ativo"
        is_active = time_since_activity < 30
        target_interval = 10 if is_active else 300  # 10s ou 5min
        
        if time_since_query >= target_interval:
            asterisk_online = False
            try:
                response = await http_client.get(f"{ARI_BASE}/endpoints/PJSIP")
                if response.status_code == 200:
                    asterisk_online = True
                    endpoints = response.json()
                    for ep in endpoints:
                        resource = ep.get("resource", "")
                        if resource.isdigit():
                            estado = ep.get("state", "unknown")
                            status_change = log_status_if_changed(resource, estado)
                            if status_change["changed"] and should_send_webex_alert(
                                status_change["previous_status"],
                                status_change["current_status"],
                                status_change["previous_notifiable_status"],
                            ):
                                # Dispara o alerta em background (sem bloquear o loop)
                                asyncio.create_task(send_webex_alert(resource, estado))
            except Exception as e:
                print(f"Error in background monitor: {e}")
            finally:
                # Loga a conectividade com o servidor Asterisk e dispara alerta se mudou
                conn_change = log_asterisk_connectivity(asterisk_online)
                if conn_change["changed"] and conn_change["previous_status"] != "unknown":
                    asyncio.create_task(
                        send_webex_connectivity_alert(asterisk_online)
                    )
            
            last_asterisk_query = time.time()
            
        # Dorme por apenas 1 segundo para poder acordar imediatamente se o usuário acessar
        await asyncio.sleep(1)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup
    init_db()
    task = asyncio.create_task(background_monitor_task())
    yield
    # Teardown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    await http_client.aclose()

app = FastAPI(title="Asterisk Monitor API", lifespan=lifespan)

@app.middleware("http")
async def track_activity(request: Request, call_next):
    global last_frontend_activity
    # Atualiza o timestamp de atividade sempre que recebe requisição na API
    last_frontend_activity = time.time()
    response = await call_next(request)
    return response

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/api/asterisk/info")
async def get_asterisk_info():
    """Retorna informações gerais do sistema Asterisk."""
    try:
        response = await http_client.get(f"{ARI_BASE}/asterisk/info")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Erro ao conectar com Asterisk: {str(e)}")

@app.get("/api/endpoints")
async def get_endpoints():
    """Lista todos os endpoints PJSIP."""
    try:
        response = await http_client.get(f"{ARI_BASE}/endpoints/PJSIP")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar endpoints: {str(e)}")

@app.get("/api/endpoints/{nome}")
async def get_endpoint_details(nome: str):
    """Retorna os detalhes de um endpoint específico."""
    try:
        response = await http_client.get(f"{ARI_BASE}/endpoints/PJSIP/{nome}")
        response.raise_for_status()
        return response.json()
    except httpx.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Endpoint não encontrado")
        raise HTTPException(status_code=500, detail=f"Erro ao buscar detalhes do endpoint: {str(e)}")

@app.get("/api/monitor/ramais")
async def monitor_ramais():
    """Retorna o status simplificado de todos os ramais numéricos."""
    try:
        response = await http_client.get(f"{ARI_BASE}/endpoints/PJSIP")
        response.raise_for_status()
        endpoints = response.json()
        
        ramais = []
        for ep in endpoints:
            resource = ep.get("resource", "")
            # Filtra apenas recursos que sejam apenas números (ignora trunks como cisco-gw)
            if resource.isdigit():
                estado = ep.get("state", "unknown")
                canais_ativos = len(ep.get("channel_ids", []))
                ramais.append({
                    "ramal": resource,
                    "status": estado,
                    "canais_ativos": canais_ativos,
                    "raw_data": ep
                })
        
        # Opcional: ordenar ramais em ordem crescente
        ramais.sort(key=lambda x: int(x["ramal"]))
        return ramais
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar lista de ramais: {str(e)}")

@app.get("/api/monitor/channels")
async def monitor_channels():
    """Retorna o número total de canais ativos (chamadas simultâneas) no PBX inteiro."""
    try:
        response = await http_client.get(f"{ARI_BASE}/channels")
        response.raise_for_status()
        canais = response.json()
        return {"total_channels": len(canais), "raw_data": canais}
    except httpx.HTTPError as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar canais globais: {str(e)}")

@app.get("/api/monitor/history")
async def monitor_history(hours: int = 24):
    """Retorna o histórico de eventos de status do período."""
    try:
        return get_status_history(hours)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar histórico: {str(e)}")

@app.get("/api/monitor/stats")
async def monitor_stats():
    """Retorna o status atual persistido para estatísticas globais."""
    try:
        return get_current_statuses()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar estatísticas: {str(e)}")

@app.get("/api/health")
async def health_check():
    """Verifica a saúde do sistema: backend + conectividade com o Asterisk."""
    asterisk_online = False
    asterisk_error = None
    try:
        resp = await http_client.get(f"{ARI_BASE}/asterisk/info", timeout=3.0)
        asterisk_online = resp.status_code == 200
    except httpx.ConnectError as e:
        asterisk_error = "connection_refused"
    except httpx.TimeoutException as e:
        asterisk_error = "timeout"
    except Exception as e:
        asterisk_error = str(e)

    # Loga a conectividade para histórico
    log_asterisk_connectivity(asterisk_online)

    current_conn = get_asterisk_current_connectivity()

    return {
        "status": "healthy" if asterisk_online else "degraded",
        "backend": "online",
        "asterisk": {
            "online": asterisk_online,
            "error": asterisk_error,
            "last_known_status": current_conn["status"],
            "last_checked": current_conn["last_updated"]
        },
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/health/connectivity-history")
async def connectivity_history(hours: int = 24):
    """Retorna o histórico de conectividade com o servidor Asterisk."""
    try:
        return get_asterisk_connectivity_history(hours)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao buscar histórico de conectividade: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
