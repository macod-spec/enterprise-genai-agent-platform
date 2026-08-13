"""Strict document parsing and indirect-prompt-injection rejection."""

import hashlib
import re
import unicodedata

from enterprise_genai_platform.rag.models import KnowledgeDocument

_MAX_DOCUMENT_BYTES = 50_000
_REQUIRED_HEADERS = {"id", "title", "version", "classification", "allowed_roles"}
_INJECTION_PATTERNS = (
    re.compile(r"ignore (all |any )?(previous|prior) instructions", re.IGNORECASE),
    re.compile(r"reveal (the )?(system|developer) prompt", re.IGNORECASE),
    re.compile(r"\b(system|assistant|developer)\s*:", re.IGNORECASE),
    re.compile(r"<\s*(script|iframe|object)\b", re.IGNORECASE),
    re.compile(r"\b(call|invoke|execute)\s+(the\s+)?tool\b", re.IGNORECASE),
)


class UnsafeKnowledgeDocument(ValueError):
    """Raised when untrusted knowledge content violates ingestion policy."""


def parse_policy_document(raw: bytes, *, source_name: str) -> KnowledgeDocument:
    """Parse a constrained Markdown document and preserve content provenance."""
    if len(raw) > _MAX_DOCUMENT_BYTES:
        raise UnsafeKnowledgeDocument("Document exceeds the ingestion size limit")
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsafeKnowledgeDocument("Document must be valid UTF-8") from exc
    normalized = unicodedata.normalize("NFKC", decoded)
    if any(unicodedata.category(char) == "Cc" and char not in "\n\t\r" for char in normalized):
        raise UnsafeKnowledgeDocument("Document contains disallowed control characters")
    headers, content = _split_document(normalized)
    missing = _REQUIRED_HEADERS - headers.keys()
    unknown = headers.keys() - _REQUIRED_HEADERS
    if missing or unknown:
        raise UnsafeKnowledgeDocument("Document metadata schema is invalid")
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(content):
            raise UnsafeKnowledgeDocument("Document contains a prohibited instruction pattern")
    roles = frozenset(role.strip() for role in headers["allowed_roles"].split(",") if role.strip())
    if not roles:
        raise UnsafeKnowledgeDocument("Document must declare at least one allowed role")
    if not source_name.endswith(".md"):
        raise UnsafeKnowledgeDocument("Only Markdown policy documents are accepted")
    return KnowledgeDocument(
        document_id=headers["id"],
        title=headers["title"],
        version=headers["version"],
        classification=headers["classification"],  # type: ignore[arg-type]
        allowed_roles=roles,
        content=content,
        provenance_sha256=hashlib.sha256(raw).hexdigest(),
    )


def _split_document(document: str) -> tuple[dict[str, str], str]:
    lines = document.splitlines()
    if len(lines) < 8 or lines[0] != "---":
        raise UnsafeKnowledgeDocument("Document must start with metadata front matter")
    try:
        closing = lines.index("---", 1)
    except ValueError as exc:
        raise UnsafeKnowledgeDocument("Document metadata is not terminated") from exc
    headers: dict[str, str] = {}
    for line in lines[1:closing]:
        key, separator, value = line.partition(":")
        if not separator or not key.strip() or not value.strip() or key.strip() in headers:
            raise UnsafeKnowledgeDocument("Document metadata contains an invalid field")
        headers[key.strip()] = value.strip()
    content = "\n".join(lines[closing + 1 :]).strip()
    if len(content) < 20:
        raise UnsafeKnowledgeDocument("Document content is too short")
    return headers, content
