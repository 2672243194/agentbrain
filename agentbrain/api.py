from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from pathlib import Path

from .config import Config
from .locking import atomic_write
from .models import Lesson
from .profile import Profile
from .retrieval import _days_since, search_lessons, tokenize
from .vault import Vault, VaultNotInitialized

_SUMMARY_CHARS = 160
_UNSAFE_CASE = re.compile(r'[\\/:*?"<>|\s]+')


def _open_vault(vault: Vault | None) -> Vault:
    return vault if vault is not None else Vault.open(Config.load())


def _oneline(text: str, n: int) -> str:
    s = " ".join((text or "").split())
    return s[: n - 1] + "…" if len(s) > n else s


def _clean_case_id(case_id: str) -> str:
    cid = _UNSAFE_CASE.sub("-", (case_id or "").strip())
    return cid or "misc"


def _normalize_tags(tags) -> list[str]:
    if tags is None:
        return []
    if isinstance(tags, str):
        tags = tags.split(",")
    out: list[str] = []
    for t in tags:
        t = str(t).strip().strip("#")
        if t and t not in out:
            out.append(t)
    return out[:8]


def _stamp() -> str:
    return dt.datetime.now().strftime("%Y%m%d-%H%M%S")


def _next_proposal_path(v: Vault, kind: str) -> Path:
    v.consolidations_dir.mkdir(parents=True, exist_ok=True)
    stamp = _stamp()
    path = v.consolidations_dir / f"{kind}-{stamp}.md"
    n = 2
    while path.exists():  # same-second runs must not clobber each other
        path = v.consolidations_dir / f"{kind}-{stamp}-{n}.md"
        n += 1
    return path


def _jaccard(a: set, b: set) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


_QUERY_MODES = ("index", "full")


def memory_query(
    query: str,
    top_k: int = 5,
    mode: str = "index",
    vault: Vault | None = None,
) -> str:
    try:
        v = _open_vault(vault)
    except VaultNotInitialized as e:
        return str(e)

    if mode not in _QUERY_MODES:
        mode = "index"
    ranked = search_lessons(v.lessons(), query)
    hits = ranked[: max(1, top_k)]
    if not hits:
        return (
            "No lessons matched. If this task produces a reusable lesson, "
            "call memory_ingest when done."
        )

    lines = [f"{len(hits)} lesson(s) matched (mode={mode}):", ""]
    for rank, (l, _score) in enumerate(hits, 1):
        lines.append(
            f"{rank}. [{l.lesson_id}] {l.source_summary} "
            f"(conf {l.confidence} · used {l.use_count} · {l.last_verified_at})"
        )
        lines.append(f"   tags: {', '.join(l.tags) or '-'}")
        lines.append(f"   path: {v.relpath(l.path)}")
        lines.append(f"   gist: {_oneline(l.content, _SUMMARY_CHARS)}")
        if mode == "full":
            lines.extend(["", l.content.strip(), ""])
    v.bump_use([l.lesson_id for l, _ in hits])
    return "\n".join(lines)


def memory_ingest(
    case_id: str,
    lesson: str,
    tags: list[str] | None = None,
    confidence: float = 0.8,
    source_summary: str | None = None,
    vault: Vault | None = None,
) -> str:
    try:
        v = _open_vault(vault)
    except VaultNotInitialized as e:
        return str(e)
    if not lesson or not lesson.strip():
        return "Refused: empty lesson."

    tags = _normalize_tags(tags)
    case_id = _clean_case_id(case_id)
    confidence = min(1.0, max(0.0, confidence))
    with v.locked():  # id allocation + write must be atomic: parallel ingests of
        # the same case would otherwise draw the same lesson_id and overwrite
        lesson_obj = v.new_lesson(
            case_id=case_id,
            source_summary=(source_summary or "").strip() or _oneline(lesson, 60),
            content=lesson.strip(),
            tags=tags,
            confidence=confidence,
        )
        v._save_locked(lesson_obj, action="ingest")
    return (
        f"Saved {lesson_obj.lesson_id} → {v.relpath(lesson_obj.path)}\n"
        f"tags: {', '.join(tags) or '-'} · confidence {confidence} · index & log updated"
    )


