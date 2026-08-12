"""Synthesize a cited answer from retrieved evidence via the owned model gateway.

Generation goes through `ModelGateway` (ADR-006), so the existing allowlist,
budget, PII (ADR-009) and content-safety (ADR-010) controls all apply to a
RAG answer exactly as they do to any other model-gateway call; nothing here
bypasses them.
"""

from enterprise_genai_platform.model_gateway import (
    ChatMessage,
    ModelGateway,
    ModelGenerationRequest,
)
from enterprise_genai_platform.rag.models import RetrievalResult

_INSTRUCTION = (
    "Answer the question using ONLY the evidence below. Cite every fact you "
    "use with its bracketed chunk id exactly as given, for example "
    "[POL-PAY-001#chunk-1]. If the evidence does not answer the question, "
    "say so explicitly instead of guessing."
)


def build_synthesis_prompt(query: str, evidence: RetrievalResult) -> str:
    """Build a prompt that only contains authorized, already-retrieved evidence."""
    evidence_block = "\n".join(f"[{hit.citation.chunk_id}] {hit.text}" for hit in evidence.hits)
    return f"{_INSTRUCTION}\n\nEvidence:\n{evidence_block}\n\nQuestion: {query}"


async def synthesize_grounded_answer(
    gateway: ModelGateway,
    *,
    model: str,
    query: str,
    evidence: RetrievalResult,
    tenant: str,
    agent: str = "rag-synthesis",
) -> str:
    """Return a cited answer, or a fixed refusal when no evidence was retrieved."""
    if not evidence.hits:
        return "No relevant evidence was found; unable to answer from authorised sources."
    request = ModelGenerationRequest(
        model=model,
        messages=(ChatMessage(role="user", content=build_synthesis_prompt(query, evidence)),),
        tenant=tenant,
        agent=agent,
    )
    result = await gateway.generate(request)
    return result.content
