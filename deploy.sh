#!/usr/bin/env bash
# Cria/atualiza o projeto "Asterisk Monitor" no Dokploy a partir do repo GitHub.
# - 2 Applications (backend, frontend) apontando para o mesmo repo,
#   cada uma com buildPath diferente.
# - Dokploy clona, builda o Dockerfile e roda no servidor.
#
# Pré-requisitos:
#   - ~/.secrets/dokploy-token (chmod 600)
#   - .env preenchido com ARI_*, WEBEX_*
#   - Uma SSH key cadastrada no Dokploy (Painel > Settings > SSH Keys),
#     com a chave pública correspondente como Deploy Key no repo do GitHub.
#     Exporte o ID da key como DOKPLOY_SSH_KEY_ID antes de rodar:
#       export DOKPLOY_SSH_KEY_ID=...

set -euo pipefail

# ---------- Config ----------
DOKPLOY_HOST="${DOKPLOY_HOST:-ASTERISK_HOST}"
DOKPLOY_API="http://${DOKPLOY_HOST}:3000/api"
PROJECT_NAME="${PROJECT_NAME:-Asterisk Monitor}"

GIT_URL="${GIT_URL:-git@github.com:lfabricio/asterisk-monitor.git}"
GIT_BRANCH="${GIT_BRANCH:-main}"

BACKEND_APP_NAME="${BACKEND_APP_NAME:-asterisk-monitor-backend}"
BACKEND_BUILD_PATH="${BACKEND_BUILD_PATH:-/backend}"

FRONTEND_APP_NAME="${FRONTEND_APP_NAME:-asterisk-monitor-frontend}"
FRONTEND_BUILD_PATH="${FRONTEND_BUILD_PATH:-/frontend}"
FRONTEND_PUBLISHED_PORT="${FRONTEND_PUBLISHED_PORT:-8080}"

TOKEN_FILE="${HOME}/.secrets/dokploy-token"
[[ -r "$TOKEN_FILE" ]] || { echo "ERRO: token não encontrado em $TOKEN_FILE"; exit 1; }
TOKEN="$(cat "$TOKEN_FILE")"

[[ -f .env ]] || { echo "ERRO: copie .env.example para .env e preencha"; exit 1; }
# shellcheck disable=SC1091
set -a; source .env; set +a

[[ -n "${DOKPLOY_SSH_KEY_ID:-}" ]] || {
  echo "ERRO: defina DOKPLOY_SSH_KEY_ID com o ID da chave SSH cadastrada no Dokploy."
  echo "      Liste em http://${DOKPLOY_HOST}:3000 → Settings → SSH Keys"
  echo "      Ou via API:"
  echo "        curl -s -H 'x-api-key: \$(cat ~/.secrets/dokploy-token)' http://${DOKPLOY_HOST}:3000/api/sshKey.all | jq"
  exit 1
}

for cmd in jq curl python3; do
  command -v "$cmd" >/dev/null || { echo "ERRO: '$cmd' não instalado"; exit 1; }
done

# ---------- Helpers ----------
api_post() {
  local path="$1"; shift
  curl -fsS -X POST -H "x-api-key: ${TOKEN}" -H "Content-Type: application/json" \
    "${DOKPLOY_API}/${path}" "$@"
}
api_get() {
  curl -fsS -H "x-api-key: ${TOKEN}" "${DOKPLOY_API}/$1"
}

resolve_project_id() {
  api_get "project.all" | jq -r --arg n "$PROJECT_NAME" '.[] | select(.name==$n) | .projectId' | head -1
}
resolve_default_env_id() {
  api_get "project.one?projectId=$1" | jq -r '.environments[] | select(.isDefault==true) | .environmentId'
}
resolve_app_id_by_name() {
  api_get "project.one?projectId=$1" \
    | jq -r --arg n "$2" '.environments[].applications[]? | select(.name==$n) | .applicationId' | head -1
}
get_app() { api_get "application.one?applicationId=$1"; }

ensure_app() {
  local app_name="$1"
  local existing
  existing="$(resolve_app_id_by_name "$PROJECT_ID" "$app_name" || true)"
  if [[ -n "$existing" ]]; then echo "$existing"; return; fi
  api_post application.create \
    -d "$(jq -nc --arg n "$app_name" --arg e "$ENV_ID" '{name:$n, environmentId:$e}')" \
    | jq -r '.applicationId'
}