def _similar(a: Lesson, b: Lesson) -> bool:
    if _jaccard(set(tokenize(a.source_summary)), set(tokenize(b.source_summary))) >= 0.6:
        return True
    tags_sim = _jaccard(set(a.tags), set(b.tags))
    content_sim = _jaccard(set(tokenize(a.content)), set(tokenize(b.content)))
    return tags_sim >= 0.5 and content_sim >= 0.4


def _similar_pre(
    sa: set, ta: set, ca: set, sb: set, tb: set, cb: set
) -> bool:
    if _jaccard(sa, sb) >= 0.6:
        return True
    return _jaccard(ta, tb) >= 0.5 and _jaccard(ca, cb) >= 0.4


def memory_lint(scope: str = "all", vault: Vault | None = None) -> str:
    try:
        v = _open_vault(vault)
    except VaultNotInitialized as e:
        return str(e)

    all_lessons = v.lessons(include_superseded=True)
    lessons = all_lessons
    if scope.startswith("tag:"):
        target = scope[4:].strip()
        lessons = [l for l in all_lessons if target in l.tags]
    if not lessons:
        return "No lessons in scope."

    findings: list[str] = []
    proposals: list[str] = []
    all_ids = {l.lesson_id for l in all_lessons}  # DANGLING must look beyond scope
    active = [l for l in lessons if not l.superseded_by]

    pre = [
        (l, set(tokenize(l.source_summary)), set(l.tags), set(tokenize(l.content)))
        for l in active
    ]
    for i, (a, sa, ta, ca) in enumerate(pre):
        for b, sb, tb, cb in pre[i + 1 :]:
            if _similar_pre(sa, ta, ca, sb, tb, cb):
                findings.append(f"DUPLICATE {a.lesson_id} ≈ {b.lesson_id}")
                keeper, gone = (
                    (a, b) if a.use_count >= b.use_count else (b, a)
                )  # keep the more-used lesson; the merge direction follows usage
                proposals.append(
                    f"### Merge {gone.lesson_id} into {keeper.lesson_id}\n"
                    f"- {a.lesson_id}: {a.source_summary} (used {a.use_count})\n"
                    f"- {b.lesson_id}: {b.source_summary} (used {b.use_count})\n"
                    f"- Review both lessons; merge any unique content from "
                    f"{gone.lesson_id} into {keeper.lesson_id} by hand, then run\n"
                    f"  `agentbrain apply <this-file>`\n\n"
                    f"```agentbrain\nsupersede: {gone.lesson_id} -> {keeper.lesson_id}\n```\n"
                )

    for l in lessons:
        d = _days_since(l.last_verified_at or l.created_at)
        if d is not None and d > 90 and not l.superseded_by:
            findings.append(f"STALE {l.lesson_id} (last verified {d} days ago)")
        exp = _days_since(l.valid_until)
        if l.valid_until and exp is not None and exp >= 0:
            findings.append(f"EXPIRED {l.lesson_id} (valid_until {l.valid_until})")
        if not l.tags:
            findings.append(f"ORPHAN {l.lesson_id} (no tags)")
        if l.confidence < 0.5:
            findings.append(f"LOWCONF {l.lesson_id} (confidence {l.confidence})")
        if l.superseded_by and l.superseded_by not in all_ids:
            findings.append(f"DANGLING {l.lesson_id} → missing {l.superseded_by}")

    if not findings:
        return "Lint clean: no duplicates, no stale/expired/orphan/low-confidence lessons."

    findings.sort()
    with v.locked():  # proposal + audit log as one atomic unit
        proposal_path = _next_proposal_path(v, "lint")
        atomic_write(
            proposal_path,
            "# Lint proposal — auto-generated\n\n"
            f"Scope: {scope}\nDate: {dt.date.today()}\n\n## Findings\n\n"
            + "\n".join(f"- {f}" for f in findings)
            + "\n\n## Suggested merges\n\n"
            + "\n".join(proposals or ["- none"])
            + "\n\n> Apply only after human approval.\n",
        )
        v._append_log_locked("lint", f"findings:{len(findings)}")
    return "\n".join(
        [f"Lint found {len(findings)} issue(s):", ""]
        + [f"- {f}" for f in findings]
        + [
            "",
            f"Proposal written: {v.relpath(proposal_path)}",
            "Review it, merge content by hand where needed, then run "
            f"`agentbrain apply {v.relpath(proposal_path)}`.",
        ]
    )


