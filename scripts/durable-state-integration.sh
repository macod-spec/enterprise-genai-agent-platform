#!/usr/bin/env bash
set -euo pipefail

readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly COMPOSE_PROJECT="enterprise-genai-durable-test"

for tool in docker openssl; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "required tool is unavailable: ${tool}" >&2
    exit 1
  fi
done

export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export REDIS_PASSWORD="$(openssl rand -hex 24)"
export GRAFANA_ADMIN_PASSWORD="$(openssl rand -hex 24)"
export POSTGRES_STATE_URL="postgresql://agent_platform:${POSTGRES_PASSWORD}@127.0.0.1:15432/agent_platform"
export REDIS_STATE_URL="redis://:${REDIS_PASSWORD}@127.0.0.1:16379/0"

cleanup() {
  docker compose --project-name "${COMPOSE_PROJECT}" --profile durable \
    --file "${PROJECT_ROOT}/compose.yaml" down --volumes --remove-orphans >/dev/null 2>&1 || true
  unset POSTGRES_PASSWORD REDIS_PASSWORD GRAFANA_ADMIN_PASSWORD POSTGRES_STATE_URL REDIS_STATE_URL
}
trap cleanup EXIT

docker compose --project-name "${COMPOSE_PROJECT}" --profile durable \
  --file "${PROJECT_ROOT}/compose.yaml" up --detach --wait postgres redis

"${PROJECT_ROOT}/.venv/bin/python" "${PROJECT_ROOT}/scripts/verify-durable-state.py"
