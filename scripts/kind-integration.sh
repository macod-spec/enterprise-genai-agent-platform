#!/usr/bin/env bash
set -euo pipefail

readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly CLUSTER_NAME="enterprise-genai-local"
readonly NAMESPACE="agent-platform"
readonly RELEASE="enterprise-genai"
readonly IMAGE="enterprise-genai-agent-platform:local"
readonly CHART="${PROJECT_ROOT}/infrastructure/helm/agent-platform"
readonly KIND_CONFIG="${PROJECT_ROOT}/infrastructure/kind/cluster.yaml"
readonly REPORT_DIR="${PROJECT_ROOT}/.security-reports"

for tool in docker kind kubectl helm curl jq; do
  if ! command -v "${tool}" >/dev/null 2>&1; then
    echo "required tool is unavailable: ${tool}" >&2
    exit 1
  fi
done

port_forward_pid=""
cleanup() {
  if [[ -n "${port_forward_pid}" ]]; then
    kill "${port_forward_pid}" >/dev/null 2>&1 || true
    wait "${port_forward_pid}" >/dev/null 2>&1 || true
  fi
  kind delete cluster --name "${CLUSTER_NAME}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

mkdir -p "${REPORT_DIR}"
kind create cluster --config "${KIND_CONFIG}" --wait 120s
kind load docker-image "${IMAGE}" --name "${CLUSTER_NAME}"

kubectl create namespace "${NAMESPACE}"
kubectl label namespace "${NAMESPACE}" \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/enforce-version=latest \
  pod-security.kubernetes.io/audit=restricted \
  pod-security.kubernetes.io/warn=restricted

helm upgrade --install "${RELEASE}" "${CHART}" \
  --namespace "${NAMESPACE}" \
  --values "${CHART}/values-kind.yaml" \
  --wait \
  --timeout 180s

kubectl rollout status deployment/"${RELEASE}"-gateway \
  --namespace "${NAMESPACE}" \
  --timeout 120s

kubectl get deployment "${RELEASE}"-gateway --namespace "${NAMESPACE}" -o json \
  >"${REPORT_DIR}/kind-deployment.json"
kubectl get networkpolicy --namespace "${NAMESPACE}" -o json \
  >"${REPORT_DIR}/kind-networkpolicies.json"

kubectl port-forward --namespace "${NAMESPACE}" service/"${RELEASE}"-gateway 18001:8000 \
  >"${REPORT_DIR}/kind-port-forward.log" 2>&1 &
port_forward_pid="$!"

for _ in {1..30}; do
  if curl --fail --silent http://127.0.0.1:18001/health/live >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

curl --fail --silent http://127.0.0.1:18001/health/live | jq -e '.status == "ok"'
curl --fail --silent http://127.0.0.1:18001/health/ready | jq -e '.status == "ready"'
curl --fail --silent http://127.0.0.1:18001/metrics \
  --output "${REPORT_DIR}/kind-metrics.prom"
grep -q '^agent_platform_http_requests_total' "${REPORT_DIR}/kind-metrics.prom"

jq -e '
  .spec.template.spec.automountServiceAccountToken == false and
  .spec.template.spec.securityContext.runAsNonRoot == true and
  .spec.template.spec.containers[0].securityContext.readOnlyRootFilesystem == true and
  .spec.template.spec.containers[0].securityContext.allowPrivilegeEscalation == false and
  .spec.template.spec.containers[0].securityContext.capabilities.drop == ["ALL"]
' "${REPORT_DIR}/kind-deployment.json" >/dev/null

echo "kind integration and Kubernetes security assertions passed"
