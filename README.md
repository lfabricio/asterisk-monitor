# asterisk-monitor

Monitor de disponibilidade em tempo real para **Asterisk (PBX)**. Acompanha o estado dos ramais PJSIP via **ARI (Asterisk REST Interface)**, registra o histórico de cada transição e dispara alertas no **Webex** quando um ramal — ou o próprio Asterisk — cai ou volta.

## Funcionalidades

- 📡 **Monitoramento de ramais PJSIP** via ARI (`/endpoints/PJSIP`), com estado online/offline por ramal.
- 🔔 **Alertas no Webex** apenas nas transições relevantes (online ↔ offline), evitando ruído.
- 🩺 **Healthcheck do próprio Asterisk** (conectividade do ARI), com histórico separado.
- 🗂️ **Histórico persistente** em SQLite (mudanças de status e de conectividade).
- ⏱️ **Polling adaptativo**: 10s quando há alguém no dashboard, 5min quando ocioso.
- 📊 **Dashboard web** (Vite) servido por nginx.
- 🐳 **Pronto para Docker** via `docker-compose`.

## Arquitetura

```
┌──────────────┐      ARI / HTTP     ┌─────────────┐
│  Asterisk    │ ◀────────────────── │  backend    │  FastAPI + httpx
│  (PJSIP)     │                     │  :8000      │  → SQLite (histórico)
└──────────────┘                     └─────┬───────┘  → Webex (alertas)
                                           │
                                     ┌─────▼───────┐
                                     │  frontend   │  Vite SPA + nginx
                                     │  :8080      │
                                     └─────────────┘
```

- **Backend** — FastAPI com `httpx.AsyncClient` para o ARI e uma tarefa de background que faz o polling, persiste o histórico em SQLite e notifica o Webex.
- **Frontend** — SPA (Vite) servida por nginx, consumindo a API do backend.

## Stack

`Python` · `FastAPI` · `uvicorn` · `httpx` · `SQLite` · `Vite` · `nginx` · `Docker` · `Webex API`

## Como rodar

```bash
cp .env.example .env   # preencha ARI_BASE / ARI_USER / ARI_PASS (Webex é opcional)
docker compose up -d --build
```

- Dashboard: <http://localhost:8080>
- API: <http://localhost:8000>

### Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `ARI_BASE` | URL base do ARI (ex.: `http://asterisk:8088/ari`) |
| `ARI_USER` / `ARI_PASS` | Credenciais do ARI |
| `WEBEX_BOT_TOKEN` | Token do bot Webex (opcional — alertas) |
| `WEBEX_ROOM_ID` | Sala Webex de destino (opcional) |
| `DB_FILE` | Caminho do SQLite (default `/data/history.db`) |
