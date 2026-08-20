from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


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
