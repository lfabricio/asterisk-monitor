import os
import httpx
import logging
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

# Fuso horário do Brasil (UTC-3 fixo — horário de verão abolido desde 2019)
BRAZIL_TZ = timezone(timedelta(hours=-3))


async def _send_webex_message(message: str):
    """
    Envia uma mensagem markdown para o Webex Room configurado.
    Retorna True se enviou com sucesso, False caso contrário.
    """
    token = os.environ.get("WEBEX_BOT_TOKEN")
    room_id = os.environ.get("WEBEX_ROOM_ID")
    
    if not token or not room_id:
        return False

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
        return True
    except Exception as e:
        logger.error(f"Falha ao enviar mensagem Webex: {e}")
        return False


async def send_webex_alert(ramal: str, status: str):
    """
    Envia um alerta para um Webex Room assincronamente baseado no status do ramal.
    """
    token = os.environ.get("WEBEX_BOT_TOKEN")
    room_id = os.environ.get("WEBEX_ROOM_ID")
    
    if not token or not room_id:
        return

    now_str = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")
    status_lower = status.lower()

    if status_lower == "offline":
        message = f"🚨 **ALERTA:** O ramal **{ramal}** ficou **OFFLINE** às {now_str}!"
    elif status_lower == "online":
        message = f"✅ **INFO:** O ramal **{ramal}** voltou a ficar **ONLINE** às {now_str}."
    else:
        return

    await _send_webex_message(message)


async def send_webex_connectivity_alert(is_online: bool):
    """
    Envia um alerta de conectividade do servidor Asterisk (PBX) para o Webex.
    Dispara quando o servidor Asterisk fica offline ou volta online.
    """
    now_str = datetime.now(ZoneInfo("America/Sao_Paulo")).strftime("%d/%m/%Y %H:%M:%S")

    if is_online:
        message = (
            f"✅ **RECUPERAÇÃO:** O servidor **Asterisk (PBX)** voltou a ficar **ONLINE** "
            f"às {now_str}.\n\n"
            f"📊 O sistema de monitoramento retomou as verificações normalmente."
        )
    else:
        message = (
            f"🚨 **ALERTA CRÍTICO:** O servidor **Asterisk (PBX)** está **OFFLINE** "
            f"às {now_str}!\n\n"
            f"⚠️ Todos os serviços de telefonia podem estar indisponíveis.\n"
            f"🔧 Verifique o status do serviço e da conexão de rede."
        )

    await _send_webex_message(message)
