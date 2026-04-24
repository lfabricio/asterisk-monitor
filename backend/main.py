import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
import httpx
from dotenv import load_dotenv

load_dotenv()

ARI_BASE = os.getenv("ARI_BASE", "http://ASTERISK_HOST:8088/ari")
ARI_USER = os.getenv("ARI_USER", "ari_user")
ARI_PASS = os.getenv("ARI_PASS", "REDACTED_ARI_PASSWORD")

TIMEOUT = 5.0

# Cliente HTTP compartilhado para reuso de conexões (boa prática no httpx)
http_client = httpx.AsyncClient(auth=(ARI_USER, ARI_PASS), timeout=TIMEOUT)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Setup
    yield
    # Teardown
    await http_client.aclose()

app = FastAPI(title="Asterisk Monitor API", lifespan=lifespan)

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

@app.get("/api/monitor/3770")
async def monitor_3770():
    """Retorna o status simplificado do ramal 3770 para o monitoramento."""
    try:
        response = await http_client.get(f"{ARI_BASE}/endpoints/PJSIP/3770")
        response.raise_for_status()
        data = response.json()
        
        estado = data.get("state", "unknown")
        canais_ativos = len(data.get("channel_ids", []))
        
        return {
            "ramal": "3770",
            "status": estado,
            "canais_ativos": canais_ativos,
            "raw_data": data
        }
    except httpx.HTTPError as e:
        if e.response is not None and e.response.status_code == 404:
            raise HTTPException(status_code=404, detail="Ramal 3770 não encontrado")
        raise HTTPException(status_code=500, detail=f"Erro ao monitorar ramal 3770: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
