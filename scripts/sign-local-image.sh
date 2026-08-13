#!/usr/bin/env bash
set -euo pipefail

readonly PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly REPORT_DIR="${PROJECT_ROOT}/.security-reports"
readonly IMAGE_ARCHIVE="${REPORT_DIR}/enterprise-genai-agent-platform.tar"
readonly PUBLIC_KEY="${REPORT_DIR}/enterprise-genai-agent-platform.pub"
readonly SIGNATURE="${REPORT_DIR}/enterprise-genai-agent-platform.sig"
readonly COSIGN_IMAGE="gcr.io/projectsigstore/cosign@sha256:68839b7f13dac5a6744a5d8818e984dd39183374e37855c19e14d623d9bc9037"

for tool in docker openssl; do
  command -v "${tool}" >/dev/null 2>&1 || {
    echo "required tool is unavailable: ${tool}" >&2
    exit 1
  }
done

if [[ ! -s "${IMAGE_ARCHIVE}" ]]; then
  echo "missing image archive; run 'make container-security' first" >&2
  exit 1
fi

signing_workspace="$(mktemp -d "${REPORT_DIR}/cosign-signing.XXXXXX")"
readonly signing_workspace_name="$(basename "${signing_workspace}")"
cleanup() {
  rm -rf "${signing_workspace}"
}
trap cleanup EXIT

export COSIGN_PASSWORD
COSIGN_PASSWORD="$(openssl rand -hex 32)"

readonly cosign_run=(
  docker run --rm --network none
  --user "$(id -u):$(id -g)"
  --env COSIGN_PASSWORD
  --volume "${REPORT_DIR}:/reports"
  "${COSIGN_IMAGE}"
)

"${cosign_run[@]}" generate-key-pair \
  --output-key-prefix "/reports/${signing_workspace_name}/cosign"
cp "${signing_workspace}/cosign.pub" "${PUBLIC_KEY}"
"${cosign_run[@]}" sign-blob \
  --yes \
  --tlog-upload=false \
  --key "/reports/${signing_workspace_name}/cosign.key" \
  --output-signature "/reports/$(basename "${SIGNATURE}")" \
  "/reports/$(basename "${IMAGE_ARCHIVE}")"
"${cosign_run[@]}" verify-blob \
  --key "/reports/$(basename "${PUBLIC_KEY}")" \
  --signature "/reports/$(basename "${SIGNATURE}")" \
  --insecure-ignore-tlog=true \
  "/reports/$(basename "${IMAGE_ARCHIVE}")"

echo "Local image archive signature verified. Ephemeral private key destroyed."
