.PHONY: bootstrap run format lint typecheck test evaluate reliability operator-demo operational-readiness portfolio-evidence portfolio-demo terraform-zero-plan preproduction-readiness audit secrets sast licenses lock-check check security container-security sign-image kind-integration durable-state-integration

PYTHON := .venv/bin/python
LOCAL_IMAGE := enterprise-genai-agent-platform:local
SECURITY_REPORTS := $(CURDIR)/.security-reports
TRIVY_IMAGE := aquasec/trivy:0.67.2
SEMGREP_IMAGE := semgrep/semgrep:1.172.0@sha256:65dcd4408adda7c183a6b4550cb1e9b19f7f627a6fbb7e0559bd466bedc44d7b
LICENSE_ALLOWLIST := 3-Clause BSD License;Apache Software License;Apache Software License; MIT License;Apache-2.0;Apache-2.0 AND BSD-2-Clause;Apache-2.0 OR BSD-2-Clause;Apache-2.0 OR BSD-3-Clause;Apache-2.0 OR MIT;BSD License;BSD-2-Clause;BSD-3-Clause;MIT;MIT License;MIT OR Apache-2.0;MIT-0;MIT No Attribution License (MIT-0);MPL-2.0 AND (Apache-2.0 OR MIT);Mozilla Public License 2.0 (MPL 2.0);PSF-2.0;Python Software Foundation License

bootstrap:
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install -e '.[dev]'
	.venv/bin/pre-commit install

run:
	.venv/bin/uvicorn enterprise_genai_platform.gateway.app:create_app --factory --reload

format:
	.venv/bin/ruff format .
	.venv/bin/ruff check --fix .

lint:
	.venv/bin/ruff check .
	.venv/bin/ruff format --check .

typecheck:
	.venv/bin/mypy src tests

test:
	$(PYTHON) -m pytest

evaluate:
	$(PYTHON) -m enterprise_genai_platform.evaluation.runner

reliability:
	$(PYTHON) scripts/load-failure-test.py

operator-demo:
	$(PYTHON) scripts/operator-demo.py

operational-readiness:
	$(PYTHON) scripts/operational-readiness.py

portfolio-evidence:
	$(PYTHON) scripts/portfolio-evidence.py

portfolio-demo: evaluate reliability operator-demo operational-readiness portfolio-evidence

terraform-zero-plan:
	./scripts/terraform-plan-zero.sh

preproduction-readiness: terraform-zero-plan
	$(PYTHON) scripts/preproduction-readiness.py

audit:
	.venv/bin/pip-audit --cache-dir .security-reports/pip-audit-cache
	.venv/bin/bandit -r src agents mcp platform rag scripts -c pyproject.toml

secrets:  # pragma: allowlist secret
	git ls-files -co --exclude-standard -z | xargs -0 .venv/bin/detect-secrets-hook # pragma: allowlist secret

sast:
	docker run --rm --volume $(CURDIR):/src:ro --workdir /src $(SEMGREP_IMAGE) semgrep scan --config .semgrep.yml --error --metrics off

licenses:
	mkdir -p $(SECURITY_REPORTS)
	.venv/bin/pip-licenses --with-system --format=json --output-file=$(SECURITY_REPORTS)/python-licenses.json --allow-only='$(LICENSE_ALLOWLIST)'

lock-check:
	UV_CACHE_DIR=$(SECURITY_REPORTS)/uv-cache .venv/bin/uv lock --check
	$(PYTHON) -m pip check

check: lint typecheck test

security: check evaluate reliability operator-demo operational-readiness portfolio-evidence audit secrets lock-check licenses sast

container-security:
	mkdir -p $(SECURITY_REPORTS)
	docker build --provenance=false --target runtime --tag $(LOCAL_IMAGE) .
	docker save --output $(SECURITY_REPORTS)/enterprise-genai-agent-platform.tar $(LOCAL_IMAGE)
	docker run --rm --volume $(SECURITY_REPORTS):/reports $(TRIVY_IMAGE) image --sbom-sources= --input /reports/enterprise-genai-agent-platform.tar --format cyclonedx --output /reports/enterprise-genai-agent-platform.cdx.json --skip-version-check
	docker run --rm --volume $(SECURITY_REPORTS):/reports $(TRIVY_IMAGE) image --db-repository ghcr.io/aquasecurity/trivy-db:2 --sbom-sources= --input /reports/enterprise-genai-agent-platform.tar --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --format json --output /reports/container-vulnerabilities.json --exit-code 1 --skip-version-check

sign-image: container-security
	./scripts/sign-local-image.sh

kind-integration: sign-image
	./scripts/kind-integration.sh

durable-state-integration: check
	./scripts/durable-state-integration.sh
