from __future__ import annotations

from dataclasses import dataclass, field
import datetime as dt
import hashlib
import json
from pathlib import Path


def _canonical(value, root: dict, stack: tuple[int, ...] = ()):
    """Deterministic, typed encoding of safe YAML, including sets and aliases."""
    if isinstance(value, (dict, list, tuple, set)):
        identity = id(value)
        if identity in stack:
            return ["ref", stack.index(identity)]
        children = (*stack, identity)
        if isinstance(value, dict):
            pairs = [(_canonical(k, root, children), v) for k, v in value.items()
                     if value is not root or k not in ("use_count", "last_verified_at")]
            pairs.sort(key=lambda pair: json.dumps(pair[0], ensure_ascii=True))
            return ["map", [[k, _canonical(v, root, children)] for k, v in pairs]]
        items = [_canonical(v, root, children) for v in value]
        if isinstance(value, set):
            items.sort(key=lambda item: json.dumps(item, ensure_ascii=True))
        return [type(value).__name__, items]
    if isinstance(value, bytes):
        return ["bytes", value.hex()]
    if isinstance(value, (dt.datetime, dt.date)):
        return [type(value).__name__, value.isoformat()]
    if isinstance(value, float):
        return ["float", value.hex()]
    return [type(value).__name__, value]


@dataclass
class Lesson:
    lesson_id: str
    case_id: str
    source_summary: str
    content: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: str = ""
    last_verified_at: str = ""
    valid_until: str = ""
    confidence: float = 0.8
    verified: bool = True
    superseded_by: str = ""
    use_count: int = 0
    path: Path | None = None
    _source_meta: dict | None = field(default=None, repr=False, compare=False)

    @property
    def version(self) -> str:
        """Fingerprint content/conditions, excluding read and verification telemetry.

        Computed only for full reads/feedback, never during index ranking. Keep
        custom frontmatter in the fingerprint without rewriting the source.
        """
        meta = self._source_meta if self._source_meta is not None else {
            "case_id": self.case_id, "source_summary": self.source_summary,
            "tags": self.tags, "created_at": self.created_at,
            "valid_until": self.valid_until, "confidence": self.confidence,
            "verified": self.verified, "superseded_by": self.superseded_by,
        }
        content = self.content.replace("\r\n", "\n")
        # Keep Markdown indentation, and normalize metadata deterministically
        # across Python processes/hash seeds, including mixed-type YAML sets.
        try:
            payload = json.dumps([_canonical(meta, meta), content], ensure_ascii=True,
                                 separators=(",", ":"))
        except (RecursionError, TypeError, ValueError):
            # Extremely deep/unsupported hand-written metadata must not break
            # normal reads; feedback cannot claim a version for this content.
            return ""
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
