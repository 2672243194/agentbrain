from __future__ import annotations

import re

# High-entropy credential shapes. Each pattern is anchored on format, not
# context, so ordinary prose never trips them.
_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("OpenAI-style key (sk-…)", re.compile(r"\bsk-[A-Za-z0-9_\-]{16,}\b")),
    ("Anthropic key (sk-ant-…)", re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{16,}\b")),
    ("GitHub token (ghp_/gho_/ghu_…)", re.compile(r"\bgh[posu]_[A-Za-z0-9]{20,}\b")),
    ("AWS access key id (AKIA…)", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("AWS secret key (40-char base64)", re.compile(r"\b[A-Za-z0-9/+=]{40}\b")),
    ("Slack token (xox…)", re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b")),
    ("Google API key (AIza…)", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("PyPI token", re.compile(r"\bpypi-[A-Za-z0-9_\-]{20,}\b")),
    ("Bearer header", re.compile(r"\bBearer\s+[A-Za-z0-9_\-\.=/+]{20,}", re.IGNORECASE)),
    ("Private key block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("Generic key=value assignment", re.compile(
        r"\b(?:password|passwd|pwd|api[_-]?key|apikey|secret|token|access[_-]?key)"
        r"\s*[=:]\s*['\"]?[^\s'\"]{8,}",
        re.IGNORECASE,
    )),
]

# Obviously-safe stand-ins that must never be flagged.
_PLACEHOLDERS = [
    re.compile(r"\$\{ENV:[A-Z0-9_]+\}"),
    re.compile(r"\$\{env:[A-Za-z0-9_]+\}"),
    re.compile(r"\b(?:sk-xxx+|your[_-]?(?:api[_-]?)?key|xxx+|placeholder|changeme|redacted|<[^>]+>)\b", re.IGNORECASE),
]

_WHITELIST_HINT = (
    "Replace the value with an env-var reference, e.g. ${ENV:VAR_NAME}."
)


def scan(text: str) -> list[tuple[str, str]]:
    """Return [(kind, matched_text)] for credential-looking substrings.

    Placeholder forms (${ENV:VAR}, sk-xxx, <your-key>, …) are exempt: teaching
    examples and references must ingest fine.
    """
    if not text:
        return []
    hits: list[tuple[str, str]] = []
    exempt_spans: list[tuple[int, int]] = []
    for rx in _PLACEHOLDERS:
        for m in rx.finditer(text):
            exempt_spans.append(m.span())
    for kind, rx in _PATTERNS:
        for m in rx.finditer(text):
            s, e = m.span()
            if any(s < we and ws < e for ws, we in exempt_spans):
                continue
            snippet = m.group(0)
            snippet = snippet[:12] + "…" if len(snippet) > 12 else snippet
            hits.append((kind, snippet))
    return hits


def redaction_hint(hits: list[tuple[str, str]]) -> str:
    kinds = ", ".join(sorted({k for k, _ in hits}))
    return f"Refused: credential-looking content detected ({kinds}). {_WHITELIST_HINT}"