def memory_distill(
    window_days: int = 30,
    min_repeat: int = 3,
    vault: Vault | None = None,
) -> str:
    try:
        v = _open_vault(vault)
    except VaultNotInitialized as e:
        return str(e)

    cutoff = (dt.date.today() - dt.timedelta(days=window_days)).isoformat()
    entries = [e for e in v.log_entries() if e["date"] >= cutoff and e["action"] == "ingest"]

    case_counts: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    for e in entries:
        obj = e["object"]
        case_id = obj.rsplit("-lesson-", 1)[0] if "-lesson-" in obj else obj
        case_counts[case_id] += 1
        for t in e["tags"]:
            tag_counts[t] += 1

    hot_cases = sorted((c, n) for c, n in case_counts.items() if c and n >= min_repeat)
    hot_tags = sorted((t, n) for t, n in tag_counts.items() if n >= min_repeat)
    if not hot_cases and not hot_tags:
        return (
            f"No recurring patterns in the last {window_days} days "
            f"(threshold: {min_repeat}). Nothing to distill."
        )

    lines = [f"Distill analysis (window {window_days}d, {len(entries)} ingests):", ""]
    sections: list[str] = []
    for c, n in hot_cases:
        lines.append(f"- case `{c}` ingested {n}× in window")
        members = [e["object"] for e in entries if e["object"].rsplit("-lesson-", 1)[0] == c]
        sections.append(
            f"## Case `{c}` — {n} lessons\n\n"
            + "\n".join(f"- {m}" for m in members)
            + "\n\nSuggested: distill these into one playbook lesson; mark members "
            "superseded after approval.\n"
        )
    for t, n in hot_tags:
        lines.append(f"- tag `{t}` appeared {n}× in window")
        sections.append(
            f"## Tag `{t}` — {n} occurrences\n\nSuggested: consolidate recurring "
            f"`{t}` lessons into one distilled lesson after approval.\n"
        )

    with v.locked():  # proposal + audit log as one atomic unit
        proposal_path = _next_proposal_path(v, "distill")
        atomic_write(
            proposal_path,
            "# Distill proposal — auto-generated\n\n"
            f"Window: {window_days} days · threshold: {min_repeat}\n\n"
            + "\n".join(sections),
        )
        v._append_log_locked("distill", f"cases:{len(hot_cases)},tags:{len(hot_tags)}")
    lines += ["", f"Proposal written: {v.relpath(proposal_path)} — human approval required."]
    return "\n".join(lines)


def memory_profile(vault: Vault | None = None) -> str:
    try:
        v = _open_vault(vault)
    except VaultNotInitialized as e:
        return str(e)
    text = Profile(v).read()
    if not text:
        return (
            "Profile is empty. The owner can add Markdown files under "
            "Agent-Profile/Immutable/ (hard rules) and Agent-Profile/Mutable-Hints/ "
            "(soft preferences); agents read them via memory_profile."
        )
    return text


def memory_suggest(title: str, change: str, vault: Vault | None = None) -> str:
    try:
        v = _open_vault(vault)
    except VaultNotInitialized as e:
        return str(e)
    if not title or not title.strip():
        return "Refused: empty title."
    if not change or not change.strip():
        return "Refused: empty change."
    path = Profile(v).suggest(title, change)
    v.append_log("suggest", v.relpath(path))
    return (
        f"Suggestion saved → {v.relpath(path)}\n"
        "The owner reviews _suggestions/ and applies it manually; "
        "Agent-Profile itself was not modified."
    )
