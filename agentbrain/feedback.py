"""Append-only, task-deduplicated outcome reports; no lesson reinforcement."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
from typing import TYPE_CHECKING

from .frontmatter import dump, parse_document
from .locking import atomic_write
from .redact import redaction_hint, scan

if TYPE_CHECKING:
    from .vault import Vault

OUTCOMES = ("helpful", "partial", "ineffective", "not_applicable", "unverified")
_VERSION = re.compile(r"[0-9a-f]{64}\Z")
_FIELDS = {"lesson_id", "lesson_version", "outcome", "environment", "evidence"}
_MAX_FILE_BYTES = 65536


@dataclass
class FeedbackEntry:
    # Let the API reject unknown fields without SDK validation echoing their
    # potentially sensitive values; all content validation happens below.
    __pydantic_config__ = {"extra": "allow"}
    lesson_id: str
    lesson_version: str
    outcome: str
    environment: str
    evidence: str


def _text(value, field: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{field} must be nonempty text of at most {limit} characters.")
    if any(ord(c) < 32 or ord(c) == 127 or c in "\u0085\u2028\u2029" for c in value):
        raise ValueError(f"{field} must be a single line without control characters.")
    return value.strip()


def _entries(values) -> list[dict[str, str]]:
    if not isinstance(values, list) or not 1 <= len(values) <= 10:
        raise ValueError("feedback requires 1-10 entries per batch.")
    clean = []
    for value in values:
        if isinstance(value, FeedbackEntry):
            value = vars(value)
        if not isinstance(value, dict) or set(value) != _FIELDS:
            raise ValueError("each entry requires lesson_id, lesson_version, outcome, environment and evidence only.")
        entry = {k: _text(value[k], k, limit) for k, limit in (
            ("lesson_id", 200), ("lesson_version", 64), ("outcome", 20),
            ("environment", 240), ("evidence", 320),
        )}
        if not _VERSION.fullmatch(entry["lesson_version"]):
            raise ValueError("lesson_version must be the 64-character version returned by a full read.")
        if entry["outcome"] not in OUTCOMES:
            raise ValueError("outcome must be " + ", ".join(OUTCOMES) + ".")
        clean.append(entry)
    return clean


def _key(entry: dict[str, str]) -> tuple[str, str]:
    # Match the host filesystem's lesson-ID semantics (case aliases on Windows).
    return os.path.normcase(entry["lesson_id"]), entry["lesson_version"]


def _canonical(entry: dict[str, str]) -> dict[str, str]:
    return dict(entry, lesson_id=os.path.normcase(entry["lesson_id"]))


def _task_hash(task_id: str) -> str:
    # 128-bit locator plus the full stored task ID avoids Windows MAX_PATH
    # overflow once the atomic-write temporary suffix is added.
    return hashlib.sha256(task_id.encode("utf-8")).hexdigest()[:32]


def _directory(vault: Vault) -> Path:
    directory = vault.case_dir / "_feedback"
    # A symlink/junction must not redirect writes into lessons or owner rules.
    if directory.resolve() != directory.absolute() or (directory.exists() and not directory.is_dir()):
        raise ValueError("feedback directory is not a regular directory inside the Vault.")
    return directory


def _load(path: Path) -> tuple[str, list[dict[str, str]]]:
    if path.is_symlink() or path.resolve() != path.absolute() or path.stat().st_size > _MAX_FILE_BYTES:
        raise ValueError("unsafe feedback file")
    meta = parse_document(path.read_text(encoding="utf-8-sig")).meta
    if meta.get("kind") != "agentbrain-feedback" or meta.get("schema") != 1:
        raise ValueError("invalid feedback schema")
    task = _text(meta.get("task_id"), "task_id", 128)
    if not path.name.startswith(_task_hash(task) + "-"):
        raise ValueError("feedback task identity does not match its filename")
    return task, _entries(meta.get("entries"))


def record(vault: Vault, task_id: str, entries: list[dict] | list[FeedbackEntry]) -> str:
    if not vault.is_initialized():
        raise ValueError("Vault not initialized; run agentbrain init before reporting feedback.")
    task_id = _text(task_id, "task_id", 128)
    clean = _entries(entries)
    hits = scan(task_id)
    for entry in clean:
        for value in entry.values():
            hits.extend(scan(value))
    if hits:
        return redaction_hint(hits)
    # Never derive paths from any submitted ID, even the opaque task identifier.
    pending: dict[tuple[str, str], dict[str, str]] = {}
    for entry in clean:
        if vault._lesson_path(entry["lesson_id"]) is None:
            raise ValueError("invalid lesson_id; use the ID returned by memory_read.")
        key = _key(entry)
        if key in pending and _canonical(pending[key]) != _canonical(entry):
            raise ValueError("conflicting feedback for the same task, lesson and version.")
        pending[key] = entry

    directory = _directory(vault)
    with vault.locked():
        directory = _directory(vault)
        existing: dict[tuple[str, str], dict[str, str]] = {}
        for path in sorted(directory.glob(_task_hash(task_id) + "-*.md")):
            try:
                stored_task, stored_entries = _load(path)
            except (OSError, UnicodeError, ValueError, RecursionError):
                raise ValueError("existing feedback for this task is unreadable; owner review required.") from None
            if stored_task != task_id:
                raise ValueError("feedback task identity conflict; owner review required.")
            for entry in stored_entries:
                key = _key(entry)
                if key in existing and _canonical(existing[key]) != _canonical(entry):
                    raise ValueError("existing feedback has conflicting reports; owner review required.")
                existing[key] = entry

        fresh = []
        for key, entry in pending.items():
            if key in existing:
                if _canonical(existing[key]) != _canonical(entry):
                    raise ValueError("conflicting feedback already exists for this task, lesson and version.")
                continue  # Exact retries still succeed if the source later changed.
            lesson = vault.get(entry["lesson_id"])
            if lesson is None:
                raise ValueError("lesson not found; read the intended lesson before reporting feedback.")
            if lesson.version != entry["lesson_version"]:
                raise ValueError("lesson version changed; re-read and assess it before submitting new feedback.")
            fresh.append(entry)

        skipped = len(clean) - len(fresh)
        if not fresh:
            return f"Feedback recorded: 0; skipped: {skipped} (already recorded)."
        payload = json.dumps(sorted(fresh, key=_key), sort_keys=True, ensure_ascii=False)
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]
        path = directory / f"{_task_hash(task_id)}-{digest}.md"
        if path.exists() or path.is_symlink():
            raise ValueError("feedback destination already exists; owner review required.")
        text = dump({
            "kind": "agentbrain-feedback", "schema": 1, "task_id": task_id,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
            "entries": fresh,
        }, "# Memory feedback\n\nReported outcomes, not independently verified facts.\n"
           "No lesson, confidence or retrieval weight is changed by this report.")
        # One atomic Markdown write per batch: validation/conflict failures can
        # never leave a partially recorded batch. No log/index/snapshot churn.
        directory.mkdir(parents=True, exist_ok=True)
        atomic_write(path, text, newline="\n")
        return f"Feedback recorded: {len(fresh)}; skipped: {skipped}."


def summary(vault: Vault) -> list[str]:
    """Read-only totals, deduplicated even if files have been copied by hand."""
    records: dict[tuple[str, str, str], dict[str, str]] = {}
    conflicts = set()
    invalid = 0
    try:
        directory = _directory(vault)
        for path in sorted(directory.glob("*.md")):
            try:
                task, entries = _load(path)
            except (OSError, UnicodeError, ValueError, RecursionError):
                invalid += 1
                continue
            for entry in entries:
                key = (task, *_key(entry))
                if key in records and _canonical(records[key]) != _canonical(entry):
                    conflicts.add(key)
                records[key] = entry
    except (OSError, ValueError):
        invalid += 1
    counts = Counter(entry["outcome"] for key, entry in records.items() if key not in conflicts)
    lines = ["Feedback reports (all recorded versions; self-reported):",
             "- " + " · ".join(f"{name}: {counts[name]}" for name in OUTCOMES),
             "No feedback is not evidence of ineffectiveness; reports do not change ranking."]
    if invalid or conflicts:
        lines.append(f"Ignored unreadable feedback files: {invalid}; conflicting reports: {len(conflicts)}.")
    return lines