set_source_git() {
  local app_id="$1" build_path="$2"
  api_post application.update -d "$(jq -nc --arg id "$app_id" '{applicationId:$id, sourceType:"git"}')" >/dev/null
  api_post application.saveGitProvider -d "$(jq -nc \
      --arg id  "$app_id" \
      --arg url "$GIT_URL" \
      --arg br  "$GIT_BRANCH" \
      --arg bp  "$build_path" \
      --arg key "$DOKPLOY_SSH_KEY_ID" \
      '{applicationId:$id, customGitUrl:$url, customGitBranch:$br, customGitBuildPath:$bp, customGitSSHKeyId:$key, watchPaths:[]}')" >/dev/null
}

set_build_dockerfile() {
  local app_id="$1"
  api_post application.saveBuildType -d "$(jq -nc --arg id "$app_id" \
      '{applicationId:$id, buildType:"dockerfile", dockerfile:"Dockerfile", dockerContextPath:".", dockerBuildStage:"", herokuVersion:"", railpackVersion:""}')" >/dev/null
}

set_env() {
  local app_id="$1" env_block="$2"
  api_post application.saveEnvironment -d "$(jq -nc \
      --arg id "$app_id" --arg env "$env_block" \
      '{applicationId:$id, env:$env, buildArgs:"", buildSecrets:"", createEnvFile:false}')" >/dev/null
}

ensure_port() {
  local app_id="$1" published="$2" target="$3"
  local existing
  existing="$(get_app "$app_id" | jq -r --argjson p "$published" '.ports[]? | select(.publishedPort==$p) | .portId' | head -1)"
  [[ -n "$existing" ]] && return 0
  api_post port.create -d "$(jq -nc \
      --arg id "$app_id" --argjson p "$published" --argjson t "$target" \
      '{applicationId:$id, publishedPort:$p, targetPort:$t, protocol:"tcp"}')" >/dev/null
}

deploy_app() {
  api_post application.deploy -d "$(jq -nc --arg id "$1" '{applicationId:$id}')" >/dev/null
}

# ---------- 1. Project ----------
echo "==> [1/5] Resolvendo projeto '${PROJECT_NAME}'..."
PROJECT_ID="$(resolve_project_id || true)"
if [[ -z "$PROJECT_ID" ]]; then
  echo "    Criando projeto..."
  PROJECT_ID="$(api_post project.create -d "$(jq -nc --arg n "$PROJECT_NAME" '{name:$n}')" \
    | jq -r '.project.projectId // .projectId')"
fi
ENV_ID="$(resolve_default_env_id "$PROJECT_ID")"
echo "    projectId=${PROJECT_ID}  environmentId=${ENV_ID}"

# ---------- 2. Backend ----------
echo "==> [2/5] Backend application..."
BACKEND_ID="$(ensure_app "$BACKEND_APP_NAME")"
echo "    applicationId=${BACKEND_ID}"
set_source_git       "$BACKEND_ID" "$BACKEND_BUILD_PATH"
set_build_dockerfile "$BACKEND_ID"
BACKEND_ENV="$(printf 'ARI_BASE=%s\nARI_USER=%s\nARI_PASS=%s\nWEBEX_BOT_TOKEN=%s\nWEBEX_ROOM_ID=%s\nDB_FILE=/data/history.db\n' \
  "${ARI_BASE}" "${ARI_USER}" "${ARI_PASS}" "${WEBEX_BOT_TOKEN:-}" "${WEBEX_ROOM_ID:-}")"
set_env "$BACKEND_ID" "$BACKEND_ENV"

echo "==> [3/5] Disparando build do backend..."
deploy_app "$BACKEND_ID"
BACKEND_APPNAME_REAL="$(get_app "$BACKEND_ID" | jq -r '.appName')"
echo "    backend appName real = ${BACKEND_APPNAME_REAL}"

# ---------- 3. Frontend ----------
echo "==> [4/5] Frontend application..."
FRONTEND_ID="$(ensure_app "$FRONTEND_APP_NAME")"
echo "    applicationId=${FRONTEND_ID}"
set_source_git       "$FRONTEND_ID" "$FRONTEND_BUILD_PATH"
set_build_dockerfile "$FRONTEND_ID"
FRONTEND_ENV="$(printf 'BACKEND_UPSTREAM=%s:8000\n' "$BACKEND_APPNAME_REAL")"
set_env "$FRONTEND_ID" "$FRONTEND_ENV"
ensure_port "$FRONTEND_ID" "$FRONTEND_PUBLISHED_PORT" 80

echo "==> [5/5] Disparando build do frontend..."
deploy_app "$FRONTEND_ID"

echo
echo "OK!"
echo "    Frontend: http://${DOKPLOY_HOST}:${FRONTEND_PUBLISHED_PORT}"
echo "    Painel:   http://${DOKPLOY_HOST}:3000"
