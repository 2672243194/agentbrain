from __future__ import annotations

import datetime as dt
import re
from pathlib import Path
from typing import Iterator

from .config import Config
from .frontmatter import dump, parse
from .locking import atomic_write, vault_lock
from .models import Lesson
from .snapshot import Snapshot

_DATE = "%Y-%m-%d"
_LOG_RE = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\] (.+)$")


class VaultNotInitialized(RuntimeError):
    pass


def _as_tags(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    return []


class Vault:
    def __init__(self, root: Path | str):
        self.root = Path(root).expanduser().resolve()
        self.case_dir = self.root / "Case-Learnings"
        self.index_md = self.case_dir / "Index.md"
        self.log_md = self.case_dir / "log.md"
        self.learnings_dir = self.case_dir / "Learnings"
        self.consolidations_dir = self.case_dir / "_consolidations"

    @classmethod
    def open(cls, cfg: Config | None = None, root: Path | str | None = None) -> "Vault":
        vault = cls(root if root is not None else (cfg or Config.load()).vault_dir)
        if not vault.is_initialized():
            raise VaultNotInitialized(
                f"agentbrain vault not found at '{vault.root}'. "
                f"Run: agentbrain init \"{vault.root}\" (or set AGENTBRAIN_VAULT)."
            )
        return vault

    def is_initialized(self) -> bool:
        return self.learnings_dir.is_dir()

    def relpath(self, path: Path) -> str:
        try:
            return Path(path).resolve().relative_to(self.root).as_posix()
        except ValueError:
            return str(path)

    def locked(self) -> "Iterator[None]":
        """Hold the vault write lock; nest via re-entrancy is NOT supported —
        public write methods already lock internally, use this only to wrap
        multi-step transactions (e.g. apply_proposal)."""
        return vault_lock(self.root)

    def _snapshot_locked(self, message: str) -> None:
        """Best-effort git snapshot; call only while holding the write lock.
        Query-driven use_count bumps are deliberately not snapshotted — they
        ride along with the next content commit."""
        Snapshot(self.root).commit(message)

    # --- lessons ---

    def lessons(self, include_superseded: bool = False) -> list[Lesson]:
        out: list[Lesson] = []
        if not self.learnings_dir.is_dir():
            return out
        for p in sorted(self.learnings_dir.glob("*.md")):
            lesson = self.load_lesson(p)
            if lesson is None:
                continue
            if lesson.superseded_by and not include_superseded:
                continue
            out.append(lesson)
        return out

    def load_lesson(self, path: Path) -> Lesson | None:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            return None
        if not text.startswith("---"):
            return None  # not a lesson (e.g. a stray README.md)
        meta, body = parse(text)
        if not any(
            k in meta for k in ("case_id", "source_summary", "tags", "use_count", "created_at")
        ):
            return None  # frontmatter carries no lesson fields — not ours, skip
        return Lesson(
            lesson_id=path.stem,
            case_id=str(meta.get("case_id", path.stem)),
            source_summary=str(meta.get("source_summary", "")).strip(),
            content=body.strip(),
            tags=_as_tags(meta.get("tags")),
            created_at=str(meta.get("created_at", "")),
            last_verified_at=str(meta.get("last_verified_at", "")),
            valid_until=str(meta.get("valid_until", "") or ""),
            confidence=float(meta.get("confidence") if meta.get("confidence") is not None else 0.8),
            verified=bool(meta.get("verified", True)),
            superseded_by=str(meta.get("superseded_by", "") or ""),
            use_count=int(meta.get("use_count") or 0),
            path=path,
        )

    def get(self, lesson_id: str) -> Lesson | None:
        p = self.learnings_dir / f"{lesson_id}.md"
        return self.load_lesson(p) if p.is_file() else None

    def save(self, lesson: Lesson, action: str | None = None) -> None:
        with self.locked():
            self._save_locked(lesson, action, rebuild=True)
            self._snapshot_locked(f"{action or 'save'}: {lesson.lesson_id}")

    def _save_locked(
        self, lesson: Lesson, action: str | None = None, rebuild: bool = True
    ) -> None:
        meta = {
            "case_id": lesson.case_id,
            "tags": lesson.tags,
            "source_summary": lesson.source_summary,
            "created_at": lesson.created_at,
            "last_verified_at": lesson.last_verified_at,
            "valid_until": lesson.valid_until,
            "confidence": lesson.confidence,
            "verified": lesson.verified,
            "superseded_by": lesson.superseded_by,
            "use_count": lesson.use_count,
        }
        lesson.path = lesson.path or self.learnings_dir / f"{lesson.lesson_id}.md"
        lesson.path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(lesson.path, dump(meta, lesson.content))
        if action:
            self._append_log_locked(action, lesson.lesson_id, lesson.tags)
        if rebuild:
            self._rebuild_index_locked()

    def new_lesson(
        self,
        case_id: str,
        source_summary: str,
        content: str,
        tags: list[str],
        confidence: float = 0.8,
    ) -> Lesson:
        today = dt.date.today().strftime(_DATE)
        lesson_id = self.next_lesson_id(case_id)
        return Lesson(
            lesson_id=lesson_id,
            case_id=case_id,
            source_summary=source_summary,
            content=content,
            tags=list(tags),
            created_at=today,
            last_verified_at=today,
            confidence=confidence,
            path=self.learnings_dir / f"{lesson_id}.md",
        )

    def next_lesson_id(self, case_id: str) -> str:
        prefix = f"{case_id}-lesson-"
        n = 0
        if self.learnings_dir.is_dir():
            rx = re.compile(rf"^{re.escape(prefix)}(\d+)$")
            for p in self.learnings_dir.glob("*.md"):  # glob metachars in case_id
                m = rx.match(p.stem)  # would silently miss files → id collision
                if m:
                    n = max(n, int(m.group(1)))
        return f"{prefix}{n + 1:02d}"

    def bump_use(self, lesson_ids: list[str]) -> None:
        if not lesson_ids:
            return
        with self.locked():
            for lesson_id in lesson_ids:
                lesson = self.get(lesson_id)
                if lesson is None:
                    continue
                lesson.use_count += 1
                self._save_locked(lesson, rebuild=False)
            self._rebuild_index_locked()

    # --- index ---

    def rebuild_index(self, lessons: list[Lesson] | None = None) -> None:
        with self.locked():
            self._rebuild_index_locked(lessons)
            self._snapshot_locked("index: rebuild")

    def _rebuild_index_locked(self, lessons: list[Lesson] | None = None) -> None:
        lessons = lessons if lessons is not None else self.lessons(include_superseded=True)
        lines = [
            "# Case-Learnings Index",
            "",
            "> Auto-generated by `agentbrain`. Do not edit by hand.",
            "",
            "| lesson | summary | tags | case | verified | used |",
            "|--------|---------|------|------|----------|------|",
        ]
        for l in sorted(lessons, key=lambda x: x.lesson_id):
            summary = l.source_summary.replace("|", "/")
            if l.superseded_by:
                summary = f"{summary} (→ {l.superseded_by})"
            tags = ", ".join(l.tags).replace("|", "/") or "-"
            lines.append(
                f"| {l.lesson_id} | {summary} | {tags} | {l.case_id} "
                f"| {l.last_verified_at} | {l.use_count} |"
            )
        self.index_md.parent.mkdir(parents=True, exist_ok=True)
        atomic_write(self.index_md, "\n".join(lines) + "\n")

    # --- log ---

    def append_log(self, action: str, obj: str, tags: list[str] | None = None) -> None:
        with self.locked():
            self._append_log_locked(action, obj, tags)

    def _append_log_locked(self, action: str, obj: str, tags: list[str] | None = None) -> None:
        today = dt.date.today().strftime(_DATE)
        tag_s = f" | tags:{','.join(tags)}" if tags else ""
        self.log_md.parent.mkdir(parents=True, exist_ok=True)
        with self.log_md.open("a", encoding="utf-8") as f:
            f.write(f"## [{today}] {action} | {obj}{tag_s}\n")

    def log_entries(self) -> list[dict]:
        entries: list[dict] = []
        if not self.log_md.is_file():
            return entries
        for line in self.log_md.read_text(encoding="utf-8").splitlines():
            m = _LOG_RE.match(line.strip())
            if not m:
                continue
            date, rest = m.groups()
            parts = [p.strip() for p in rest.split("|")]
            tags: list[str] = []
            if len(parts) > 2 and parts[2].startswith("tags:"):
                tags = [t for t in parts[2][5:].split(",") if t]
            entries.append(
                {
                    "date": date,
                    "action": parts[0],
                    "object": parts[1] if len(parts) > 1 else "",
                    "tags": tags,
                }
            )
        return entries
