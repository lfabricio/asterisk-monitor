import os
import httpx
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Fuso horário do Brasil (UTC-3 fixo — horário de verão abolido desde 2019)
BRAZIL_TZ = timezone(timedelta(hours=-3))

async def send_webex_alert(ramal: str, status: str):
    """
    Envia um alerta para um Webex Room assincronamente baseado no status do ramal.
    """
    token = os.environ.get("WEBEX_BOT_TOKEN")
    room_id = os.environ.get("WEBEX_ROOM_ID")
    
    if not token or not room_id:
        # Se as credenciais não estiverem configuradas, apenas ignoramos silenciosamente
        return

    now_str = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
    status_lower = status.lower()

    if status_lower == "offline":
        message = f"🚨 **ALERTA:** O ramal **{ramal}** ficou **OFFLINE** às {now_str}!"
    elif status_lower == "online":
        message = f"✅ **INFO:** O ramal **{ramal}** voltou a ficar **ONLINE** às {now_str}."
    else:
        # Ignora outros status (ex: unknown)
        return

    url = "https://webexapis.com/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "roomId": room_id,
        "markdown": message
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=headers, json=payload, timeout=5.0)
            response.raise_for_status()
    except Exception as e:
        logger.error(f"Falha ao enviar alerta Webex para o ramal {ramal}: {e}")
