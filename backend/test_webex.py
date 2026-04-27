import asyncio
from dotenv import load_dotenv
from webex_notifier import send_webex_alert

# Carrega as variáveis do .env atual
load_dotenv()

async def test_alert():
    print("Testando o envio de notificação para o Webex...")
    print("Tentando enviar status 'offline' para o ramal 9999...")
    await send_webex_alert("9999", "offline")
    
    print("Aguardando 2 segundos...")
    await asyncio.sleep(2)
    
    print("Tentando enviar status 'online' para o ramal 9999...")
    await send_webex_alert("9999", "online")
    print("Teste finalizado. Verifique seu Webex Space!")

if __name__ == "__main__":
    asyncio.run(test_alert())
