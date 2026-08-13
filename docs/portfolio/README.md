# Portfolio evidence pack

## Project statement

The Enterprise GenAI Agent Platform is a secure, reusable paved road for teams to
build and operate governed AI agents. Its NovaBank Operations Copilot reference
implementation demonstrates bounded LangGraph orchestration, specialist agents,
MCP tool policy, authorised RAG, human approval, durable state, observability,
evaluation and secure delivery controls.

The implementation and all executable evidence run locally. Azure architecture and
Terraform are validate-only: this project has not created or claimed operation of
Azure resources.

## Reviewer path

1. Read the [architecture diagrams](architecture-diagrams.md).
2. Use the [role evidence matrix](evidence-matrix.md) to trace claims to code,
   tests, security controls and generated evidence.
3. Run the [operator demonstration](demo-guide.md).
4. Review the [limitations and production gates](limitations.md).

## One-minute summary

- **Problem:** teams otherwise duplicate agent architecture, security, RAG,
  deployment, observability and governance.
- **Platform:** a Python/FastAPI gateway and LangGraph supervisor route requests to
  allowlisted specialists through a governed MCP boundary.
- **Security:** deny-by-default RBAC and tool policy, metadata-only auditing,
  data-minimising state, prompt-injection controls, security scanning and signed
  local container evidence.
- **Operations:** SLO alerts, metrics and traces, recovery exercises, bounded
  retries, performance regression gates and incident runbooks.
- **Delivery:** Docker, Helm, ephemeral kind, Terraform validation and non-deploying
  GitHub Actions demonstrate the path without creating cloud resources.

## Reproduce the evidence

```bash
make check
make evaluate
make reliability
make operator-demo
make operational-readiness
make portfolio-evidence
```

With Docker Desktop running, `make sign-image` and `make kind-integration` extend
the evidence through image scanning, SBOM generation, offline signing and an
ephemeral Kubernetes deployment. These commands do not push an image or contact
Azure.
