from __future__ import annotations

import datetime as dt
import math
import re
from pathlib import Path, PureWindowsPath
from typing import Iterator

from .config import Config
from .frontmatter import Document, dump, parse_document
from .locking import atomic_write, vault_lock
from .models import Lesson
from .retrieval import _days_since, oneline
from .snapshot import Snapshot

_DATE = "%Y-%m-%d"
_LOG_RE = re.compile(r"^## \[(\d{4}-\d{2}-\d{2})\] (.+)$")
_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f\x7f]')


class VaultNotInitialized(RuntimeError):
    pass


def _safe_filename(name: str) -> bool:
    # Apply Windows filename rules on every platform, including device aliases
    # (CON.md, COM1.md, etc.) and NTFS alternate data streams.
    return (
        bool(name)
        and not _UNSAFE_FILENAME.search(name)
        and not PureWindowsPath(name).is_reserved()
    )


def _as_tags(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [t.strip() for t in value.split(",") if t.strip()]
    if isinstance(value, list):
        return [str(t).strip() for t in value if str(t).strip()]
    return []


def _as_float(value, default: float) -> float:
    try:
        number = float(value)
        return number if math.isfinite(number) else default
    except (TypeError, ValueError, OverflowError):
        return default  # hand-edited frontmatter must not poison vault reads


def _as_int(value, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _as_bool(value, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ("false", "no", "0", "off")
    return bool(value)


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
        """Hold the re-entrant vault write lock for multi-step transactions
        (e.g. apply_proposal). Public write methods already lock internally."""
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
        document = self._read_document(path)
        return self._lesson_from_document(path, document) if document else None

    @staticmethod
    def _read_document(path: Path) -> Document | None:
        try:
            if not _safe_filename(path.name) or not path.is_file():
                return None
            with path.open("r", encoding="utf-8", newline="") as stream:
                return parse_document(stream.read())
        except (OSError, UnicodeError, ValueError):
            return None

    @staticmethod
    def _lesson_from_document(path: Path, document: Document) -> Lesson | None:
        meta, body = document.meta, document.body
        if not any(
            k in meta for k in ("case_id", "source_summary", "tags", "use_count", "created_at")
        ):
            return None  # frontmatter carries no lesson fields — not ours, skip
        return Lesson(
            lesson_id=path.stem,
            case_id=str(meta.get("case_id", path.stem)),
            source_summary=str(meta.get("source_summary", "")).strip(),
            content=body.strip("\r\n"),
            tags=_as_tags(meta.get("tags")),
            created_at=str(meta.get("created_at", "")),
            last_verified_at=str(meta.get("last_verified_at", "")),
            valid_until=str(meta.get("valid_until", "") or ""),
            confidence=max(0.0, min(1.0, _as_float(meta.get("confidence"), 0.8))),
            verified=_as_bool(meta.get("verified"), True),
            superseded_by=str(meta.get("superseded_by", "") or ""),
            use_count=max(0, _as_int(meta.get("use_count") or 0, 0)),
            path=path,
        )

    def broken_lessons(self) -> list[Path]:
        """Learnings/*.md files that carry a frontmatter block but do not parse
        into a lesson — likely hand-mangled metadata. Plain notes without
        frontmatter are not lessons and are not reported."""
        out: list[Path] = []
        if not self.learnings_dir.is_dir():
            return out
        for p in sorted(self.learnings_dir.glob("*.md")):
            document = self._read_document(p)
            if document is None:
                out.append(p)
                continue
            if (
                document.text.lstrip("\ufeff").startswith("---")
                and self._lesson_from_document(p, document) is None
            ):
                out.append(p)
        return out

    def get(self, lesson_id: str) -> Lesson | None:
        p = self._lesson_path(lesson_id)
        return self.load_lesson(p) if p is not None else None

    def _lesson_path(self, lesson_id: str) -> Path | None:
        filename = f"{lesson_id}.md"
        if not lesson_id or ".." in lesson_id or not _safe_filename(filename):
            return None
        return self.learnings_dir / filename

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

    def _prepare_metadata_update(
        self, lesson_id: str, updates: dict[str, str | int | bool],
    ) -> tuple[Lesson, str]:
        """Prepare a lossless field update; call while holding the write lock."""
        path = self._lesson_path(lesson_id)
        document = self._read_document(path) if path is not None else None
        lesson = self._lesson_from_document(path, document) if document else None
        if lesson is None:
            raise ValueError(f"Lesson not found: {lesson_id}")
        for key, value in updates.items():
            text = document.with_scalar(key, value)
            if text is None:
                raise ValueError(f"Cannot safely update {key} in {lesson_id}; review its YAML field by hand.")
            document = parse_document(text)
            if document.meta.get(key) != value:
                raise ValueError(f"Cannot safely update {key} in {lesson_id}; review its YAML field by hand.")
        updated = self._lesson_from_document(path, document)
        if updated is None:
            raise ValueError(f"Cannot safely update metadata in {lesson_id}.")
        return updated, document.text

    def next_lesson_id(self, case_id: str) -> str:
        prefix = f"{case_id}-lesson-"
        n = 0
        if self.learnings_dir.is_dir():
            rx = re.compile(rf"^{re.escape(prefix)}(\d+)$", re.IGNORECASE)
            for p in self.learnings_dir.glob("*.md"):  # glob metachars in case_id
                m = rx.match(p.stem)  # would silently miss files → id collision
                if m:
                    n = max(n, int(m.group(1)))
        candidate = f"{prefix}{n + 1:02d}"
        while (self.learnings_dir / f"{candidate}.md").exists():
            n += 1
            candidate = f"{prefix}{n + 1:02d}"
        return candidate

    def bump_use(self, lesson_ids: list[str]) -> None:
        self.read_and_bump(lesson_ids)

    def read_and_bump(self, lesson_ids: list[str]) -> list[Lesson]:
        """Read selected lessons once and atomically record active lesson use.

        Return the pre-increment objects, in first-requested order. Reading
        retired/expired lessons remains possible without reinforcing them.
        """
        if not lesson_ids:
            return []
        found: list[Lesson] = []
        with self.locked():
            for lesson_id in dict.fromkeys(lesson_ids):
                path = self._lesson_path(lesson_id)
                document = self._read_document(path) if path is not None else None
                lesson = self._lesson_from_document(path, document) if document else None
                if lesson is None:
                    continue
                found.append(lesson)
                expiry = _days_since(lesson.valid_until)
                if lesson.superseded_by or (expiry is not None and expiry >= 0):
                    continue
                updated = document.with_integer("use_count", lesson.use_count + 1)
                if updated is not None:
                    atomic_write(path, updated, newline="")
        return found

    def verify(self, lesson_ids: list[str]) -> tuple[list[str], list[str]]:
        """Stamp last_verified_at with today for the given lessons.

        Returns (verified_ids, missing_ids). Owner-facing remedy for the STALE
        finding lint reports; agents never call this.
        """
        today = dt.date.today().strftime(_DATE)
        verified: list[str] = []
        missing: list[str] = []
        with self.locked():
            prepared: list[tuple[Lesson, str]] = []
            for lesson_id in dict.fromkeys(lesson_ids):
                lesson = self.get(lesson_id)
                if lesson is None:
                    missing.append(lesson_id)
                    continue
                prepared.append(self._prepare_metadata_update(lesson_id, {"last_verified_at": today}))
            for lesson, text in prepared:
                atomic_write(lesson.path, text, newline="")
                self._append_log_locked("verify", lesson.lesson_id, lesson.tags)
                verified.append(lesson.lesson_id)
            if verified:
                self._rebuild_index_locked()
                self._snapshot_locked(f"verify: {len(verified)} lesson(s)")
        return verified, missing

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
            "| lesson | summary | tags | case | verified |",
            "|--------|---------|------|------|----------|",
        ]
        for l in sorted(lessons, key=lambda x: x.lesson_id):
            summary = oneline(l.source_summary, 120).replace("|", "/")
            if l.superseded_by:
                summary = f"{summary} (→ {l.superseded_by})"
            tags = ", ".join(l.tags).replace("|", "/") or "-"
            lines.append(
                f"| {l.lesson_id} | {summary} | {tags} | {l.case_id} "
                f"| {l.last_verified_at} |"
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
        for line in self.log_md.read_text(encoding="utf-8-sig").splitlines():
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
